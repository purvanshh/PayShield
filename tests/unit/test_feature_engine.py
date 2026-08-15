"""Phase 7 unit tests: the extended 21d/8d feature vectors, the target-first
hydration order used by the live readout, and shape agreement with the model.
"""


import pytest
import torch


class TestFeatureWidths:
    def test_merchant_features_width_21(self):
        from engine.graph_feature_engine import MERCHANT_FEAT_DIM, _merchant_features
        assert MERCHANT_FEAT_DIM == 21
        feats = _merchant_features({"category_code": "food", "avg_txn_amount": 9000,
                                    "refund_rate": 0.1, "account_age_days": 750,
                                    "city_tier": 2, "is_shell": True,
                                    "round_amount_share": 0.6})
        assert len(feats) == 21
        assert feats[15] == pytest.approx(9000.0 / 10000.0)
        assert feats[-2] == 1.0          # is_shell
        assert feats[-1] == pytest.approx(0.6)  # round_amount_share

    def test_transaction_features_width_8(self):
        from engine.graph_feature_engine import TRANSACTION_FEAT_DIM, _transaction_features
        assert TRANSACTION_FEAT_DIM == 8
        feats = _transaction_features({
            "amount": 10000.0,
            "timestamp": "2026-08-01T12:30:00Z",
            "inter_arrival_gap_min": 30.0,
            "txn_count_5m": 4.0,
            "txn_count_1h": 15.0,
            "loc_dist_km": 200.0,
        })
        assert len(feats) == 8
        assert feats[0] == pytest.approx(10000.0 / 20000.0)
        assert feats[4] == pytest.approx(30.0 / 480.0)   # gap
        assert feats[5] == pytest.approx(4.0 / 10.0)     # 5m velocity
        assert feats[6] == pytest.approx(15.0 / 30.0)    # 1h velocity
        assert feats[7] == pytest.approx(200.0 / 800.0)  # location distance

    def test_feature_dim_constants_match_model_reference(self):
        from engine.graph_feature_engine import (
            DEVICE_FEAT_DIM,
            MERCHANT_FEAT_DIM,
            TRANSACTION_FEAT_DIM,
            USER_FEAT_DIM,
        )
        assert (USER_FEAT_DIM, MERCHANT_FEAT_DIM, DEVICE_FEAT_DIM, TRANSACTION_FEAT_DIM) == (5, 21, 4, 8)


class TestHaversine:
    def test_haversine_zero_distance(self):
        from engine.graph_feature_engine import haversine_km
        assert haversine_km(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    def test_haversine_known_distance(self):
        from engine.graph_feature_engine import haversine_km
        # Delhi (28.6139, 77.2090) -> Mumbai (19.0760, 72.8777): ~1150 km
        km = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)
        assert 1080 < km < 1250


def _ego_graph():
    import networkx as nx
    g = nx.MultiDiGraph()
    for n, t in [("u1", "user"), ("u2", "user"), ("m1", "merchant"),
                 ("d1", "device"), ("t1", "transaction"), ("t2", "transaction"),
                 ("t3", "transaction"), ("t4", "transaction")]:
        g.add_node(n, node_type=t)
    g.nodes["u1"]["credit_score"] = 810.0
    g.nodes["u2"]["credit_score"] = 540.0
    g.nodes["t1"].update(amount=1000.0, timestamp=2)
    g.nodes["t2"].update(amount=2000.0, timestamp=1)
    g.nodes["t3"].update(amount=9000.0, timestamp=10)
    g.nodes["t4"].update(amount=8000.0, timestamp=20)
    g.add_edge("u1", "t1", edge_type="performed")
    g.add_edge("u1", "t2", edge_type="performed")
    g.add_edge("u2", "t3", edge_type="performed")
    g.add_edge("u2", "t4", edge_type="performed")
    g.add_edge("t1", "m1", edge_type="at")
    g.add_edge("u1", "d1", edge_type="used")
    return g


