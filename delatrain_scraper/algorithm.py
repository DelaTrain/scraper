from dataclasses import dataclass
from datetime import date
from .structures import Station, TrainSummary, Train


@dataclass
class ScraperState:
    stations_to_locate: set[str]
    stations_to_scrape: set[Station]
    trains_to_scrape: set[TrainSummary]

    day: date
    stations: dict[str, Station]
    trains: list[Train]

    def __init__(self, day: date, starting_station: str) -> None:
        self.day = day
        self.stations_to_locate = {starting_station}
        self.stations_to_scrape = set()
        self.trains_to_scrape = set()
        self.stations = {}
        self.trains = []

    def finished(self) -> bool:
        return not self.stations_to_locate and not self.stations_to_scrape and not self.trains_to_scrape

    def scrape(self) -> None:
        # TODO: implement scraping logic
        from time import sleep

        print("Scraping... (not implemented yet)")
        sleep(5)
