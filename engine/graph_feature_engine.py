import networkx as nx
import numpy as np
import torch
from torch_geometric.data import HeteroData

# Feature contracts shared with scripts/benchmark_gnn.py — the trained model
# was fit on exactly these vectors, so live hydration must reproduce them
# dimension-for-dimension. Missing attributes fall back to zeros.
MCC_ORDER = [
    "food", "travel", "utilities", "fashion", "groceries",
    "entertainment", "health", "education", "transport", "rent",
    "recharge", "insurance", "investment", "cashback", "other",
]


def _f(attr: dict, key: str, default: float = 0.0) -> float:
    val = attr.get(key, default)
    if isinstance(val, str):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _user_features(attr: dict) -> list[float]:
    return [
        _f(attr, "credit_score", 0.0) / 900.0,
        min(_f(attr, "account_age_days", 0.0) / 1200.0, 1.0),
        _f(attr, "kyc_tier", 0.0) / 3.0,
        min(_f(attr, "avg_monthly_txn_count", 0.0) / 100.0, 1.0),
        min(_f(attr, "device_count", 0.0) / 3.0, 1.0),
    ]


def _merchant_features(attr: dict) -> list[float]:
    mcc = str(attr.get("category_code", "")).lower()
    return [1.0 if c == mcc else 0.0 for c in MCC_ORDER] + [
        min(_f(attr, "avg_txn_amount", 0.0) / 10000.0, 1.0),
        min(_f(attr, "refund_rate", 0.0), 1.0),
        min(_f(attr, "account_age_days", 0.0) / 1500.0, 1.0),
        _f(attr, "city_tier", 0.0) / 4.0,
        1.0 if attr.get("is_shell") else 0.0,
        min(_f(attr, "round_amount_share", 0.0), 1.0),
    ]


def _device_features(attr: dict) -> list[float]:
    try:
        major, minor = (int(p) for p in str(attr.get("app_version", "0.0")).split(".")[:2])
    except ValueError:
        major, minor = 0, 0
    return [
        1.0 if attr.get("os_family") == "android" else 0.0,
        major / 8.0,
        minor / 9.0,
        1.0 if attr.get("is_emulator") else 0.0,
    ]


