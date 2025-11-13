import osmnx
import networkx
from functools import cache
from geopandas import GeoDataFrame
from ..structures.stations import Station
from ..structures.position import Position
from ..structures.paths import Rail

osmnx.settings.max_query_area_size = float("inf")
osmnx.settings.cache_folder = "osmnx_cache"
osmnx.settings.requests_timeout = 600

_STATION_HITBOX_RADIUS = 300  # in meters
_DEFAULT_RAIL_MAX_SPEED = "120"  # in km/h


@cache
def _all_stations() -> GeoDataFrame:
    tags = {
        "railway": ["station", "halt"],
    }
    gdf = osmnx.features_from_place("Poland", tags)  # type: ignore
    return gdf


def get_station_by_name(name: str) -> Station | None:
    stations = _all_stations()
    matched = stations[stations["name"] == name]
    if matched.empty:
        return None
    matched = matched.iloc[0]
    lat = float(matched.geometry.y)
    long = float(matched.geometry.x)
    return Station(name, Position(lat, long))


def _find_rail(from_station: Station, to_station: Station, graph: networkx.MultiDiGraph) -> Rail | None:
    from_station, to_station = sorted((from_station, to_station), key=lambda s: s.name)
    from_node = osmnx.nearest_nodes(graph, from_station.longitude, from_station.latitude)
    to_node = osmnx.nearest_nodes(graph, to_station.longitude, to_station.latitude)
    try:
        path = networkx.shortest_path(graph, from_node, to_node, weight="length")
    except networkx.NetworkXNoPath:
        return None
    if len(path) < 2:
        return None
    points = [Position(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in path]
    edges = [graph.edges[path[i], path[i + 1], 0] for i in range(len(path) - 1)]
    max_speeds = [float(edge.get("maxspeed", _DEFAULT_RAIL_MAX_SPEED)) for edge in edges]
    return Rail(from_station.name, to_station.name, points, max_speeds)


def _is_rail_redundant(rail: Rail, stations: list[Station]) -> bool:
    for station in stations:
        if station.name in (rail.start_station, rail.end_station):
            continue
        for point in rail.points:
            if station.location.distance_to(point) < _STATION_HITBOX_RADIUS / 1000:
                return True
    return False


def find_rails_to_adjacent_stations(
    main_station: Station, nearby_stations: list[Station]
) -> tuple[list[Rail], float, float]:
    tags = '["railway"~"construction|rail"]'
    box_radius = _STATION_HITBOX_RADIUS
    if nearby_stations:
        box_radius += max(main_station.distance_to(station) for station in nearby_stations) * 1000

    graph = osmnx.graph_from_point(
        (main_station.latitude, main_station.longitude),
        dist=box_radius,
        dist_type="bbox",
        custom_filter=tags,
        simplify=False,
        retain_all=True,
    )
    main_node = osmnx.nearest_nodes(graph, main_station.longitude, main_station.latitude)
    rails = [rail for station in nearby_stations if (rail := _find_rail(main_station, station, graph))]
    rails = [rail for rail in rails if not _is_rail_redundant(rail, nearby_stations)]
    return rails, graph.nodes[main_node]["y"], graph.nodes[main_node]["x"]
