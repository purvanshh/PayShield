import hashlib
import json
import logging
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd
import torch
from torch_geometric.data import HeteroData

logger = logging.getLogger(__name__)

# Input widths of the trained GNN — kept in lockstep with
# engine/graph_feature_engine and the checkpoint (merchant 21d, txn 8d).
USER_FEAT_DIM = 5
MERCHANT_FEAT_DIM = 21
DEVICE_FEAT_DIM = 4
TRANSACTION_FEAT_DIM = 8

# Extra transaction attributes that the feature engine maps into velocity /
# geo features; the writer stores these on the transaction node at write time.
LIVE_TXN_ATTRS = ("inter_arrival_gap_min", "txn_count_5m", "txn_count_1h", "loc_dist_km")


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


def build_from_live_transaction(
    graph: nx.Graph, txn: dict, features: dict | None = None
) -> nx.Graph:
    """Incrementally add a live transaction to an in-memory NetworkX graph.

    Mirrors the Neo4j write primitives so both backends converge on the same
    state. `txn` is a dict with txn_id/user_id/merchant_id/amount/timestamp/
    device_fingerprint/txn_type and optionally counterparty_user_id.
    """
    txn_id = str(txn.get("txn_id", ""))
    user_id = str(txn.get("user_id", ""))
    merchant_id = str(txn.get("merchant_id", ""))
    device_id = str(txn.get("device_fingerprint") or "UNKNOWN_DEVICE")
    amount = float(txn.get("amount", 0.0))
    timestamp = txn.get("timestamp")

    if not graph.has_node(txn_id):
        txn_attrs = {k: txn[k] for k in LIVE_TXN_ATTRS if k in txn}
        if "lat" in txn and "lon" in txn:
            txn_attrs["lat"], txn_attrs["lon"] = txn["lat"], txn["lon"]
        graph.add_node(
            txn_id,
            node_type="Transaction",
            amount=amount,
            timestamp=str(timestamp or ""),
            **txn_attrs,
        )
    if user_id and not graph.has_node(user_id):
        graph.add_node(user_id, node_type="User", user_id=user_id)
    if merchant_id and not graph.has_node(merchant_id):
        merchant_attrs = {"merchant_id": merchant_id}
        if "round_amount_share" in txn:
            merchant_attrs["round_amount_share"] = txn["round_amount_share"]
        graph.add_node(merchant_id, node_type="Merchant", **merchant_attrs)
    elif merchant_id and "round_amount_share" in txn:
        graph.nodes[merchant_id]["round_amount_share"] = txn["round_amount_share"]
    if device_id != "UNKNOWN_DEVICE" and not graph.has_node(device_id):
        graph.add_node(device_id, node_type="Device", device_id=device_id)

    if user_id and not graph.has_edge(user_id, txn_id):
        graph.add_edge(user_id, txn_id, edge_type="performed")
    if merchant_id and not graph.has_edge(txn_id, merchant_id):
        graph.add_edge(txn_id, merchant_id, edge_type="at")
    if device_id != "UNKNOWN_DEVICE" and not graph.has_edge(txn_id, device_id):
        graph.add_edge(txn_id, device_id, edge_type="used")

    counterparty = txn.get("counterparty_user_id")
    if txn.get("txn_type") == "P2P" and counterparty:
        if not graph.has_node(counterparty):
            graph.add_node(counterparty, node_type="User", user_id=counterparty)
        if not graph.has_edge(user_id, txn_id):
            graph.add_edge(user_id, txn_id, edge_type="transferred_to")
        if not graph.has_edge(txn_id, counterparty):
            graph.add_edge(txn_id, counterparty, edge_type="transferred_to")

    return graph


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
            m_nodes = await self.neo4j.run_query(
                merchant_cypher, {"merchant_id": merchant_id, "hops": hops}
            )
            for record in m_nodes:
                nid = str(record.get("node_id", ""))
                if nid and not graph.has_node(nid):
                    graph.add_node(
                        nid,
                        node_type=record.get("node_type", "Transaction"),
                        **record.get("props", {}),
                    )

        data = self._serialize_graph(graph)
        await self.redis.set(cache_key, data, ttl=self.CACHE_TTL)
        logger.info(
            f"Ego-graph cached for {user_id}/{merchant_id} ({graph.number_of_nodes()} nodes)"
        )

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
                {
                    "id": n,
                    "node_type": d.get("node_type", "unknown"),
                    **{k: v for k, v in d.items() if k != "node_type"},
                }
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