def _transaction_features(attr: dict) -> list[float]:
    amount = _f(attr, "amount", 0.0)
    gap = min(_f(attr, "inter_arrival_gap_min", 1440.0) / 480.0, 1.0)
    c5m = min(_f(attr, "txn_count_5m", 0.0) / 10.0, 1.0)
    c1h = min(_f(attr, "txn_count_1h", 0.0) / 30.0, 1.0)
    dist = min(_f(attr, "loc_dist_km", 0.0) / 800.0, 1.0)
    ts = attr.get("timestamp", 0.0)
    if isinstance(ts, (int, float)):
        import datetime as _dt
        ts = _dt.datetime.fromtimestamp(ts / 1000.0 if ts > 1e12 else ts)
    elif isinstance(ts, str):
        from datetime import datetime as _dt2
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                ts = _dt2.strptime(ts, fmt)
                break
            except ValueError:
                continue
        else:
            ts = None
    if ts is None or not hasattr(ts, "hour"):
        # No temporal context → neutral zeros for every derived feature
        return [min(amount / 20000.0, 1.0), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    return [
        min(amount / 20000.0, 1.0),
        ts.hour / 24.0,
        1.0 if ts.weekday() >= 5 else 0.0,
        1.0 if ts.day <= 2 else 0.0,
        gap,
        c5m,
        c1h,
        dist,
    ]


class GraphFeatureEngine:
    def __init__(self, graph_db):
        self.graph_db = graph_db

    def extract_ego_graph(self, user_id: str, merchant_id: str, hops: int = 2, device_id: str | None = None):
        seeds = [s for s in (user_id, merchant_id, device_id) if s and s != "UNKNOWN_DEVICE"]
        subgraph_nodes = set()
        for node_id in seeds:
            if not self.graph_db.graph.has_node(node_id):
                continue
            subgraph_nodes.add(node_id)
            current_hop = {node_id}
            for _ in range(hops):
                next_hop = set()
                for n in current_hop:
                    neighbors = set(self.graph_db.graph.predecessors(n)) | set(self.graph_db.graph.successors(n))
                    next_hop.update(neighbors)
                subgraph_nodes.update(next_hop)
                current_hop = next_hop

        subgraph = self.graph_db.graph.subgraph(subgraph_nodes).copy()
        return subgraph

    def hydrate_features(self, subgraph: nx.MultiDiGraph, feature_store) -> HeteroData:
        data = HeteroData()

        node_types = {"user": [], "merchant": [], "device": [], "transaction": []}
        for n, attr in subgraph.nodes(data=True):
            ntype = str(attr.get("node_type", "transaction")).lower().rstrip("s")
            if ntype in node_types:
                node_types[ntype].append(n)

        data["user"].x = self._build_node_tensor(subgraph, node_types["user"], _user_features, width=5)
        data["merchant"].x = self._build_node_tensor(subgraph, node_types["merchant"], _merchant_features, width=len(MCC_ORDER) + 6)
        data["device"].x = self._build_node_tensor(subgraph, node_types["device"], _device_features, width=4)
        data["transaction"].x = self._build_node_tensor(subgraph, node_types["transaction"], _transaction_features, width=8)

        edge_defs = {
            ("user", "performed", "transaction"): [],
            ("transaction", "to", "merchant"): [],
            ("user", "used", "device"): [],
            ("user", "transferred_to", "user"): [],
            ("device", "shared_by", "user"): [],
        }

        def _nt(n) -> str:
            return str(subgraph.nodes[n].get("node_type", "transaction")).lower().rstrip("s")

        performed = []
        for u, v, a in subgraph.edges(data=True):
            if a.get("edge_type") == "performed" and _nt(u) == "user" and _nt(v) == "transaction":
                performed.append((u, v))
        edge_defs[("user", "performed", "transaction")] = performed

        for u, v, a in subgraph.edges(data=True):
            if a.get("edge_type") == "at" and _nt(u) == "transaction" and _nt(v) == "merchant":
                edge_defs[("transaction", "to", "merchant")].append((u, v))

        used = []
        for u, v, a in subgraph.edges(data=True):
            if a.get("edge_type") != "used":
                continue
            if _nt(u) == "user" and _nt(v) == "device":
                used.append((u, v))
            elif _nt(u) == "transaction" and _nt(v) == "device":
                owner = [p for p, t in performed if t == u]
                if owner:
                    used.append((owner[0], v))
        edge_defs[("user", "used", "device")] = used

        sender: dict = {}
        receiver: dict = {}
        for u, v, a in subgraph.edges(data=True):
            if a.get("edge_type") != "transferred_to":
                continue
            if _nt(u) == "user" and _nt(v) == "transaction":
                sender[v] = u
            elif _nt(u) == "transaction" and _nt(v) == "user":
                receiver[u] = v
        edge_defs[("user", "transferred_to", "user")] = [
            (sender[t], receiver[t]) for t in sender.keys() & receiver.keys()
        ]

        for (src, rel, dst), edges in edge_defs.items():
            if not edges:
                data[(src, rel, dst)].edge_index = torch.zeros((2, 0), dtype=torch.long)
                continue
            src_nodes = node_types[src]
            dst_nodes = node_types[dst]
            src_map = {n: i for i, n in enumerate(src_nodes)}
            dst_map = {n: i for i, n in enumerate(dst_nodes)}
            edge_index = []
            for u, v in edges:
                if u in src_map and v in dst_map:
                    edge_index.append([src_map[u], dst_map[v]])
            if edge_index:
                data[(src, rel, dst)].edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()

        return data

    def _build_node_tensor(self, subgraph, nodes: list, feat_fn, width: int) -> torch.Tensor:
        if not nodes:
            return torch.zeros((0, width), dtype=torch.float32)
        feats = [feat_fn(subgraph.nodes[n]) for n in nodes]
        return torch.tensor(np.array(feats, dtype=np.float32)).reshape(len(nodes), width)


def extract_ego_graph_live(graph, user_id: str, merchant_id: str, device_id: str | None = None,
                           hops: int = 2, max_txns: int = 10):
    """Extract the ego graph around user/merchant/device from a live graph.

    Works with any graph exposing ``nodes(data=True)`` / ``edges(data=True)``
    (the shared NetworkX graph from app state). Returns an :class:`nx.Graph`
    which the caller must hydrate before GNN inference.

    The user's transaction neighbors are capped to the ``max_txns`` most
    recent ones — the model was trained on ego graphs with at most 10
    transactions, and larger live subgraphs would both skew the features
    and blow the L2 latency budget.
    """
    seeds = [s for s in (user_id, merchant_id, device_id) if s and s != "UNKNOWN_DEVICE"]
    subgraph_nodes = set()
    for node_id in seeds:
        if not graph.has_node(node_id):
            continue
        subgraph_nodes.add(node_id)
        frontier = {node_id}
        for _ in range(hops):
            next_frontier = set()
            for n in frontier:
                next_frontier.update(graph.neighbors(n))
            subgraph_nodes.update(next_frontier)
            frontier = next_frontier

    if user_id in subgraph_nodes and max_txns > 0:
        txns = [
            n for n in graph.neighbors(user_id)
            if str(graph.nodes[n].get("node_type", "transaction")).lower().rstrip("s") == "transaction"
        ]
        if len(txns) > max_txns:
            txns.sort(key=lambda n: graph.nodes[n].get("timestamp", 0), reverse=True)
            kept = set(txns[:max_txns])
            for t in txns[max_txns:]:
                subgraph_nodes.discard(t)

    return graph.subgraph(subgraph_nodes).copy()
