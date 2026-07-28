import logging
from typing import Any, Optional

import networkx as nx

logger = logging.getLogger(__name__)


class NetworkXGraphDB:
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

    def find_risk_paths(self, source_id: str, target_id: str, max_hops: int = 4) -> list[dict]:
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return []
        try:
            paths = []
            for path in nx.all_simple_paths(self.graph, source_id, target_id, cutoff=max_hops):
                risk = self._calculate_path_risk(path)
                paths.append({"nodes": path, "length": len(path) - 1, "risk_score": risk})
            paths.sort(key=lambda p: p["risk_score"], reverse=True)
            return paths[:10]
        except nx.NetworkXNoPath:
            return []

    def get_network_score(self, entity_id: str) -> dict[str, Any]:
        ego = self.get_ego_graph(entity_id, hops=2)
        if ego.number_of_nodes() == 0:
            return {"entity_id": entity_id, "network_score": 0.0, "connected_entities": 0, "risk_clusters": 0}

        risk_score = 0.0
        for node in ego.nodes():
            attrs = self.get_node_attributes(node)
            if attrs.get("is_fraud", False):
                risk_score += 1.0
            if attrs.get("risk_score", 0.0) > 0:
                risk_score += attrs.get("risk_score", 0.0) * 0.5

        connected = ego.number_of_nodes() - 1
        risk_score = min(1.0, risk_score / max(connected, 1))

        return {
            "entity_id": entity_id,
            "network_score": round(risk_score, 4),
            "connected_entities": connected,
            "risk_clusters": len([n for n in ego.nodes() if ego.nodes[n].get("is_fraud", False)]),
        }

    def create_entity(self, entity_id: str, entity_type: str, features: dict | None = None):
        self.add_node(entity_id, entity_type, features)
        logger.info(f"Entity created: {entity_id} ({entity_type})")

    def link_entities(self, source_id: str, target_id: str, relation_type: str, features: dict | None = None):
        self.add_edge(source_id, target_id, relation_type, **(features or {}))
        logger.info(f"Entities linked: {source_id} -[{relation_type}]-> {target_id}")

    def _calculate_path_risk(self, path: list[str]) -> float:
        risk = 0.0
        for node_id in path:
            attrs = self.get_node_attributes(node_id)
            risk += attrs.get("risk_score", 0.0)
            if attrs.get("is_fraud", False):
                risk += 0.5
        return min(1.0, risk / max(len(path), 1))

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def clear(self):
        self.graph.clear()

    def close(self):
        pass


GraphDB = NetworkXGraphDB
