import osmnx
import numpy
from networkx import MultiDiGraph
from functools import cache
from geopandas import GeoDataFrame
from ..structures.stations import Station
from ..structures.position import Position
from ..structures.paths import Rail

osmnx.settings.max_query_area_size = float("inf")
osmnx.settings.cache_folder = "osmnx_cache"
osmnx.settings.requests_timeout = 600

_STATION_SEARCH_CUTOFF = 15  # in kilometers
_STATION_HITBOX_RADIUS = 100  # in meters
_AUGMENTED_EDGES_MULTIPLIER = 2.0
_DEFAULT_RAIL_MAX_SPEED = "120"  # in km/h

_negative_nodes = set()


@cache
def _all_stations() -> GeoDataFrame:
    tags = {
        "railway": ["station", "halt"],
    }
    gdf = osmnx.features_from_place("Poland", tags)  # type: ignore
    return gdf


@cache
def _all_rails() -> MultiDiGraph:
    tags = '["railway"~"construction|rail"]'
    graph = osmnx.graph_from_place(
        "Poland",
        custom_filter=tags,
        simplify=False,
        retain_all=True,
    )
    return graph


def augment_rail_graph(stations: list[Station]) -> None:
    if _negative_nodes:
        return  # already augmented
    graph = _all_rails()
    for station in stations:
        graph.add_node(station.augmented_node_id, y=station.latitude, x=station.longitude)
        _negative_nodes.add(station.augmented_node_id)
    for node in graph.nodes(data=True):
        if node[0] < 0:
            continue
        for station in stations:
            distance = station.location.distance_to(Position(node[1]["y"], node[1]["x"]))
            if distance > _STATION_HITBOX_RADIUS:
                continue
            station_node = station.augmented_node_id
            graph.add_edge(
                node[0],
                station_node,
                length=distance * _AUGMENTED_EDGES_MULTIPLIER,
                maxspeed=_DEFAULT_RAIL_MAX_SPEED,
            )
            graph.add_edge(
                station_node,
                node[0],
                length=distance * _AUGMENTED_EDGES_MULTIPLIER,
                maxspeed=_DEFAULT_RAIL_MAX_SPEED,
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


def find_rails_to_adjacent_stations(station: Station) -> tuple[list[Rail], float, float]:
    graph = _all_rails()
    raise NotImplementedError