class HeterogeneousGraphBuilder:
    """Build heterogeneous graphs from transaction DataFrames for batch PyG training.

    Mirrors the live graph structure: User/Transaction/Merchant/Device nodes with
    performed/to/used/transfer/shared_by edges. Converts to PyG HeteroData with
    feature tensors matching the trained model's input dimensions.
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def build_from_transactions(
        self,
        df: pd.DataFrame,
        users: dict | None = None,
        merchants: dict | None = None,
        devices: dict | None = None,
    ):
        users = users or {}
        merchants = merchants or {}
        devices = devices or {}

        for _, row in df.iterrows():
            uid = row["user_id"]
            mid = row["merchant_id"]
            did = row["device_fingerprint"]
            txn_id = row["txn_id"]

            self.graph.add_node(uid, node_type="user")
            self.graph.add_node(mid, node_type="merchant")
            self.graph.add_node(txn_id, node_type="transaction")

            if did not in self.graph:
                dev_info = devices.get(did, {})
                self.graph.add_node(
                    did,
                    node_type="device",
                    os_family=dev_info.get("os_family", "unknown"),
                    app_version=dev_info.get("app_version", "0.0.0"),
                    is_emulator=dev_info.get("is_emulator", False),
                    first_seen_timestamp=str(dev_info.get("first_seen_timestamp", "")),
                )

            user_info = users.get(uid, {})
            if uid not in self.graph:
                self.graph.add_node(
                    uid,
                    node_type="user",
                    credit_score=user_info.get("credit_score", 700),
                    account_age_days=user_info.get("account_age_days", 365),
                    kyc_tier=user_info.get("kyc_tier", "KYC2"),
                    avg_monthly_txn_count=user_info.get("avg_monthly_txn_count", 20),
                    device_count=user_info.get("device_count", 1),
                )

            merchant_info = merchants.get(mid, {})
            if mid not in self.graph:
                self.graph.add_node(
                    mid,
                    node_type="merchant",
                    category_code=merchant_info.get("category_code", "other"),
                    avg_txn_amount=merchant_info.get("avg_txn_amount", 500),
                    refund_rate=merchant_info.get("refund_rate", 0.02),
                    account_age_days=merchant_info.get("account_age_days", 365),
                    benford_chi2=merchant_info.get("benford_chi2", 0.0),
                )

            self.graph.add_edge(uid, txn_id, edge_type="performed")
            self.graph.add_edge(txn_id, mid, edge_type="to")
            self.graph.add_edge(uid, did, edge_type="used")

    def add_p2p_edges(self, df: pd.DataFrame):
        p2p = df[df["txn_type"] == "P2P"]
        for _, row in p2p.iterrows():
            sender = row["user_id"]
            receiver = row["merchant_id"]
            if self.graph.has_node(sender) and self.graph.has_node(receiver):
                self.graph.add_edge(sender, receiver, edge_type="transfer")

    def add_device_sharing_edges(self, window_hours: int = 24):
        device_users: dict[str, list[tuple[str, float]]] = {}
        for n, data in self.graph.nodes(data=True):
            if data.get("node_type") == "device":
                for u, v, ed in self.graph.edges(n, data=True):
                    if ed.get("edge_type") == "used":
                        uid = v if self.graph.nodes[v].get("node_type") == "user" else u
                        device_users.setdefault(n, []).append(uid)

        for dev, uids in device_users.items():
            if len(uids) > 1:
                for i in range(len(uids)):
                    for j in range(i + 1, len(uids)):
                        self.graph.add_edge(uids[i], uids[j], edge_type="shared_by")

    def to_pyg_data(self) -> HeteroData:
        data = HeteroData()

        node_types = {"user": [], "merchant": [], "device": [], "transaction": []}
        for n, attr in self.graph.nodes(data=True):
            ntype = attr.get("node_type", "transaction")
            if ntype in node_types:
                node_types[ntype].append(n)

        user_feats = self._collect_features(
            node_types["user"],
            ["credit_score", "account_age_days", "avg_monthly_txn_count", "device_count"],
        )
        merchant_feats = self._collect_features(
            node_types["merchant"],
            ["category_code", "avg_txn_amount", "refund_rate", "account_age_days", "benford_chi2"],
        )
        device_feats = self._collect_features(
            node_types["device"], ["os_family", "app_version", "is_emulator"]
        )

        data["user"].x = torch.tensor(np.array(user_feats, dtype=np.float32))
        data["merchant"].x = torch.tensor(np.array(merchant_feats, dtype=np.float32))
        data["device"].x = torch.tensor(np.array(device_feats, dtype=np.float32))

        edge_defs = {
            ("user", "performed", "transaction"): [],
            ("transaction", "to", "merchant"): [],
            ("user", "used", "device"): [],
            ("user", "transfer", "user"): [],
            ("device", "shared_by", "user"): [],
        }

        for u, v, attr in self.graph.edges(data=True):
            etype = attr.get("edge_type", "performed")
            for key in edge_defs:
                if (
                    etype == key[1]
                    and self.graph.nodes[u].get("node_type") == key[0]
                    and self.graph.nodes[v].get("node_type") == key[2]
                ):
                    edge_defs[key].append((u, v))

        for (src, rel, dst), edges in edge_defs.items():
            if not edges:
                continue
            src_map = {n: i for i, n in enumerate(node_types[src])}
            dst_map = {n: i for i, n in enumerate(node_types[dst])}
            edge_index = []
            for u, v in edges:
                if u in src_map and v in dst_map:
                    edge_index.append([src_map[u], dst_map[v]])
            if edge_index:
                data[(src, rel, dst)].edge_index = (
                    torch.tensor(edge_index, dtype=torch.long).t().contiguous()
                )

        return data

    def _collect_features(self, nodes: list, feat_names: list[str]) -> list[list[float]]:
        features = []
        for n in nodes:
            attr = self.graph.nodes[n]
            feats = []
            for fname in feat_names:
                val = attr.get(fname, 0)
                if isinstance(val, str):
                    val = hash(val) % 1000 / 1000.0
                feats.append(float(val))
            features.append(feats)
        return features

        if graph.has_node(user_id):
            features.degree_centrality = round(nx.degree_centrality(graph).get(user_id, 0.0), 6)
            features.pagerank = round(nx.pagerank(graph, alpha=0.85).get(user_id, 0.0), 6)
            features.betweenness_centrality = round(
                nx.betweenness_centrality(graph, k=min(50, graph.number_of_nodes())).get(
                    user_id, 0.0
                ),
                6,
            )

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
        for field_name in [
            "degree_centrality",
            "clustering_coefficient",
            "pagerank",
            "triangle_count",
            "betweenness_centrality",
            "eccentricity",
            "community_count",
            "avg_neighbor_degree",
            "node_count",
            "edge_count",
        ]:
            raw = getattr(features, field_name)
            rmin, rmax = self.feature_ranges.get(field_name, (0.0, 1.0))
            if rmax > rmin:
                setattr(normalized, field_name, round((raw - rmin) / (rmax - rmin), 6))
            else:
                setattr(normalized, field_name, 0.0)
        return normalized


@dataclass
class FraudGraphFeatures:
    user_id: str
    cycle_count: int = 0
    cycle_total_amount: float = 0.0
    merchant_concentration_ratio: float = 0.0
    device_sharing_depth: int = 0
    temporal_edge_density_24h: float = 0.0
    mutual_partner_count: int = 0
    shell_merchant_neighbor_count: int = 0
    avg_cycle_length: float = 0.0

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "cycle_count": self.cycle_count,
            "cycle_total_amount": self.cycle_total_amount,
            "merchant_concentration_ratio": self.merchant_concentration_ratio,
            "device_sharing_depth": self.device_sharing_depth,
            "temporal_edge_density_24h": self.temporal_edge_density_24h,
            "mutual_partner_count": self.mutual_partner_count,
            "shell_merchant_neighbor_count": self.shell_merchant_neighbor_count,
            "avg_cycle_length": self.avg_cycle_length,
        }


class FraudGraphFeatureExtractor:
    def extract_money_flow_cycles(self, graph: nx.Graph, user_id: str) -> list[list[str]]:
        try:
            all_cycles = list(nx.simple_cycles(graph.to_directed()))
        except Exception:
            return []

        user_cycles = []
        for cycle in all_cycles:
            if user_id in cycle and 2 < len(cycle) <= 5:
                user_cycles.append(cycle)

        return user_cycles

    def extract_merchant_concentration(self, graph: nx.Graph, user_id: str) -> float:
        merchant_txns: dict[str, int] = {}
        for u, v, d in graph.edges(data=True):
            edge_type = d.get("edge_type", "")
            if (u == user_id and edge_type == "performed") or (v == user_id):
                ntype = graph.nodes[v].get("node_type", "")
                if ntype == "Merchant":
                    merchant_txns[v] = merchant_txns.get(v, 0) + 1

        if not merchant_txns:
            return 0.0

        total = sum(merchant_txns.values())
        top = max(merchant_txns.values())
        return round(top / total, 4) if total > 0 else 0.0

    def extract_device_sharing_depth(self, graph: nx.Graph, user_id: str) -> int:
        if not graph.has_node(user_id):
            return 0

        visited = {user_id}
        queue = [(user_id, 0)]
        max_depth = 0

        while queue:
            current, depth = queue.pop(0)
            ntype = graph.nodes[current].get("node_type", "")

            if ntype == "Device" and depth > 0:
                device_users = [
                    n for n in graph.neighbors(current) if graph.nodes[n].get("node_type") == "User"
                ]
                if len(device_users) > 1:
                    max_depth = max(max_depth, depth)

            for neighbor in graph.neighbors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        return max_depth

    def extract_temporal_edge_density(self, graph: nx.Graph, window_hours: int = 24) -> float:
        n = graph.number_of_nodes()
        if n < 2:
            return 0.0

        max_possible = n * (n - 1) / 2
        if max_possible == 0:
            return 0.0

        return round(graph.number_of_edges() / max_possible, 6)

    def extract_mutual_transaction_partners(
        self, graph: nx.Graph, user_id_a: str, user_id_b: str
    ) -> int:
        def get_merchants(user_id: str) -> set[str]:
            merchants = set()
            for neighbor in graph.neighbors(user_id):
                if graph.nodes[neighbor].get("node_type") == "Merchant":
                    merchants.add(neighbor)
            return merchants

        merchants_a = get_merchants(user_id_a)
        merchants_b = get_merchants(user_id_b)
        return len(merchants_a & merchants_b)

    def extract_all(self, graph: nx.Graph, user_id: str) -> FraudGraphFeatures:
        features = FraudGraphFeatures(user_id=user_id)

        cycles = self.extract_money_flow_cycles(graph, user_id)
        features.cycle_count = len(cycles)
        if cycles:
            features.avg_cycle_length = round(float(np.mean([len(c) for c in cycles])), 2)

        features.merchant_concentration_ratio = self.extract_merchant_concentration(graph, user_id)
        features.device_sharing_depth = self.extract_device_sharing_depth(graph, user_id)
        features.temporal_edge_density_24h = self.extract_temporal_edge_density(graph)

        if features.cycle_count > 0:
            features.cycle_total_amount = features.cycle_count * 100.0

        return features
