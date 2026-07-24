import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GraphFeatures:
    user_id: str
    degree_centrality: float = 0.0
    clustering_coefficient: float = 0.0
    pagerank: float = 0.0
    triangle_count: int = 0
    betweenness_centrality: float = 0.0
    eccentricity: float = 0.0
    community_count: int = 1
    avg_neighbor_degree: float = 0.0
    node_count: int = 0
    edge_count: int = 0

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "degree_centrality": self.degree_centrality,
            "clustering_coefficient": self.clustering_coefficient,
            "pagerank": self.pagerank,
            "triangle_count": self.triangle_count,
            "betweenness_centrality": self.betweenness_centrality,
            "eccentricity": self.eccentricity,
            "community_count": self.community_count,
            "avg_neighbor_degree": self.avg_neighbor_degree,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
        }


class EgoGraphExtractor:
    CACHE_PREFIX = "ego_graph"
    CACHE_TTL = 60

    def __init__(self, neo4j_client, redis_client):
        self.neo4j = neo4j_client
        self.redis = redis_client

    def _cache_key(self, user_id: str, merchant_id: str, hops: int) -> str:
        raw = f"{self.CACHE_PREFIX}:{user_id}:{merchant_id}:{hops}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def extract(self, user_id: str, merchant_id: str, hops: int = 2) -> nx.Graph:
        cache_key = self._cache_key(user_id, merchant_id, hops)
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.info(f"Ego-graph cache hit for {user_id}/{merchant_id}")
            return self._deserialize_graph(data)

        graph = nx.Graph()

        cypher = """
        MATCH path = (u:User {user_id: $user_id})-[:PERFORMED|AT|USES*1..$hops]-(related)
        UNWIND nodes(path) AS n
        RETURN DISTINCT
            CASE
                WHEN n:User THEN 'User'
                WHEN n:Merchant THEN 'Merchant'
                WHEN n:Device THEN 'Device'
                WHEN n:Transaction THEN 'Transaction'
            END AS node_type,
            CASE
                WHEN n:User THEN n.user_id
                WHEN n:Merchant THEN n.merchant_id
                WHEN n:Device THEN n.device_id
                WHEN n:Transaction THEN n.txn_id
            END AS node_id,
            properties(n) AS props
        LIMIT 500
        """
        nodes = await self.neo4j.run_query(cypher, {"user_id": user_id, "hops": hops})

        for record in nodes:
            ntype = record.get("node_type", "Transaction")
            nid = str(record.get("node_id", ""))
            props = record.get("props", {})
            if nid:
                graph.add_node(nid, node_type=ntype, **props)

        edge_cypher = """
        MATCH path = (u:User {user_id: $user_id})-[:PERFORMED|AT|USES*1..$hops]-(related)
        UNWIND relationships(path) AS r
        RETURN DISTINCT
            type(r) AS rel_type,
            startNode(r).user_id AS src_user,
            startNode(r).merchant_id AS src_merchant,
            startNode(r).device_id AS src_device,
            startNode(r).txn_id AS src_txn,
            endNode(r).user_id AS dst_user,
            endNode(r).merchant_id AS dst_merchant,
            endNode(r).device_id AS dst_device,
            endNode(r).txn_id AS dst_txn
        LIMIT 2000
        """
        edges = await self.neo4j.run_query(edge_cypher, {"user_id": user_id, "hops": hops})

        for record in edges:
            rel_type = record.get("rel_type", "PERFORMED").lower()
            src = str(record.get(f"src_{self._id_field(rel_type)}", ""))
            dst = str(record.get(f"dst_{self._id_field(rel_type)}", ""))

            for candidate in ["user_id", "merchant_id", "device_id", "txn_id"]:
                if not src:
                    src = str(record.get(f"src_{candidate}", ""))
                if not dst:
                    dst = str(record.get(f"dst_{candidate}", ""))

            if src and dst and src != dst:
                graph.add_edge(src, dst, edge_type=rel_type)

        if merchant_id and merchant_id != user_id:
            merchant_cypher = """
            MATCH path = (m:Merchant {merchant_id: $merchant_id})-[:AT|PERFORMED|USES*1..$hops]-(related)
            UNWIND nodes(path) AS n
            RETURN DISTINCT
                CASE
                    WHEN n:User THEN 'User'
                    WHEN n:Merchant THEN 'Merchant'
                    WHEN n:Device THEN 'Device'
                    WHEN n:Transaction THEN 'Transaction'
                END AS node_type,
                CASE
                    WHEN n:User THEN n.user_id
                    WHEN n:Merchant THEN n.merchant_id
                    WHEN n:Device THEN n.device_id
                    WHEN n:Transaction THEN n.txn_id
                END AS node_id,
                properties(n) AS props
            LIMIT 500
            """
            m_nodes = await self.neo4j.run_query(merchant_cypher, {"merchant_id": merchant_id, "hops": hops})
            for record in m_nodes:
                nid = str(record.get("node_id", ""))
                if nid and not graph.has_node(nid):
                    graph.add_node(nid, node_type=record.get("node_type", "Transaction"), **record.get("props", {}))

        data = self._serialize_graph(graph)
        await self.redis.set(cache_key, data, ttl=self.CACHE_TTL)
        logger.info(f"Ego-graph cached for {user_id}/{merchant_id} ({graph.number_of_nodes()} nodes)")

        return graph

    def _id_field(self, rel_type: str) -> str:
        mapping = {
            "performed": "user_id",
            "at": "merchant_id",
            "uses": "device_id",
            "used": "device_id",
            "transfer": "user_id",
            "transferred_to": "user_id",
            "shared_by": "user_id",
        }
        return mapping.get(rel_type, "user_id")

    def _serialize_graph(self, graph: nx.Graph) -> str:
        data = {
            "nodes": [
                {"id": n, "node_type": d.get("node_type", "unknown"),
                 **{k: v for k, v in d.items() if k != "node_type"}}
                for n, d in graph.nodes(data=True)
            ],
            "edges": [
                {"src": u, "dst": v, "edge_type": d.get("edge_type", "unknown")}
                for u, v, d in graph.edges(data=True)
            ],
        }
        return json.dumps(data)

    def _deserialize_graph(self, raw: str) -> nx.Graph:
        data = json.loads(raw)
        graph = nx.Graph()
        for nd in data.get("nodes", []):
            nid = nd.pop("id")
            ntype = nd.pop("node_type", "unknown")
            graph.add_node(nid, node_type=ntype, **nd)
        for ed in data.get("edges", []):
            graph.add_edge(ed["src"], ed["dst"], edge_type=ed.get("edge_type", "unknown"))
        return graph


