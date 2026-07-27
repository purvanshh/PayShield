import logging

import networkx as nx

logger = logging.getLogger(__name__)


class GraphDB:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_node(self, node_id: str, node_type: str, features: dict | None = None):
        attrs = {"node_type": node_type, **(features or {})}
        self.graph.add_node(node_id, **attrs)

    def add_edge(self, u: str, v: str, edge_type: str, **attrs):
        self.graph.add_edge(u, v, edge_type=edge_type, **attrs)

    def get_ego_graph(self, node_id: str, hops: int = 2) -> nx.MultiDiGraph:
        if not self.graph.has_node(node_id):
            return nx.MultiDiGraph()
        nodes = {node_id}
        current_frontier = {node_id}
        for _ in range(hops):
            next_frontier = set()
            for n in current_frontier:
                for neighbor in self.graph.predecessors(n):
                    if neighbor not in nodes:
                        next_frontier.add(neighbor)
                for neighbor in self.graph.successors(n):
                    if neighbor not in nodes:
                        next_frontier.add(neighbor)
            nodes.update(next_frontier)
            current_frontier = next_frontier
        return self.graph.subgraph(nodes).copy()

    def has_node(self, node_id: str) -> bool:
        return self.graph.has_node(node_id)

    def get_node_attributes(self, node_id: str) -> dict:
        return dict(self.graph.nodes[node_id]) if self.graph.has_node(node_id) else {}

    def get_neighbors(self, node_id: str, node_type: str | None = None) -> list[str]:
        if not self.graph.has_node(node_id):
            return []
        neighbors = list(self.graph.predecessors(node_id)) + list(self.graph.successors(node_id))
        if node_type:
            return [n for n in neighbors if self.graph.nodes[n].get("node_type") == node_type]
        return neighbors

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def clear(self):
        self.graph.clear()
