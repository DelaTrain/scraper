from networkx import Graph, shortest_path, NetworkXNoPath, NodeNotFound
from .utils import oneshot_cache
from .structures.paths import RoutingRule, Rail
from .structures.trains import Train

_MAX_PATH_LENGTH_MULTIPLIER = 3.5

RoutingErrors = dict[tuple[str, str], tuple[list[str], float] | None]


@oneshot_cache
def construct_rails_graph(rails: frozenset[Rail]) -> Graph:
    graph = Graph()
    for rail in rails:
        if not graph.has_node(rail.start_station.name):
            graph.add_node(rail.start_station.name, pos=rail.start_station.location)
        if not graph.has_node(rail.end_station.name):
            graph.add_node(rail.end_station.name, pos=rail.end_station.location)
        graph.add_edge(rail.start_station.name, rail.end_station.name, length=rail.length, rail=rail)
    return graph


def find_rule_for_path(graph: Graph, start: str, end: str) -> tuple[RoutingRule | None, RoutingErrors]:
    if graph.has_edge(start, end):
        graph[start][end]["rail"].redundant = False
        return None, {}
    try:
        path = shortest_path(graph, start, end, weight="length")
        path_length = sum(graph[path[j]][path[j + 1]]["length"] for j in range(len(path) - 1))
        direct_length = graph.nodes[start]["pos"].distance_to(graph.nodes[end]["pos"])
        via = path[1:-1]
        if path_length > direct_length * _MAX_PATH_LENGTH_MULTIPLIER:
            return None, {(start, end): (via, path_length / direct_length)}
        rule = RoutingRule(start, end, via)
        for j in range(len(path) - 1):
            graph[path[j]][path[j + 1]]["rail"].redundant = False
        return rule, {}
    except (NetworkXNoPath, NodeNotFound):
        return None, {(start, end): None}


def find_rules_for_train(graph: Graph, train: Train) -> tuple[list[RoutingRule], RoutingErrors]:
    rules = []
    errors = {}
    for i in range(len(train.stops) - 1):
        start = train.stops[i].station_name
        end = train.stops[i + 1].station_name
        rule, error = find_rule_for_path(graph, start, end)
        if rule is not None:
            rules.append(rule)
        errors |= error
    return rules, errors