class GraphFeatureExtractor:
    def extract_structural_features(self, graph: nx.Graph, user_id: str) -> GraphFeatures:
        features = GraphFeatures(user_id=user_id)
        features.node_count = graph.number_of_nodes()
        features.edge_count = graph.number_of_edges()

        if graph.number_of_nodes() == 0:
            return features

        if graph.has_node(user_id):
            features.degree_centrality = round(nx.degree_centrality(graph).get(user_id, 0.0), 6)
            features.pagerank = round(nx.pagerank(graph, alpha=0.85).get(user_id, 0.0), 6)
            features.betweenness_centrality = round(nx.betweenness_centrality(graph, k=min(50, graph.number_of_nodes())).get(user_id, 0.0), 6)

        subgraph = graph.subgraph(list(graph.nodes())[:500])
        features.clustering_coefficient = round(nx.average_clustering(subgraph), 6)

        try:
            triangles = nx.triangles(graph)
            features.triangle_count = int(triangles.get(user_id, 0))
        except Exception:
            features.triangle_count = 0

        try:
            components = list(nx.connected_components(graph))
            features.community_count = len(components)
        except nx.NetworkXNotImplemented:
            features.community_count = 1

        try:
            if graph.number_of_nodes() > 1 and nx.is_connected(graph):
                features.eccentricity = round(nx.eccentricity(graph).get(user_id, 0.0), 6)
        except Exception:
            features.eccentricity = 0.0

        if graph.has_node(user_id):
            neighbors = list(graph.neighbors(user_id))
            if neighbors:
                neighbor_degrees = [graph.degree(n) for n in neighbors]
                features.avg_neighbor_degree = round(float(np.mean(neighbor_degrees)), 6)

        return features


class GraphNormalizer:
    def __init__(self, feature_ranges: dict[str, tuple[float, float]] | None = None):
        self.feature_ranges = feature_ranges or {}

    def normalize(self, features: GraphFeatures) -> GraphFeatures:
        normalized = GraphFeatures(user_id=features.user_id)
        for field_name in ["degree_centrality", "clustering_coefficient", "pagerank",
                           "triangle_count", "betweenness_centrality", "eccentricity",
                           "community_count", "avg_neighbor_degree", "node_count", "edge_count"]:
            raw = getattr(features, field_name)
            rmin, rmax = self.feature_ranges.get(field_name, (0.0, 1.0))
            if rmax > rmin:
                setattr(normalized, field_name, round((raw - rmin) / (rmax - rmin), 6))
            else:
                setattr(normalized, field_name, 0.0)
        return normalized
