from pandas import DataFrame
from dataclasses import dataclass, InitVar, field
from datetime import date
from .structures.stations import Station
from .structures.trains import TrainSummary, Train, TrainStop
from .structures.position import Position
from .structures.paths import Rail
from .data_sources.osm import get_station_by_name, find_rails_to_adjacent_stations
from .data_sources.rozklad_pkp import get_train_urls_from_station, get_full_train_info


@dataclass
class ScraperState:
    # Inputs
    day: date
    starting_station: InitVar[str]
    rail_radius: int = 0  # finding radius, in kilometers
    rail_interval: int = 0  # resampling interval, in meters

    # Scraper queues
    stations_to_locate: set[str] = field(default_factory=set)
    stations_to_scrape: set[Station] = field(default_factory=set)
    trains_to_scrape: list[TrainSummary] = field(default_factory=list)

    # Scraper helpers
    broken_stations: set[str] = field(default_factory=set)
    all_stops: dict[TrainStop, Train] = field(default_factory=dict)  # for fast lookup when handling duplicates
    blacklisted_trains: list[Train] = field(default_factory=list)  # alternative train numbers to ignore

    # Scraper results
    stations: set[Station] = field(default_factory=set)
    trains: list[Train] = field(default_factory=list)

    # Pathfinding queues
    rails_to_find: set[Station] = field(default_factory=set)
    trains_to_analyze: list[Train] = field(default_factory=list)

    # Pathfinding results
    rails: dict[tuple[str, str], Rail] = field(default_factory=dict)
    routing_rules: dict[tuple[str, str], None] = field(default_factory=dict)  # TODO

    def __post_init__(self, starting_station: str) -> None:
        self.stations_to_locate.add(starting_station)

    def get_export_data(self) -> dict:
        return {
            "day": self.day,
            "stations": self.stations | self.stations_to_scrape,
            "trains": self.trains,
            "rails": list(self.rails.values()),
        }

    def is_scrape_finished(self) -> bool:
        return not self.stations_to_locate and not self.stations_to_scrape and not self.trains_to_scrape

    def is_fixup_finished(self) -> bool:
        return not self.broken_stations

    def is_pathfinding_finished(self) -> bool:
        return not self.rails_to_find

    def _locate_stations(self) -> None:
        print("Locating stations...")
        for station_name in self.stations_to_locate.copy():
            station = get_station_by_name(station_name)
            if station:
                print(f"Located station: {station.name} at {station.latitude}, {station.longitude}")
                self.stations_to_scrape.add(station)
            else:
                print(f"Station '{station_name}' could not be located. Run fixup later to resolve manually.")
                self.broken_stations.add(station_name)
            self.stations_to_locate.remove(station_name)

    def _choose_station_to_scrape(self) -> Station:
        if not self.stations:
            return next(iter(self.stations_to_scrape))
        min_distance = float("inf")
        chosen_station = None
        for station in self.stations_to_scrape:
            for scraped_station in self.stations:
                d = station.distance_to(scraped_station)
                if d < min_distance:
                    min_distance = d
                    chosen_station = station
        return chosen_station  # type: ignore

    def _scrape_station(self) -> None:
        station = self._choose_station_to_scrape()
        print(f"Scraping station: {station.name}")
        train_summaries = get_train_urls_from_station(station.name, self.day)
        for summary in train_summaries:
            hs = hash(summary)
            if all(hash(t) != hs for t in self.blacklisted_trains) and all(hash(t) != hs for t in self.trains):
                self.trains_to_scrape.append(summary)
                print(f"Found new train: {summary}")
        self.stations_to_scrape.remove(station)
        self.stations.add(station)

    def _find_duplicate_subtrain(self, train: Train) -> Train | None:
        if train in self.trains:
            found = next(t for t in self.trains if t == train)
            print(f"Duplicate subtrain detected by direct match: {found}")
            return found
        found = None
        for existing_stop in train.stops:
            if existing_stop in self.all_stops:
                if found == self.all_stops[existing_stop]:
                    print(
                        f"Duplicate subtrain detected based on multiple stops (example: {existing_stop.station_name}): {found}"
                    )
                    return found
                found = self.all_stops[existing_stop]
        return None

    def _handle_duplicate_subtrain(self, train: Train) -> Train:
        found = self._find_duplicate_subtrain(train)
        if not found:
            return train
        self.blacklisted_trains.extend((train, found))
        self.trains.remove(found)
        self.all_stops = {k: v for k, v in self.all_stops.items() if v != found}

        result = found
        if len(train.stops) > len(found.stops):
            print("New subtrain has more stops.")
            result = train
        elif train.number < found.number:
            print("New subtrain has lower train number.")
            result = train
        else:
            print("No major improvements found.")
        result.name = result.name or train.name
        result.params.update(train.params)
        return result

    def _scrape_train(self) -> None:
        train_summary = self.trains_to_scrape[-1]
        print(f"Scraping train: {train_summary}")
        train = get_full_train_info(train_summary.url, train_summary.days)
        print(f"Train has {len(train)} subtrain(s).")

        filtered = [t for subtrain in train if (t := self._handle_duplicate_subtrain(subtrain))]
        self.trains.extend(filtered)

        for subtrain in filtered:
            print(f"Analyzing subtrain: {subtrain}")
            for stop in subtrain.stops:
                if stop.arrival_time is not None or stop.departure_time is not None:
                    self.all_stops[stop] = subtrain
                dummy_station = Station(stop.station_name)
                if (
                    dummy_station not in self.stations
                    and dummy_station not in self.stations_to_scrape
                    and stop.station_name not in self.broken_stations
                ):
                    self.stations_to_locate.add(stop.station_name)
                    print(f"Found new station: {stop.station_name}")
        self.trains_to_scrape.pop()

    def scrape(self) -> None:
        if self.stations_to_locate:
            self._locate_stations()
        elif self.trains_to_scrape:
            self._scrape_train()
        elif self.stations_to_scrape:
            self._scrape_station()

    def _find_rails_from_station(self, station: Station) -> None:
        print(f"Finding rails from station: {station.name}")
        nearby_stations = [
            s
            for s in self.stations | self.stations_to_scrape
            if s != station and station.distance_to(s) < self.rail_radius
        ]
        rails, better_lat, better_lon = find_rails_to_adjacent_stations(station, nearby_stations)

        temp_rails = {}
        for rail in rails:
            key = (rail.start_station, rail.end_station)
            if key not in self.rails:
                original_length = rail.length
                original_points = len(rail.points)
                rail.simplify_by_resampling(self.rail_interval)
                temp_rails[key] = rail
                print(
                    f"Found rail: {rail.start_station} -> {rail.end_station}, length: {original_length:.2f} -> {rail.length:.2f} km, points: {original_points} -> {len(rail.points)}"
                )
        station.location = Position(better_lat, better_lon)
        print(f"Updated station location to: {better_lat}, {better_lon}")
        self.rails.update(temp_rails)

    def fixup(self, saved: DataFrame) -> None:
        station = next(iter(self.broken_stations))
        print(f"Fixing station: {station}")
        auto = saved[saved[0] == station]
        if auto.empty:
            print(f"OpenStreetMap search: https://www.openstreetmap.org/search?query={station.replace(' ', '+')}")
            location = input("Paste OpenStreetMap location URL for valid address: ")
            location = location.strip().rstrip("/").split("/")
            if len(location) < 5:
                raise ValueError(
                    "Invalid URL format. Try something like: https://www.openstreetmap.org/#map=16/48.18513/16.37559"
                )
            lat = float(location[-2])
            lon = float(location[-1])
            saved.loc[len(saved)] = [station, lat, lon]
        else:
            row = auto.iloc[0]
            lat = float(row[1])
            lon = float(row[2])
            print(f"Using saved coordinates: {lat}, {lon}")
        found_station = Station(station, Position(lat, lon))
        self.stations.add(found_station)
        self.broken_stations.remove(station)
        print("Station fixed successfully.")

    def pathfind(self) -> None:
        if self.rails_to_find:
            station = next(iter(self.rails_to_find))
            self._find_rails_from_station(station)
            self.rails_to_find.remove(station)

    def reset_pathfinding(self, radius: int, interval: int) -> None:
        self.rail_radius = radius
        self.rail_interval = interval
        self.rails_to_find = self.stations | self.stations_to_scrape
        self.rails = {}
        print(f"Initialized pathfinding state with radius {radius} km and interval {interval} m.")
