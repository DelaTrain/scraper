from dataclasses import dataclass
from datetime import date
from .structures import Station, TrainSummary, Train
from .data_sources.osm import get_station_by_name
from .data_sources.rozklad_pkp import get_train_urls_from_station, get_full_train_info


@dataclass
class ScraperState:
    stations_to_locate: set[str]
    stations_to_scrape: set[Station]
    trains_to_scrape: set[TrainSummary]

    day: date
    stations: set[Station]
    trains: list[Train]

    def __init__(self, day: date, starting_station: str) -> None:
        self.day = day
        self.stations_to_locate = {starting_station}
        self.stations_to_scrape = set()
        self.trains_to_scrape = set()
        self.stations = set()
        self.trains = []

    def finished(self) -> bool:
        return not self.stations_to_locate and not self.stations_to_scrape and not self.trains_to_scrape

    def _locate_stations(self) -> None:
        print("Locating stations...")
        for station_name in self.stations_to_locate.copy():
            station = get_station_by_name(station_name)
            if station:
                print(f"Located station: {station.name} at {station.latitude}, {station.longitude}")
                self.stations_to_scrape.add(station)
                self.stations_to_locate.remove(station_name)
            else:
                raise ValueError(f"Station '{station_name}' could not be located.")

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
            if summary not in self.trains_to_scrape and all(
                t.category != summary.category or t.number != summary.number for t in self.trains
            ):
                self.trains_to_scrape.add(summary)
                print(f"Found new train: {summary}")
        self.stations_to_scrape.remove(station)
        self.stations.add(station)

    def _scrape_train(self) -> None:
        train_summary = next(iter(self.trains_to_scrape))
        print(f"Scraping train: {train_summary}")
        train = get_full_train_info(train_summary.url)
        print(f"Train has {len(train)} subtrain(s).")
        self.trains.extend(train)
        for subtrain in train:
            print(f"Analyzing subtrain: {subtrain}")
            for stop in subtrain.stops:
                dummy_station = Station(stop.station_name)
                if dummy_station not in self.stations and dummy_station not in self.stations_to_scrape:
                    self.stations_to_locate.add(stop.station_name)
                    print(f"Found new station: {stop.station_name}")
        self.trains_to_scrape.remove(train_summary)

    def scrape(self) -> None:
        if self.stations_to_locate:
            self._locate_stations()
        elif self.trains_to_scrape:
            self._scrape_train()
        elif self.stations_to_scrape:
            self._scrape_station()
