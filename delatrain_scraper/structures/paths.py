from dataclasses import dataclass, field
from functools import cache
from .position import Position


@dataclass(unsafe_hash=True)
class Rail:
    start_station: str
    end_station: str
    points: list[Position] = field(compare=False, hash=False, default_factory=list)

    @property
    @cache
    def length(self) -> float:  # in kilometers
        return sum(self.points[i].distance_to(self.points[i + 1]) for i in range(len(self.points) - 1))
    
    def simplify_by_resampling(self, interval: int) -> None:  # interval in meters
        pass  # TODO
