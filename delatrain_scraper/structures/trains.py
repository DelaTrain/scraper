from dataclasses import dataclass, field
from datetime import time
from .stations import StationTrack


@dataclass(frozen=True)
class TrainSummary:
    category: str
    number: int
    url: str = field(compare=False, hash=False)
    days: str = field(compare=False, hash=False)  # TODO: change to DateRange

    def __str__(self) -> str:
        return f"{self.category} {self.number}"


@dataclass(frozen=True)
class TrainStop:
    station_name: str
    arrival_time: time | None
    departure_time: time | None
    track: StationTrack | None


@dataclass(unsafe_hash=True)
class Train:
    category: str
    number: int
    name: str | None = field(compare=False, hash=False)
    stops: list[TrainStop] = field(compare=False, hash=False)
    params: list[str] = field(compare=False, hash=False, default_factory=list)
    # days: DateRange  # TODO

    def __str__(self) -> str:
        return f"{self.category} {self.number}{f' "{self.name}"' if self.name else ''}"
