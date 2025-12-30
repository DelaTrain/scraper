from networkx import Graph, shortest_path, NetworkXNoPath, NodeNotFound
from .utils import oneshot_cache
from .structures.paths import RoutingRule, Rail
from .structures.trains import Train

_MAX_PATH_LENGTH_MULTIPLIER = 3.0


@oneshot_cache
def construct_rails_graph(rails: frozenset[Rail]) -> Graph:
    graph = Graph()
    for rail in rails:
        if not graph.has_node(rail.start_station.name):
            graph.add_node(rail.start_station.name, pos=rail.start_station.location)
        if not graph.has_node(rail.end_station.name):
            graph.add_node(rail.end_station.name, pos=rail.end_station.location)
        graph.add_edge(rail.start_station.name, rail.end_station.name, length=rail.length)
    return graph


def find_rules_for_train(graph: Graph, train: Train) -> list[RoutingRule]:
    rules = []
    for i in range(len(train.stops) - 1):
        start = train.stops[i].station_name
        end = train.stops[i + 1].station_name
        if graph.has_edge(start, end):
            continue
        try:
            path = shortest_path(graph, start, end, weight="length")
            path_length = sum(graph[path[j]][path[j + 1]]["length"] for j in range(len(path) - 1))
            direct_length = graph.nodes[start]["pos"].distance_to(graph.nodes[end]["pos"])
            if path_length > direct_length * _MAX_PATH_LENGTH_MULTIPLIER:
                continue
            via = path[1:-1]
            rules.append(RoutingRule(start, end, via))
        except (NetworkXNoPath, NodeNotFound):
            continue
    return rules
