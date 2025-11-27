import numpy
from dataclasses import dataclass
from typing import Self
from math import radians, sin, cos, sqrt, atan2

_EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Position:
    latitude: float
    longitude: float

    @classmethod
    def unknown(cls) -> Self:
        return cls(float("nan"), float("nan"))

    def distance_to(self, other: Self) -> float:  # haversine formula, in meters
        lat1 = radians(self.latitude)
        lon1 = radians(self.longitude)
        lat2 = radians(other.latitude)
        lon2 = radians(other.longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return _EARTH_RADIUS_KM * c * 1000

    def to_array(self) -> numpy.ndarray:
        return numpy.array([self.latitude, self.longitude])
