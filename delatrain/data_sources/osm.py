import osmnx
import numpy
from networkx import MultiGraph
from geopandas import GeoDataFrame
from heapq import heappop, heappush, heapify
from typing import Iterable, Generator
from dataclasses import dataclass, field, InitVar
from ..structures.stations import Station
from ..structures.position import Position
from ..structures.paths import Rail
from ..utils import oneshot_cache

osmnx.settings.max_query_area_size = float("inf")
osmnx.settings.cache_folder = "osmnx_cache"
osmnx.settings.requests_timeout = 600

_STATION_SEARCH_CUTOFF = 20_000  # in meters
_STATION_HITBOX_RADIUS = 150  # in meters
_LINE_SAMPLING_DISTANCE = 10  # in meters
_AUGMENTED_EDGES_MULTIPLIER = 2.0
_MAX_ANGLE_BETWEEN_RAILS = 75  # in degrees


@oneshot_cache
def _all_stations() -> GeoDataFrame:
    tags = {
        "railway": ["station", "halt"],
    }
    gdf = osmnx.features_from_place("Poland", tags)  # type: ignore
    return gdf


@oneshot_cache
def _all_rails() -> MultiGraph:
    tags = '["railway"~"construction|rail"]'
    graph = osmnx.graph_from_place(
        "Poland",
        custom_filter=tags,
        simplify=False,
        retain_all=True,
    )
    return graph.to_undirected()


def get_station_by_name(name: str) -> Station | None:
    name_fixed = name[:-5] if name.endswith(" (NŻ)") else name
    stations = _all_stations()
    matched = stations[stations["name"] == name_fixed]
    if len(matched) != 1:
        return None
    matched = matched.iloc[0]
    lat = float(matched.geometry.y)
    long = float(matched.geometry.x)
    return Station(name, Position(lat, long))


def _calculate_angle(p1: Position, p2: Position, p3: Position) -> float:
    a = p1.to_array()
    b = p2.to_array()
    c = p3.to_array()

    ba = a - b
    bc = c - b
    norm_ba = numpy.linalg.norm(ba)
    norm_bc = numpy.linalg.norm(bc)

    if norm_ba == 0 or norm_bc == 0:
        return 180.0

    cosine_angle = numpy.dot(ba, bc) / (norm_ba * norm_bc)
    cosine_angle = numpy.clip(cosine_angle, -1.0, 1.0)
    angle = numpy.arccos(cosine_angle)

    return float(numpy.degrees(angle))