class TestTargetFirstHydration:
    def test_default_hydration_has_no_target_metadata(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        data = GraphFeatureEngine(None).hydrate_features(_ego_graph(), None)
        assert not hasattr(data, "target_txn_n")

    def test_target_user_is_row_zero(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        g = _ego_graph()
        data = GraphFeatureEngine(None).hydrate_features(g, None, target_user_id="u1")
        user_tensor = data["user"].x
        # u1 (credit 810 -> 0.9) must be the first user row
        assert user_tensor[0, 0] == pytest.approx(810.0 / 900.0)
        assert data.target_txn_n == 2

    def test_target_transactions_lead_sorted_by_timestamp(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        g = _ego_graph()
        data = GraphFeatureEngine(None).hydrate_features(g, None, target_user_id="u1")
        txn_tensor = data["transaction"].x
        assert data.target_txn_n == 2
        amounts = [t[0] * 20000.0 for t in txn_tensor[:2]]
        # t2 (ts=1) first, then t1 (ts=2) — ascending timestamp
        assert amounts == pytest.approx([2000.0, 1000.0])
        # neighbour transactions come after the target's own
        assert txn_tensor[2, 0] * 20000.0 == pytest.approx(9000.0)

    def test_target_not_in_graph_no_metadata(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        g = _ego_graph()
        data = GraphFeatureEngine(None).hydrate_features(g, None, target_user_id="ghost")
        assert not hasattr(data, "target_txn_n")


class TestModelShapeContract:
    def test_hydrated_tensors_forward_through_serving_model(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        from engine.graph_model import PayShieldGNN

        g = _ego_graph()
        data = GraphFeatureEngine(None).hydrate_features(g, None, target_user_id="u1")
        assert data["user"].x.size(1) == 5
        assert data["merchant"].x.size(1) == 21
        assert data["device"].x.size(1) == 4
        assert data["transaction"].x.size(1) == 8

        model = PayShieldGNN(hidden_channels=16, num_layers=2, dropout=0.0)
        out = model(
            data.x_dict,
            data.edge_index_dict,
            target_user_idx=torch.tensor([0], dtype=torch.long),
            target_txn_starts=torch.tensor([0], dtype=torch.long),
            target_txn_n=torch.tensor([data.target_txn_n], dtype=torch.long),
        )
        assert out.shape == torch.Size([1])
        assert 0.0 <= out.item() <= 1.0

    def test_checkpoint_meta_drives_model_constructor(self, tmp_path):
        import torch

        from engine.graph_model import PayShieldGNN

        model = PayShieldGNN(hidden_channels=32, num_layers=2, dropout=0.1)
        torch.save({
            "state_dict": model.state_dict(),
            "hidden_channels": 32,
            "num_layers": 2,
            "dropout": 0.1,
        }, tmp_path / "ckpt.pt")
        loaded = PayShieldGNN.from_checkpoint(tmp_path / "ckpt.pt")
        assert loaded.hidden_channels == 32
        assert loaded.num_layers == 2
        assert loaded.dropout == 0.1
        # wrong-sized default must not silently produce a mismatched model
        del model


class TestLiveFeatureRecording:
    def test_build_from_live_transaction_stores_velocity_attrs(self):
        import networkx as nx

        from engine.graph_builder import LIVE_TXN_ATTRS, build_from_live_transaction
        g = nx.MultiDiGraph()
        build_from_live_transaction(g, {
            "txn_id": "T1", "user_id": "u1", "merchant_id": "m1",
            "device_fingerprint": "d1", "amount": 500.0, "timestamp": 1000,
            "txn_type": "P2M",
            "inter_arrival_gap_min": 12.0, "txn_count_5m": 3, "txn_count_1h": 9,
            "loc_dist_km": 55.0, "lat": 12.9, "lon": 77.5,
            "round_amount_share": 0.4,
        })
        txn_attrs = dict(g.nodes["T1"])
        for key in LIVE_TXN_ATTRS:
            assert key in txn_attrs
        assert txn_attrs["loc_dist_km"] == 55.0
        assert txn_attrs["lat"] == 12.9
        assert dict(g.nodes["m1"])["round_amount_share"] == 0.4

    def test_feature_cache_defaults_on_failure(self):
        class _BrokenRedis:
            async def hincrby(self, *_a, **_k):
                raise RuntimeError("down")

            async def hgetall(self, *_a, **_k):
                raise RuntimeError("down")

            async def get(self, *_a, **_k):
                raise RuntimeError("down")

            async def set(self, *_a, **_k):
                raise RuntimeError("down")

            async def pipeline(self, *_a, **_k):
                raise RuntimeError("down")

        import asyncio

        from store.feature_store import FeatureCache

        cache = FeatureCache(_BrokenRedis())
        assert asyncio.run(cache.merchant_round_share("m1")) == 0.0
        assert asyncio.run(cache.get_user_centroid("u1")) is None
