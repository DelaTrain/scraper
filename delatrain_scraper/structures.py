from dataclasses import dataclass
from datetime import time, date


@dataclass
class StationTrack:
    platform: int
    track: str


@dataclass
class TrainSummary:
    category: str
    number: int
    url: str
    days: str  # TODO: change to DateRange


@dataclass
class TrainStop:
    station_name: str
    arrival_time: time | None
    departure_time: time | None
    track: StationTrack | None


@dataclass
class Train:
    category: str
    number: int
    name: str | None
    stops: list[TrainStop]
    params: list[str]
    # days: DateRange  # TODO
