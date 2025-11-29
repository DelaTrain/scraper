from dataclasses import dataclass, field
from networkx import DiGraph
from jsonpickle import handlers
from .position import Position
from .stations import Station


def _find_point_at_distance(
    graph: DiGraph, start_position: Position, distance: float
) -> tuple[list[Position], Position | None]:  # returns (visited_points + next_point, interpolated_point)
    visited_points = []
    accumulated_distance = 0.0
    current_position = start_position
    while True:
        next_position = next(graph.successors(current_position), None)
        if not next_position:
            return visited_points, None
        segment_distance = current_position.distance_to(next_position)
        visited_points.append(next_position)
        if accumulated_distance + segment_distance >= distance:
            ratio = (distance - accumulated_distance) / segment_distance
            interpolated_x = current_position.longitude + ratio * (next_position.longitude - current_position.longitude)
            interpolated_y = current_position.latitude + ratio * (next_position.latitude - current_position.latitude)
            interpolated_point = Position(latitude=interpolated_y, longitude=interpolated_x)
            return visited_points, interpolated_point
        accumulated_distance += segment_distance
        current_position = next_position


@dataclass(unsafe_hash=True)
class Rail:
    start_station: Station
    end_station: Station
    points: list[Position] = field(compare=False, hash=False, default_factory=list)
    max_speed: list[float] = field(compare=False, hash=False, default_factory=list)  # in km/h

    def __post_init__(self):
        if self.start_station.name < self.end_station.name:
            return
        self.start_station, self.end_station = self.end_station, self.start_station
        self.points.reverse()
        self.max_speed.reverse()

    @property
    def length(self) -> float:  # in kilometers
        return sum(self.points[i].distance_to(self.points[i + 1]) for i in range(len(self.points) - 1))

    def construct_graph(self) -> DiGraph:
        graph = DiGraph()
        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i + 1]
            speed = self.max_speed[i]
            graph.add_edge(p1, p2, speed=speed)
        return graph

    def extend_ends(self, default_speed: int) -> None:
        self.points.insert(0, self.start_station.best_location())
        self.max_speed.insert(0, float(default_speed))
        self.points.append(self.end_station.best_location())
        self.max_speed.append(float(default_speed))

    def simplify_by_resampling(self, interval: int) -> None:  # interval in meters
        graph = self.construct_graph()
        current_point = self.points[0]
        while True:
            visited_points, interpolated_point = _find_point_at_distance(graph, current_point, interval)
            if not interpolated_point:  # We have reached the end
                break
            if len(visited_points) == 1:  # Interval is shorter than the next segment
                current_point = visited_points[0]
                continue

            speed = float("inf")
            speed_current_point = current_point
            edge_data = None
            for vp in visited_points:
                edge_data = graph.get_edge_data(speed_current_point, vp)
                assert edge_data is not None
                speed = min(speed, edge_data["speed"])
                speed_current_point = vp

            graph.remove_nodes_from(visited_points[:-1])
            graph.add_edge(current_point, interpolated_point, speed=speed)
            graph.add_edge(interpolated_point, visited_points[-1], speed=edge_data["speed"])  # type: ignore
            current_point = interpolated_point

        # Handle the last segment to the end point by merging
        last_point = self.points[-1]
        speed = float("inf")
        speed_current_point = last_point
        accumulated_distance = 0.0
        while True:
            predecessor = next(graph.predecessors(speed_current_point), None)
            if not predecessor:
                break
            edge_data = graph.get_edge_data(predecessor, speed_current_point)
            assert edge_data is not None
            speed = min(speed, edge_data["speed"])
            segment_distance = predecessor.distance_to(speed_current_point)
            accumulated_distance += segment_distance
            if accumulated_distance >= interval:
                break
            graph.remove_node(speed_current_point)
            speed_current_point = predecessor
        graph.add_edge(speed_current_point, last_point, speed=speed)

        # Remove cycles if any
        cycles = [(u, v) for u, v in graph.edges() if u == v]
        graph.remove_edges_from(cycles)

        # Reconstruct points and max_speed from the simplified graph
        new_points = [self.points[0]]
        new_max_speed = []
        while True:
            next_point = next(graph.successors(new_points[-1]), None)
            if not next_point:
                break
            edge_data = graph.get_edge_data(new_points[-1], next_point)
            assert edge_data is not None
            new_max_speed.append(edge_data["speed"])
            new_points.append(next_point)
        self.points = new_points
        self.max_speed = new_max_speed
        assert len(self.points) - 1 == len(self.max_speed)


@handlers.register(Rail)  # type: ignore
class RailHandler(handlers.BaseHandler):
    def flatten(self, obj, data):
        data["start_station"] = obj.start_station.name
        data["end_station"] = obj.end_station.name
        data["points"] = [p.__getstate__() for p in obj.points]
        data["max_speed"] = obj.max_speed
        return data


@dataclass(unsafe_hash=True)
class RoutingRule:
    start_station: str
    end_station: str
    via: list[str] = field(compare=False, hash=False, default_factory=list)

    def __post_init__(self):
        if self.start_station < self.end_station:
            return
        self.start_station, self.end_station = self.end_station, self.start_station
        self.via.reverse()
