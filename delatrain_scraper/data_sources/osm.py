import osmnx
from functools import cache
from geopandas import GeoDataFrame
from ..structures.stations import Station


@cache
def _all_stations() -> GeoDataFrame:
    osmnx.settings.max_query_area_size = float("inf")
    osmnx.settings.cache_folder = "osmnx_cache"
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
    return Station(name, lat, long)  # type: ignore
