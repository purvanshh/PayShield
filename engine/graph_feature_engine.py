import networkx as nx
import numpy as np
import torch
from torch_geometric.data import HeteroData


class GraphFeatureEngine:
    def __init__(self, graph_db):
        self.graph_db = graph_db

    def extract_ego_graph(self, user_id: str, merchant_id: str, hops: int = 2):
        subgraph_nodes = set()
        for node_id in [user_id, merchant_id]:
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
            ntype = attr.get("node_type", "transaction")
            if ntype in node_types:
                node_types[ntype].append(n)

        data["user"].x = self._build_node_tensor(subgraph, node_types["user"], ["credit_score", "account_age_days", "avg_monthly_txn_count", "device_count"])
        data["merchant"].x = self._build_node_tensor(subgraph, node_types["merchant"], ["category_code", "avg_txn_amount", "refund_rate", "account_age_days", "benford_chi2"])
        data["device"].x = self._build_node_tensor(subgraph, node_types["device"], ["os_family", "app_version", "is_emulator"])
        data["transaction"].x = self._build_node_tensor(subgraph, node_types["transaction"], ["amount", "timestamp"])

        edge_defs = {
            ("user", "performed", "transaction"): [],
            ("transaction", "to", "merchant"): [],
            ("user", "used", "device"): [],
            ("user", "transfer", "user"): [],
            ("device", "shared_by", "user"): [],
        }

        for u, v, attr in subgraph.edges(data=True):
            etype = attr.get("edge_type", "performed")
            for key in edge_defs:
                if etype == key[1]:
                    u_type = subgraph.nodes[u].get("node_type")
                    v_type = subgraph.nodes[v].get("node_type")
                    if u_type == key[0] and v_type == key[2]:
                        edge_defs[key].append((u, v))

        for (src, rel, dst), edges in edge_defs.items():
            if not edges:
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

    def _build_node_tensor(self, subgraph, nodes: list, feat_names: list[str]) -> torch.Tensor:
        if not nodes:
            return torch.zeros((0, len(feat_names)), dtype=torch.float32)
        feats = []
        for n in nodes:
            attr = subgraph.nodes[n]
            row = []
            for fname in feat_names:
                val = attr.get(fname, 0.0)
                if isinstance(val, str):
                    val = float(abs(hash(val)) % 1000) / 1000.0
                elif isinstance(val, bool):
                    val = 1.0 if val else 0.0
                row.append(float(val))
            feats.append(row)
        return torch.tensor(np.array(feats, dtype=np.float32))