@dataclass(eq=False)
class RailFinder:
    starting_station: Station
    all_stations: InitVar[Iterable[Station]]
    default_speed: int
    graph: MultiGraph = field(default_factory=_all_rails)

    nearby_stations: list[Station] = field(init=False)
    nearby_stations_inclusive: list[Station] = field(init=False)
    priority_queue: list[tuple[float, int, bool]] = field(init=False, default_factory=list)
    distances: dict[int, float] = field(init=False, default_factory=dict)
    previous: dict[int, int] = field(init=False, default_factory=dict)
    visited: set[int] = field(init=False, default_factory=set)

    def __post_init__(self, all_stations: Iterable[Station]) -> None:
        self.nearby_stations = [
            s
            for s in all_stations
            if s != self.starting_station and self.starting_station.distance_to(s) < _STATION_SEARCH_CUTOFF
        ]
        self.nearby_stations_inclusive = self.nearby_stations + [self.starting_station]

    def _init_collections(self) -> None:
        for node in self.graph.nodes(data=True):
            dist = self.starting_station.location.distance_to(Position(node[1]["y"], node[1]["x"]))
            if dist > _STATION_HITBOX_RADIUS:
                continue
            dist *= _AUGMENTED_EDGES_MULTIPLIER
            self.priority_queue.append((dist, node[0], False))
            self.distances[node[0]] = dist
            self.previous[node[0]] = self.starting_station.augmented_node_id
        heapify(self.priority_queue)

    def _position_from_node(self, node: int) -> Position:
        if node > 0:
            return Position(self.graph.nodes[node]["y"], self.graph.nodes[node]["x"])
        return next(filter(lambda s: s.augmented_node_id == node, self.nearby_stations_inclusive)).location

    def _check_in_station_radius(self, u: int, v: int) -> bool:
        if u < 0 or v < 0:
            return True
        p1 = self._position_from_node(u)
        p2 = self._position_from_node(v)
        line_distance = p1.distance_to(p2)
        num_samples = int(line_distance // _LINE_SAMPLING_DISTANCE) + 1
        for i in range(num_samples + 1):
            ratio = i / num_samples
            sample_lat = p1.latitude + ratio * (p2.latitude - p1.latitude)
            sample_lon = p1.longitude + ratio * (p2.longitude - p1.longitude)
            sample_pos = Position(sample_lat, sample_lon)
            for station in self.nearby_stations:
                if station.location.distance_to(sample_pos) <= _STATION_HITBOX_RADIUS:
                    return True
        return False

    def _get_neighbors(self, node: int) -> Generator[int, None, None]:
        if node < 0:
            return
        for neighbor in self.graph.neighbors(node):
            yield neighbor
        for station in self.nearby_stations:
            if station.location.distance_to(self._position_from_node(node)) <= _STATION_HITBOX_RADIUS:
                yield station.augmented_node_id

    def _get_edge_data(self, u: int, v: int) -> dict[int, dict]:
        if u > 0 and v > 0:
            return self.graph.get_edge_data(u, v)  # type: ignore
        p1 = self._position_from_node(u)
        p2 = self._position_from_node(v)
        distance = p1.distance_to(p2) * _AUGMENTED_EDGES_MULTIPLIER
        return {0: {"length": distance, "maxspeed": str(self.default_speed)}}

    def _process_next_node(self) -> None:
        current_distance, current_node, in_station_radius = heappop(self.priority_queue)
        if current_node in self.visited:
            return  # already processed
        for neighbor in self._get_neighbors(current_node):
            if current_node > 0 and neighbor > 0 and self.previous[current_node] > 0:
                angle = _calculate_angle(
                    self._position_from_node(self.previous[current_node]),
                    self._position_from_node(current_node),
                    self._position_from_node(neighbor),
                )
                if 180 - angle > _MAX_ANGLE_BETWEEN_RAILS:
                    continue  # too sharp of an angle
            edge_data = self._get_edge_data(current_node, neighbor)
            edge_length = min(d["length"] for d in edge_data.values())
            distance = current_distance + edge_length
            if distance >= self.distances.get(neighbor, float("inf")) or distance > _STATION_SEARCH_CUTOFF:
                continue  # not a better path or too far
            neighbor_in_station_radius = distance >= 2 * _STATION_HITBOX_RADIUS and self._check_in_station_radius(
                current_node, neighbor
            )
            if not neighbor_in_station_radius and in_station_radius:
                continue  # stop at adjacent stations unless they are really close to origin
            self.distances[neighbor] = distance
            self.previous[neighbor] = current_node
            heappush(self.priority_queue, (distance, neighbor, neighbor_in_station_radius))
        self.visited.add(current_node)

    def _gather_rails(self) -> list[Rail]:
        rails = []
        for s in self.nearby_stations:
            if s.augmented_node_id not in self.previous:
                continue
            path = []
            speeds = []
            current = s.augmented_node_id
            while current != self.starting_station.augmented_node_id:
                prev = self.previous[current]
                if current > 0:
                    edge_data = self._get_edge_data(prev, current)
                    avg_speed = sum(int(d.get("maxspeed", str(self.default_speed))) for d in edge_data.values()) / len(
                        edge_data
                    )
                    speeds.append(avg_speed)
                    path.append(self._position_from_node(current))
                current = prev
            speeds.pop()
            rails.append(Rail(s, self.starting_station, path, speeds))
        return rails

    def _find_better_station_location(self, rails: list[Rail]) -> Position:
        if len(rails) == 0:
            return self.starting_station.location
        sum_lat = 0.0
        sum_lon = 0.0
        for rail in rails:
            if rail.start_station == self.starting_station:
                sum_lat += rail.points[0].latitude
                sum_lon += rail.points[0].longitude
            else:
                sum_lat += rail.points[-1].latitude
                sum_lon += rail.points[-1].longitude
        return Position(sum_lat / len(rails), sum_lon / len(rails))

    def find_rails(self) -> list[Rail]:
        self._init_collections()
        while self.priority_queue:
            self._process_next_node()
        rails = self._gather_rails()
        self.starting_station.accurate_location = self._find_better_station_location(rails)
        return rails
