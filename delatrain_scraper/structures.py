from dataclasses import dataclass, field
from datetime import time, date
from typing import Self

_ROMAN_NUMERALS = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


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


@dataclass
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
    params: list[str] = field(default_factory=list)
    # days: DateRange  # TODO
