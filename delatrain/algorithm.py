from pandas import DataFrame
from dataclasses import dataclass, InitVar, field
from datetime import date
from functools import cached_property
from .structures.stations import Station
from .structures.trains import TrainSummary, Train, TrainStop
from .structures.position import Position
from .structures.paths import Rail, RoutingRule
from .data_sources.osm import get_station_by_name, find_rails_to_adjacent_stations
from .data_sources.rozklad_pkp import get_train_urls_from_station, get_full_train_info
from .routing import construct_rails_graph, find_rules_for_train
from .utils import log


@dataclass
class ScraperState:
    # Inputs
    day: date
    starting_station: InitVar[str]
    rail_interval: int = 0  # resampling interval, in meters
    default_max_speed: int = 0  # in km/h
    banned_categories: set[str] = field(default_factory=set)

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
    rails_to_find: list[Station] = field(default_factory=list)
    rails_to_simplify: dict[tuple[str, str], Rail] = field(default_factory=dict)
    trains_to_analyze: list[Train] = field(default_factory=list)

    # Pathfinding results
    rails: dict[tuple[str, str], Rail] = field(default_factory=dict)
    routing_rules: dict[tuple[str, str], RoutingRule] = field(default_factory=dict)

    def __post_init__(self, starting_station: str) -> None:
        self.stations_to_locate.add(starting_station)

    def _usable_stations(self) -> set[Station]:  # TODO: fix caching
        return self.stations | self.stations_to_scrape
    
    @cached_property
    def _usable_rails(self) -> frozenset[Rail]:
        return frozenset(self.rails.values()) | frozenset(self.rails_to_simplify.values())

    def get_export_data(self) -> dict:
        return {
            "day": self.day,
            "stations": self._usable_stations(),
            "trains": self.trains,
            "rails": list(self._usable_rails),
            "routing": list(self.routing_rules.values()),
        }

    def is_scrape_finished(self) -> bool:
        return not self.stations_to_locate and not self.stations_to_scrape and not self.trains_to_scrape

    def is_fixup_finished(self) -> bool:
        return not self.broken_stations

    def is_pathfinding_finished(self) -> bool:
        return not self.rails_to_find and not self.rails_to_simplify  # and not self.trains_to_analyze # TODO

    def _locate_stations(self) -> None:
        log("Locating stations...")
        for station_name in self.stations_to_locate.copy():
            station = get_station_by_name(station_name)
            if station:
                log(f"Located station: {station.name} at {station.latitude}, {station.longitude}")
                self.stations_to_scrape.add(station)
            else:
                log(f"Station '{station_name}' could not be located. Run `fixup stations` later to resolve manually.")
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
        log(f"Scraping station: {station.name}")
        train_summaries = get_train_urls_from_station(station.name, self.day)
        for summary in train_summaries:
            if summary.category in self.banned_categories:
                log(f"Skipping because of banned train category: {summary}")
                continue
            hs = hash(summary)
            if all(hash(t) != hs for t in self.blacklisted_trains) and all(hash(t) != hs for t in self.trains):
                self.trains_to_scrape.append(summary)
                log(f"Found new train: {summary}")
        self.stations_to_scrape.remove(station)
        self.stations.add(station)

    def _find_duplicate_subtrain(self, train: Train) -> Train | None:
        if train in self.trains:
            found = next(t for t in self.trains if t == train)
            log(f"Duplicate subtrain detected by direct match: {found}")
            return found
        found = None
        for existing_stop in train.stops:
            if existing_stop in self.all_stops:
                if found == self.all_stops[existing_stop]:
                    log(
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
            log("New subtrain has more stops.")
            result = train
        elif train.number < found.number:
            log("New subtrain has lower train number.")
            result = train
        else:
            log("No major improvements found.")
        result.name = result.name or train.name
        result.params.update(train.params)
        return result

    def _scrape_train(self) -> None:
        train_summary = self.trains_to_scrape[-1]
        log(f"Scraping train: {train_summary}")
        train = get_full_train_info(train_summary.url, train_summary.days)
        log(f"Train has {len(train)} subtrain(s).")

        filtered = [t for subtrain in train if (t := self._handle_duplicate_subtrain(subtrain))]
        self.trains.extend(filtered)

        for subtrain in filtered:
            log(f"Analyzing subtrain: {subtrain}")
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
                    log(f"Found new station: {stop.station_name}")
        self.trains_to_scrape.pop()

    def scrape(self) -> None:
        if self.stations_to_locate:
            self._locate_stations()
        elif self.trains_to_scrape:
            self._scrape_train()
        elif self.stations_to_scrape:
            self._scrape_station()

    def _cascade_station_deletion(self, station_name: str) -> tuple[list[Train], list[str]]:
        trains_to_delete = []
        for train in self.trains:
            if any(stop.station_name == station_name for stop in train.stops):
                trains_to_delete.append(train)
        stations_to_delete = [station_name]
        for station in self.broken_stations:
            if station == station_name:
                continue
            for train in self.trains:
                if train in trains_to_delete:
                    continue
                if any(stop.station_name == station for stop in train.stops):
                    break
            else:
                stations_to_delete.append(station)
        return trains_to_delete, stations_to_delete

    def _delete_broken_station(self, station_name: str) -> None:
        trains_to_delete, stations_to_delete = self._cascade_station_deletion(station_name)
        log("These trains will be deleted:")
        for train in trains_to_delete:
            log(f"- {train}")
        log("These broken stations will be deleted:")
        for station in stations_to_delete:
            log(f"- {station}")

        confirm = input("Are you sure you want to proceed? (y/N) ")
        if confirm.strip().lower() != "y":
            raise ValueError("Station deletion aborted")

        for train in trains_to_delete:
            self.trains.remove(train)
            self.blacklisted_trains.append(train)
        for station in stations_to_delete:
            self.broken_stations.remove(station)

    def fixup(self, saved: DataFrame) -> None:
        station = next(iter(self.broken_stations))
        log(f"Fixing station: {station}")
        auto = saved[saved[0] == station]
        if auto.empty:
            log(f"OpenStreetMap search: https://www.openstreetmap.org/search?query={station.replace(' ', '+')}")
            location = input("Paste OpenStreetMap location URL for a valid address or type 'delete': ")
            if location.strip().lower() == "delete":
                self._delete_broken_station(station)
                return
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
            log(f"Using saved coordinates: {lat}, {lon}")
        found_station = Station(station, Position(lat, lon))
        self.stations.add(found_station)
        self.broken_stations.remove(station)
        log("Station fixed successfully.")

    def _find_rails_from_station(self) -> None:
        station = next(iter(self.rails_to_find))
        log(f"Finding rails from station: {station.name}")
        rails, better_pos = find_rails_to_adjacent_stations(station, self._usable_stations(), self.default_max_speed)
        new_rails = {}
        for rail in rails:
            key = (rail.start_station.name, rail.end_station.name)
            if key not in self.rails_to_simplify:
                new_rails[key] = rail
                log(f"Found rail: {rail.start_station.name} -> {rail.end_station.name}")
        station.accurate_location = better_pos
        log(f"Updated station location to: {better_pos.latitude}, {better_pos.longitude}")
        self.rails_to_simplify.update(new_rails)
        self.rails_to_find.remove(station)

    def _simplify_rail(self) -> None:
        key, rail = next(iter(self.rails_to_simplify.items()))
        log(f"Simplifying rail: {rail.start_station.name} -> {rail.end_station.name}")
        rail.extend_ends(self.default_max_speed)
        original_length = rail.length
        original_points = len(rail.points)
        rail.simplify_by_resampling(self.rail_interval)
        self.rails[key] = rail
        log(
            f"Simplified rail - length: {original_length:.2f} -> {rail.length:.2f} km, points: {original_points} -> {len(rail.points)}"
        )
        del self.rails_to_simplify[key]

    def pathfind(self) -> None:
        if self.rails_to_find:
            self._find_rails_from_station()
        # elif self.rails_to_simplify:
        #     raise NotImplementedError
        #     self._simplify_rail()
        elif self.trains_to_analyze:
            self._analyze_train_route()

    def reset_pathfinding(self, interval: int, speed: int) -> None:
        self.rail_interval = interval
        self.default_max_speed = speed
        for station in self._usable_stations():
            station.accurate_location = None
        self.rails_to_find = sorted(self._usable_stations(), key=lambda s: s.name)
        self.rails_to_simplify = {}
        self.trains_to_analyze = self.trains.copy()
        self.rails = {}
        self.routing_rules = {}
        log(f"Initialized pathfinding state with interval of {interval} m and max speed of {speed} km/h.")

    def _analyze_train_route(self) -> None:
        train = self.trains_to_analyze[-1]
        log(f"Analyzing train route for: {train}")
        graph = construct_rails_graph(self._usable_rails)
        new_rules = find_rules_for_train(graph, train)
        for rule in new_rules:
            key = (rule.start_station, rule.end_station)
            if key not in self.routing_rules:
                self.routing_rules[key] = rule
                log(f"Found routing rule: {rule.start_station} -> {rule.end_station}")
        self.trains_to_analyze.pop()

