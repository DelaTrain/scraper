from dataclasses import dataclass, field
from datetime import time, date
from typing import Self
from math import radians, sin, cos, sqrt, atan2

_ROMAN_NUMERALS = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}
_EARTH_RADIUS_KM = 6371.0


def _roman_numeral_to_decimal(s: str) -> int:
    total = 0
    prev_value = 0
    for char in s:
        value = _ROMAN_NUMERALS.get(char.upper(), 0)
        if value > prev_value:
            total += value - 2 * prev_value
        else:
            total += value
        prev_value = value
    return total


@dataclass(frozen=True)
class StationTrack:
    platform: int
    track: str

    @classmethod
    def from_pkp_string(cls, s: str | None) -> Self | None:
        if not s:
            return None
        parts = s.split("/")
        if len(parts) != 2:
            return None
        return cls(_roman_numeral_to_decimal(parts[0]), parts[1])


@dataclass(unsafe_hash=True)
class Station:
    name: str
    latitude: float = field(compare=False, hash=False, default=float("nan"))
    longitude: float = field(compare=False, hash=False, default=float("nan"))
    # connections will be added, that's why not frozen

    def distance_to(self, other: Self) -> float:  # haversine formula
        lat1 = radians(self.latitude)
        lon1 = radians(self.longitude)
        lat2 = radians(other.latitude)
        lon2 = radians(other.longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return _EARTH_RADIUS_KM * c


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
