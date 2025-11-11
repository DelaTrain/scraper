from dataclasses import dataclass, field
from typing import Self
from .position import Position

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
    location: Position = field(compare=False, hash=False, default=Position.unknown())

    @property
    def latitude(self) -> float:
        return self.location.latitude
    
    @property
    def longitude(self) -> float:
        return self.location.longitude

    def distance_to(self, other: Self) -> float:
        return self.location.distance_to(other.location)
