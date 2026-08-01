import pytest
import torch

from engine.explainer import GNNExplainerWrapper, SHAPBridge
from engine.graph_feature_engine import GraphFeatureEngine
from engine.graph_model import PayShieldGNN


class TestPayShieldGNN:
    def test_model_forward(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        x_dict = {
            "user": torch.randn(5, 4),
            "merchant": torch.randn(3, 5),
            "device": torch.randn(4, 3),
            "transaction": torch.randn(2, 2),
        }
        edge_index_dict = {
            ("user", "performed", "transaction"): torch.tensor([[0, 1, 2], [0, 0, 1]], dtype=torch.long),
            ("transaction", "to", "merchant"): torch.tensor([[0, 1], [0, 1]], dtype=torch.long),
            ("user", "used", "device"): torch.tensor([[0, 1], [0, 1]], dtype=torch.long),
        }
        out = model(x_dict, edge_index_dict)
        assert out.shape == torch.Size([1])
        assert (out >= 0).all() and (out <= 1).all()

    def test_model_no_transactions(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        x_dict = {
            "user": torch.randn(3, 4),
            "merchant": torch.randn(2, 5),
            "device": torch.randn(1, 3),
            "transaction": torch.randn(0, 2),
        }
        edge_index_dict = {
            ("user", "performed", "transaction"): torch.zeros((2, 0), dtype=torch.long),
            ("transaction", "to", "merchant"): torch.zeros((2, 0), dtype=torch.long),
        }
        out = model(x_dict, edge_index_dict)
        assert out is not None

    def test_model_no_users(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        x_dict = {
            "user": torch.randn(0, 4),
            "merchant": torch.randn(2, 5),
            "device": torch.randn(0, 3),
            "transaction": torch.randn(2, 2),
        }
        edge_index_dict = {}
        out = model(x_dict, edge_index_dict)
        assert out is not None


class TestGNNExplainer:
    def test_explain_returns_dict(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        explainer = GNNExplainerWrapper(model)
        x_dict = {
            "user": torch.randn(3, 4),
            "merchant": torch.randn(2, 5),
            "device": torch.randn(1, 3),
            "transaction": torch.randn(2, 2),
        }
        edge_index_dict = {
            ("user", "performed", "transaction"): torch.tensor([[0, 1], [0, 1]], dtype=torch.long),
        }
        result = explainer.explain(x_dict, edge_index_dict)
        assert "fraud_probability" in result
        assert "node_contributions" in result
        assert "evidence_subgraph" in result
        assert 0 <= result["fraud_probability"] <= 1


class TestSHAPBridge:
    def test_compute_importances(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        bridge = SHAPBridge(model)
        tab = torch.randn(1, 4)
        result = bridge.compute_importances(tab)
        assert "shap_values" in result
        assert "top_features" in result
        assert len(result["shap_values"]) == 4


class TestGraphFeatureEngine:
    def test_build_node_tensor_empty(self):
        import networkx as nx
        engine = GraphFeatureEngine(None)
        subgraph = nx.MultiDiGraph()
        tensor = engine._build_node_tensor(subgraph, [], lambda _a: [1.0], width=1)
        assert tensor.shape == (0, 1)

    def test_build_node_tensor_with_data(self):
        import networkx as nx

        from engine.graph_feature_engine import _user_features
        engine = GraphFeatureEngine(None)
        subgraph = nx.MultiDiGraph()
        subgraph.add_node("n1", node_type="user", credit_score=750, account_age_days=365)
        subgraph.add_node("n2", node_type="user", credit_score=600, account_age_days=100)
        tensor = engine._build_node_tensor(subgraph, ["n1", "n2"], _user_features, width=5)
        assert tensor.shape == (2, 5)


class TestFeatureHelpers:
    def test_f_handles_scalar_types(self):
        from engine.graph_feature_engine import _f
        assert _f({"k": "3.5"}, "k") == 3.5
        assert _f({"k": "bad"}, "k") == 0.0
        assert _f({"k": True}, "k") == 1.0
        assert _f({"k": False}, "k") == 0.0
        assert _f({"k": 7}, "k") == 7.0
        assert _f({}, "k") == 0.0

    def test_device_features_tolerates_bad_version(self):
        from engine.graph_feature_engine import _device_features
        feats = _device_features({"app_version": "garbage", "os_family": "android"})
        assert feats[0] == 1.0
        assert feats[1] == 0.0
        assert feats[2] == 0.0

    def test_transaction_features_string_timestamps(self):
        from engine.graph_feature_engine import _transaction_features
        feats = _transaction_features({"amount": 500.0, "timestamp": "2026-08-01T12:30:00Z"})
        assert feats[1] == pytest.approx(12 / 24.0)
        feats = _transaction_features({"amount": 500.0, "timestamp": "2026-08-02 09:00:00"})
        assert feats[1] == pytest.approx(9 / 24.0)
        feats = _transaction_features({"amount": 500.0, "timestamp": "not-a-date"})
        assert feats[1:] == [0.0, 0.0, 0.0]
        feats = _transaction_features({"amount": 500.0, "timestamp": 1760000000.0})
        assert feats[0] == pytest.approx(500.0 / 20000.0)


class TestGraphFeatureHydration:
    def _graph(self):
        import networkx as nx
        g = nx.MultiDiGraph()
        for n, t in [("u1", "user"), ("u2", "user"), ("m1", "merchant"), ("d1", "device"),
                     ("t1", "transaction"), ("t2", "transaction"), ("t3", "transaction")]:
            g.add_node(n, node_type=t)
        return g

    def test_hydrate_all_edge_types(self):
        from engine.graph_feature_engine import GraphFeatureEngine
        g = self._graph()
        g.add_edge("u1", "t1", edge_type="performed")
        g.add_edge("u1", "t2", edge_type="performed")
        g.add_edge("t1", "m1", edge_type="at")
        g.add_edge("u1", "d1", edge_type="used")
        g.add_edge("t2", "d1", edge_type="used")
        g.add_edge("u1", "t3", edge_type="transferred_to")
        g.add_edge("t3", "u2", edge_type="transferred_to")
        data = GraphFeatureEngine(None).hydrate_features(g, None)
        used = data[("user", "used", "device")].edge_index
        assert used.shape == (2, 2)
        trans = data[("user", "transferred_to", "user")].edge_index
        assert trans.shape == (2, 1)
        at = data[("transaction", "to", "merchant")].edge_index
        assert at.shape == (2, 1)

    def test_hydrate_empty_edges_are_zero_sized(self):
        data = GraphFeatureEngine(None).hydrate_features(self._graph(), None)
        for rel in [("user", "performed", "transaction"), ("transaction", "to", "merchant"),
                    ("user", "used", "device"), ("user", "transferred_to", "user"),
                    ("device", "shared_by", "user")]:
            assert data[rel].edge_index.shape == (2, 0)


class TestEgoGraphExtraction:
    def test_extract_ego_graph_skips_missing_seed(self):
        import networkx as nx

        from engine.graph_feature_engine import GraphFeatureEngine
        g = nx.MultiDiGraph()
        g.add_node("m1", node_type="merchant")
        engine = GraphFeatureEngine(nx.MultiDiGraph.__new__(nx.MultiDiGraph))
        engine.graph_db = type("_DB", (), {"graph": g})()
        sub = engine.extract_ego_graph("ghost", "m1")
        assert "m1" in sub.nodes

    def test_extract_ego_graph_live_trims_old_txns(self):
        import networkx as nx

        from engine.graph_feature_engine import extract_ego_graph_live
        g = nx.Graph()
        g.add_node("u1", node_type="user")
        g.add_node("m1", node_type="merchant")
        for i in range(12):
            g.add_node(f"txn{i}", node_type="transaction", timestamp=i)
            g.add_edge("u1", f"txn{i}")
        g.add_edge("u1", "m1")
        sub = extract_ego_graph_live(g, "u1", "m1", hops=1, max_txns=10)
        assert "txn0" not in sub.nodes
        assert "txn1" not in sub.nodes
        assert "txn11" in sub.nodes
        assert len([n for n in sub.nodes if n.startswith("txn")]) == 10
