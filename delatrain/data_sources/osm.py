import osmnx
import numpy
from networkx import MultiGraph
from geopandas import GeoDataFrame
from heapq import heappop, heappush, heapify
from typing import Iterable, Generator
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


def _find_angle_between(p1: Position, p2: Position, p3: Position) -> float:
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


def _average_station_location(station: Station, rails: list[Rail]) -> Position:
    if len(rails) == 0:
        return station.location
    sum_lat = 0.0
    sum_lon = 0.0
    for rail in rails:
        if rail.start_station == station:
            sum_lat += rail.points[0].latitude
            sum_lon += rail.points[0].longitude
        else:
            sum_lat += rail.points[-1].latitude
            sum_lon += rail.points[-1].longitude
    return Position(
        sum_lat / len(rails),
        sum_lon / len(rails),
    )


def _position_from_node(graph: MultiGraph, node: int, nearby_stations: Iterable[Station]) -> Position:
    if node > 0:
        return Position(graph.nodes[node]["y"], graph.nodes[node]["x"])
    return next(filter(lambda s: s.augmented_node_id == node, nearby_stations)).location


def _check_in_station_radius(graph: MultiGraph, u: int, v: int, nearby_stations: Iterable[Station]) -> bool:
    if u < 0 or v < 0:
        return True
    p1 = _position_from_node(graph, u, nearby_stations)
    p2 = _position_from_node(graph, v, nearby_stations)
    line_distance = p1.distance_to(p2)
    num_samples = int(line_distance // _LINE_SAMPLING_DISTANCE) + 1
    for i in range(num_samples + 1):
        ratio = i / num_samples
        sample_lat = p1.latitude + ratio * (p2.latitude - p1.latitude)
        sample_lon = p1.longitude + ratio * (p2.longitude - p1.longitude)
        sample_pos = Position(sample_lat, sample_lon)
        for station in nearby_stations:
            if station.location.distance_to(sample_pos) <= _STATION_HITBOX_RADIUS:
                return True
    return False


def _augmented_graph_neighbors(
    graph: MultiGraph, node: int, nearby_stations: Iterable[Station]
) -> Generator[int, None, None]:
    if node < 0:
        return
    for neighbor in graph.neighbors(node):
        yield neighbor
    for station in nearby_stations:
        if station.location.distance_to(_position_from_node(graph, node, nearby_stations)) <= _STATION_HITBOX_RADIUS:
            yield station.augmented_node_id


def _augmented_graph_edge_data(
    graph: MultiGraph, u: int, v: int, nearby_stations: Iterable[Station], default_speed: int
) -> dict[int, dict]:
    if u > 0 and v > 0:
        return graph.get_edge_data(u, v)  # type: ignore
    p1 = _position_from_node(graph, u, nearby_stations)
    p2 = _position_from_node(graph, v, nearby_stations)
    distance = p1.distance_to(p2) * _AUGMENTED_EDGES_MULTIPLIER
    return {0: {"length": distance, "maxspeed": str(default_speed)}}


def find_rails_to_adjacent_stations(  # TODO: convert to a class
    station: Station, all_stations: Iterable[Station], default_speed: int
) -> tuple[list[Rail], Position]:
    nearby_stations = [s for s in all_stations if s != station and station.distance_to(s) < _STATION_SEARCH_CUTOFF]

    graph = _all_rails()
    pq = []
    distances = {}
    previous = {}
    visited = set()

    for node in graph.nodes(data=True):
        dist = station.location.distance_to(Position(node[1]["y"], node[1]["x"]))
        if dist > _STATION_HITBOX_RADIUS:
            continue
        dist *= _AUGMENTED_EDGES_MULTIPLIER
        pq.append((dist, node[0], False))
        distances[node[0]] = dist
        previous[node[0]] = station.augmented_node_id

    heapify(pq)
    while pq:
        current_distance, current_node, in_station_radius = heappop(pq)
        if current_node in visited:
            continue  # already processed
        for neighbor in _augmented_graph_neighbors(graph, current_node, nearby_stations):
            if current_node > 0 and neighbor > 0:
                p = previous[current_node]
                angle = _find_angle_between(
                    _position_from_node(graph, p, nearby_stations + [station]),
                    _position_from_node(graph, current_node, nearby_stations),
                    _position_from_node(graph, neighbor, nearby_stations),
                )
                if 180 - angle > _MAX_ANGLE_BETWEEN_RAILS:
                    continue  # too sharp of an angle
            edge_data = _augmented_graph_edge_data(graph, current_node, neighbor, nearby_stations, default_speed)
            edge_length = min(d["length"] for d in edge_data.values())
            distance = current_distance + edge_length
            if distance >= distances.get(neighbor, float("inf")) or distance > _STATION_SEARCH_CUTOFF:
                continue  # not a better path or too far
            neighbor_in_station_radius = distance >= 2 * _STATION_HITBOX_RADIUS and _check_in_station_radius(
                graph, current_node, neighbor, nearby_stations
            )
            if not neighbor_in_station_radius and in_station_radius:
                continue  # stop at adjacent stations unless they are really close to origin
            distances[neighbor] = distance
            previous[neighbor] = current_node
            heappush(pq, (distance, neighbor, neighbor_in_station_radius))
        visited.add(current_node)

    rails = []
    for s in nearby_stations:
        if s.augmented_node_id not in previous:
            continue
        path = []
        speeds = []
        current = s.augmented_node_id
        while current != station.augmented_node_id:
            prev = previous[current]
            if current > 0:
                edge_data = _augmented_graph_edge_data(graph, prev, current, nearby_stations + [station], default_speed)
                avg_speed = sum(int(d.get("maxspeed", str(default_speed))) for d in edge_data.values()) / len(edge_data)
                speeds.append(avg_speed)
                path.append(_position_from_node(graph, current, nearby_stations))
            current = prev
        speeds.pop()
        rails.append(Rail(s, station, path, speeds))
    average_location = _average_station_location(station, rails)
    return rails, average_location
