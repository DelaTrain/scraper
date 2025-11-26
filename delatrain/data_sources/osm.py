import osmnx
import numpy
from networkx import MultiGraph
from functools import cache
from geopandas import GeoDataFrame
from heapq import heappop, heappush
from typing import Iterable
from ..structures.stations import Station
from ..structures.position import Position
from ..structures.paths import Rail

osmnx.settings.max_query_area_size = float("inf")
osmnx.settings.cache_folder = "osmnx_cache"
osmnx.settings.requests_timeout = 600

_STATION_SEARCH_CUTOFF = 15_000  # in meters
_STATION_HITBOX_RADIUS = 150  # in meters
_AUGMENTED_EDGES_MULTIPLIER = 2.0
_MAX_ANGLE_BETWEEN_RAILS = 75  # in degrees


@cache
def _all_stations() -> GeoDataFrame:
    tags = {
        "railway": ["station", "halt"],
    }
    gdf = osmnx.features_from_place("Poland", tags)  # type: ignore
    return gdf


@cache
def _all_rails() -> MultiGraph:
    tags = '["railway"~"construction|rail"]'
    graph = osmnx.graph_from_place(
        "Poland",
        custom_filter=tags,
        simplify=False,
        retain_all=True,
    )
    return graph.to_undirected()


def augment_rail_graph(stations: list[Station], default_speed: int) -> None:
    graph = _all_rails()
    for station in stations:
        graph.add_node(station.augmented_node_id, y=station.latitude, x=station.longitude)
    for node in graph.nodes(data=True):
        if node[0] < 0:
            continue
        for station in stations:
            distance = station.location.distance_to(Position(node[1]["y"], node[1]["x"]))
            if distance > _STATION_HITBOX_RADIUS:
                continue
            graph.add_edge(
                node[0],
                station.augmented_node_id,
                length=distance * _AUGMENTED_EDGES_MULTIPLIER,
                maxspeed=str(default_speed),
            )


def get_station_by_name(name: str) -> Station | None:
    stations = _all_stations()
    matched = stations[stations["name"] == name]
    if matched.empty:
        return None
    matched = matched.iloc[0]
    lat = float(matched.geometry.y)
    long = float(matched.geometry.x)
    return Station(name, Position(lat, long))


def _find_angle_between(p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]) -> float:
    a = numpy.array(p1)
    b = numpy.array(p2)
    c = numpy.array(p3)

    ba = a - b
    bc = c - b

    cosine_angle = numpy.dot(ba, bc) / (numpy.linalg.norm(ba) * numpy.linalg.norm(bc))
    cosine_angle = numpy.clip(cosine_angle, -1.0, 1.0)
    angle = numpy.arccos(cosine_angle)

    return float(numpy.degrees(angle))


def _average_station_location(station: Station, rails: list[Rail]) -> Position:
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


def find_rails_to_adjacent_stations(
    station: Station, all_stations: Iterable[Station], default_speed: int
) -> tuple[list[Rail], Position]:
    graph = _all_rails()
    pq = [(0.0, station.augmented_node_id, False)]
    distances = {station.augmented_node_id: 0.0}
    previous = {}

    while pq:
        current_distance, current_node, in_station_radius = heappop(pq)
        if current_node in previous:
            continue  # already processed
        for neighbor in graph.neighbors(current_node):
            if current_node > 0 and neighbor > 0:
                p = previous[current_node]
                angle = _find_angle_between(
                    (graph.nodes[p]["x"], graph.nodes[p]["y"]),
                    (graph.nodes[current_node]["x"], graph.nodes[current_node]["y"]),
                    (graph.nodes[neighbor]["x"], graph.nodes[neighbor]["y"]),
                )
                if 180 - angle > _MAX_ANGLE_BETWEEN_RAILS:
                    continue  # too sharp of an angle
            edge_data = graph.get_edge_data(current_node, neighbor)
            edge_length = min(d["length"] for d in edge_data.values())
            distance = current_distance + edge_length
            if distance >= distances.get(neighbor, float("inf")) or distance > _STATION_SEARCH_CUTOFF:
                continue  # not a better path or too far
            neighbor_in_station_radius = distance >= 2 * _STATION_HITBOX_RADIUS and any(
                Position(graph.nodes[neighbor]["y"], graph.nodes[neighbor]["x"]).distance_to(
                    Position(graph.nodes[s.augmented_node_id]["y"], graph.nodes[s.augmented_node_id]["x"])
                )
                <= _STATION_HITBOX_RADIUS
                for s in all_stations
                if s != station
            )
            if not neighbor_in_station_radius and in_station_radius:
                continue  # stop at adjacent stations unless they are really close to origin
            distances[neighbor] = distance
            previous[neighbor] = current_node
            heappush(pq, (distance, neighbor, neighbor_in_station_radius))

    rails = []
    for s in all_stations:
        if s == station or s.augmented_node_id not in previous:
            continue
        path = []
        speeds = []
        current = s.augmented_node_id
        while current != station.augmented_node_id:
            prev = previous[current]
            if current > 0:
                edge_data = graph.get_edge_data(prev, current)
                avg_speed = sum(int(d.get("maxspeed", str(default_speed))) for d in edge_data.values()) / len(edge_data)
                speeds.append(avg_speed)
                path.append(Position(graph.nodes[current]["y"], graph.nodes[current]["x"]))
            current = prev
        speeds.pop()
        rails.append(Rail(s, station, path, speeds))
    average_location = _average_station_location(station, rails)
    return rails, average_location
