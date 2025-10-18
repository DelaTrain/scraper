from dataclasses import dataclass
from datetime import time, date


@dataclass
class StationTrack:
    platform: int
    track: int


@dataclass
class TrainSummary:
    category: str
    number: int
    url: str
    days: str  # TODO: change to DateRange


@dataclass
class Train:
    category: str
    number: int
    name: str | None
    stations: list[tuple[str, time, time, StationTrack | None]]
    params: list[str]
    # days: DateRange  # TODO
