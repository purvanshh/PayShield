import hashlib

import networkx as nx
import numpy as np
import pandas as pd
import torch
from torch_geometric.data import HeteroData


class HeterogeneousGraphBuilder:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def build_from_transactions(self, df: pd.DataFrame, users: dict | None = None, merchants: dict | None = None, devices: dict | None = None):
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

        user_feats = self._collect_features(node_types["user"], ["credit_score", "account_age_days", "avg_monthly_txn_count", "device_count"])
        merchant_feats = self._collect_features(node_types["merchant"], ["category_code", "avg_txn_amount", "refund_rate", "account_age_days", "benford_chi2"])
        device_feats = self._collect_features(node_types["device"], ["os_family", "app_version", "is_emulator"])

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
                if etype == key[1] and self.graph.nodes[u].get("node_type") == key[0] and self.graph.nodes[v].get("node_type") == key[2]:
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
                data[(src, rel, dst)].edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()

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
