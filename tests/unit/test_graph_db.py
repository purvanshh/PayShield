import pandas as pd
import pytest

from data.graph_builder import HeterogeneousGraphBuilder
from store.graph_db import GraphDB


class TestHeterogeneousGraphBuilder:
    def test_build_from_transactions(self):
        df = pd.DataFrame([
            {"txn_id": "T1", "user_id": "U1", "merchant_id": "M1",
             "device_fingerprint": "D1", "txn_type": "P2M", "amount": 100.0,
             "timestamp": "2026-07-01", "lat": 19.0, "lon": 72.0, "mcc_code": "food",
             "is_fraud": False, "fraud_type": None},
        ])
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df)
        g = builder.graph
        assert g.has_node("U1")
        assert g.has_node("M1")
        assert g.has_node("T1")
        assert g.has_node("D1")
        assert g.has_edge("U1", "T1")
        assert g.has_edge("T1", "M1")
        assert g.has_edge("U1", "D1")

    def test_node_types(self):
        df = pd.DataFrame([
            {"txn_id": "T1", "user_id": "U1", "merchant_id": "M1",
             "device_fingerprint": "D1", "txn_type": "P2M", "amount": 100.0,
             "timestamp": "2026-07-01", "lat": 19.0, "lon": 72.0, "mcc_code": "food",
             "is_fraud": False, "fraud_type": None},
        ])
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df)
        g = builder.graph
        assert g.nodes["U1"]["node_type"] == "user"
        assert g.nodes["M1"]["node_type"] == "merchant"
        assert g.nodes["T1"]["node_type"] == "transaction"
        assert g.nodes["D1"]["node_type"] == "device"

    def test_p2p_edges(self):
        df = pd.DataFrame([
            {"txn_id": "T1", "user_id": "U1", "merchant_id": "U2",
             "device_fingerprint": "D1", "txn_type": "P2P", "amount": 100.0,
             "timestamp": "2026-07-01", "lat": 19.0, "lon": 72.0, "mcc_code": "food",
             "is_fraud": False, "fraud_type": None},
        ])
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df)
        builder.add_p2p_edges(df)
        assert builder.graph.has_edge("U1", "U2", key=0)

    def test_pyg_data_conversion(self):
        df = pd.DataFrame([
            {"txn_id": "T1", "user_id": "U1", "merchant_id": "M1",
             "device_fingerprint": "D1", "txn_type": "P2M", "amount": 100.0,
             "timestamp": "2026-07-01", "lat": 19.0, "lon": 72.0, "mcc_code": "food",
             "is_fraud": False, "fraud_type": None},
        ])
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df)
        pyg = builder.to_pyg_data()
        assert hasattr(pyg, "node_types")
        assert "user" in pyg.node_types
        assert "merchant" in pyg.node_types

    def test_ego_graph_empty(self):
        db = GraphDB()
        ego = db.get_ego_graph("nonexistent")
        assert ego.number_of_nodes() == 0
