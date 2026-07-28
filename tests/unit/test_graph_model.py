import pytest
import torch

from engine.graph_model import PayShieldGNN
from engine.graph_feature_engine import GraphFeatureEngine
from engine.ensemble import EnsembleFusionEngine
from engine.explainer import GNNExplainerWrapper, SHAPBridge


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
        assert out.shape == torch.Size([2])
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
        tensor = engine._build_node_tensor(subgraph, [], ["x"])
        assert tensor.shape == (0, 1)

    def test_build_node_tensor_with_data(self):
        import networkx as nx
        engine = GraphFeatureEngine(None)
        subgraph = nx.MultiDiGraph()
        subgraph.add_node("n1", node_type="user", credit_score=750, account_age_days=365)
        subgraph.add_node("n2", node_type="user", credit_score=600, account_age_days=100)
        tensor = engine._build_node_tensor(subgraph, ["n1", "n2"], ["credit_score", "account_age_days"])
        assert tensor.shape == (2, 2)
