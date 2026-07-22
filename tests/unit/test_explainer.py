import pytest
import torch

from engine.explainer import GNNExplainerWrapper, SHAPBridge
from engine.graph_model import PayShieldGNN


class TestGNNExplainer:
    def test_explain_returns_all_keys(self):
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
        result = explainer.explain(x_dict, edge_index_dict, target_node_type="user", top_k=2)
        assert "fraud_probability" in result
        assert 0 <= result["fraud_probability"] <= 1
        assert "node_contributions" in result
        assert "evidence_subgraph" in result

    def test_explain_empty_graph(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        explainer = GNNExplainerWrapper(model)
        x_dict = {
            "user": torch.randn(0, 4),
            "merchant": torch.randn(0, 5),
            "device": torch.randn(0, 3),
            "transaction": torch.randn(0, 2),
        }
        edge_index_dict = {}
        result = explainer.explain(x_dict, edge_index_dict)
        assert result is not None


class TestSHAPBridge:
    def test_shap_values_dimensionality(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        bridge = SHAPBridge(model)
        tab = torch.randn(1, 5)
        result = bridge.compute_importances(tab)
        assert len(result["shap_values"]) == 5

    def test_shap_values_normalized(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        bridge = SHAPBridge(model)
        tab = torch.randn(1, 4)
        result = bridge.compute_importances(tab)
        if any(v != 0 for v in result["shap_values"]):
            total = sum(abs(v) for v in result["shap_values"])
            assert abs(total - 1.0) < 0.01 or total == 0

    def test_shap_single_feature(self):
        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        bridge = SHAPBridge(model)
        tab = torch.randn(1, 1)
        result = bridge.compute_importances(tab)
        assert len(result["shap_values"]) == 1
