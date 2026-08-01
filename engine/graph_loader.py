import logging
from collections import defaultdict

import networkx as nx
import numpy as np
import torch

logger = logging.getLogger(__name__)

try:
    from torch_geometric.data import Batch, HeteroData
    _has_pyg = True
except ImportError:
    HeteroData = None
    Batch = None
    _has_pyg = False
    logger.warning("PyTorch Geometric not installed; HeteroGraphConverter will be a no-op")


NODE_FEATURE_DIMS = {
    "User": 5,
    "Merchant": 5,
    "Device": 3,
    "Transaction": 4,
}

EDGE_TYPES = [
    ("User", "performed", "Transaction"),
    ("Transaction", "to", "Merchant"),
    ("User", "used", "Device"),
    ("User", "transferred_to", "User"),
    ("Device", "shared_by", "User"),
]


def _extract_user_features(attr: dict) -> list[float]:
    return [
        float(attr.get("credit_score", 600)) / 1000.0,
        float(attr.get("account_age_days", 0)) / 365.0,
        float(attr.get("avg_monthly_txn_count", 0)) / 100.0,
        float(attr.get("device_count", 1)) / 10.0,
        float(attr.get("kyc_tier", 0)) / 3.0,
    ]


def _extract_merchant_features(attr: dict) -> list[float]:
    mcc = int(attr.get("category_code", 0)) % 15
    mcc_onehot = [1.0 if i == mcc else 0.0 for i in range(15)]
    base = [
        float(attr.get("avg_txn_amount", 0)) / 10000.0,
        float(attr.get("refund_rate", 0)),
        float(attr.get("account_age_days", 0)) / 365.0,
        float(attr.get("benford_chi2", 0)) / 100.0,
    ]
    return mcc_onehot[:4] + base[-1:]


def _extract_device_features(attr: dict) -> list[float]:
    return [
        1.0 if str(attr.get("os_family", "")).lower() == "android" else 0.0,
        float(attr.get("is_emulator", 0)),
        float(attr.get("first_seen_days", 0)) / 30.0,
    ]


def _extract_transaction_features(attr: dict) -> list[float]:
    return [
        float(attr.get("amount", 0)) / 10000.0,
        float(attr.get("timestamp_hour", 12)) / 23.0,
        float(attr.get("timestamp_day", 1)) / 7.0,
        float(attr.get("is_high_risk_merchant", 0)),
    ]


FEATURE_EXTRACTORS = {
    "User": _extract_user_features,
    "Merchant": _extract_merchant_features,
    "Device": _extract_device_features,
    "Transaction": _extract_transaction_features,
}

NODE_TYPE_LABELS = {
    "User": "User",
    "Merchant": "Merchant",
    "Device": "Device",
    "Transaction": "Transaction",
}


class HeteroGraphConverter:
    def __init__(self):
        if not _has_pyg:
            logger.warning("PyG not available; converter will not produce usable HeteroData")
        self.relabel_map = NODE_TYPE_LABELS

    def convert(self, graph: nx.Graph, target_user_id: str | None = None) -> "HeteroData":
        if not _has_pyg:
            raise ImportError("PyTorch Geometric is required for conversion")

        data = HeteroData()

        node_map: dict[str, dict[str, list[str]]] = {
            "User": [],
            "Merchant": [],
            "Device": [],
            "Transaction": [],
        }

        for nid, attr in graph.nodes(data=True):
            ntype = attr.get("node_type", "Transaction")
            if ntype in node_map:
                node_map[ntype].append(nid)

        for ntype, node_ids in node_map.items():
            extractor = FEATURE_EXTRACTORS.get(ntype)
            if not extractor or not node_ids:
                data[ntype].x = torch.zeros((len(node_ids), NODE_FEATURE_DIMS.get(ntype, 1)), dtype=torch.float32)
                continue
            features = [extractor(graph.nodes[nid]) for nid in node_ids]
            data[ntype].x = torch.tensor(np.array(features, dtype=np.float32))

        edge_dict: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        for u, v, attr in graph.edges(data=True):
            etype = attr.get("edge_type", "performed")
            for src_type, rel, dst_type in EDGE_TYPES:
                if etype == rel:
                    u_type = graph.nodes[u].get("node_type")
                    v_type = graph.nodes[v].get("node_type")
                    if u_type == src_type and v_type == dst_type:
                        edge_dict[(src_type, rel, dst_type)].append((u, v))
                    break

        for (src_type, rel, dst_type), edges in edge_dict.items():
            src_ids = node_map[src_type]
            dst_ids = node_map[dst_type]
            src_index = {nid: i for i, nid in enumerate(src_ids)}
            dst_index = {nid: i for i, nid in enumerate(dst_ids)}

            edge_index = []
            for u, v in edges:
                if u in src_index and v in dst_index:
                    edge_index.append([src_index[u], dst_index[v]])

            if edge_index:
                data[(src_type, rel, dst_type)].edge_index = (
                    torch.tensor(edge_index, dtype=torch.long).t().contiguous()
                )
            else:
                data[(src_type, rel, dst_type)].edge_index = torch.zeros((2, 0), dtype=torch.long)

        for src_type, rel, dst_type in EDGE_TYPES:
            if (src_type, rel, dst_type) not in edge_dict:
                data[(src_type, rel, dst_type)].edge_index = torch.zeros((2, 0), dtype=torch.long)

        if target_user_id and target_user_id in node_map.get("User", []):
            user_idx = node_map["User"].index(target_user_id)
            data["User"].target_node = torch.tensor([user_idx], dtype=torch.long)

        return data


class HeteroDataBatch:
    @staticmethod
    def batch(data_list: list) -> "Batch":
        if not _has_pyg:
            raise ImportError("PyTorch Geometric is required for batching")
        if not data_list:
            raise ValueError("Cannot batch empty list")
        if len(data_list) == 1:
            return data_list[0]
        return Batch.from_data_list(data_list)

    @staticmethod
    def batch_to_device(batch, device: str = "cpu"):
        return batch.to(device) if hasattr(batch, "to") else batch
