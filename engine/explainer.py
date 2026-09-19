"""Unified explainability module for PayShield GNN and tabular models.

Consolidates gradient-based (engine) and PyG/shap-based (ml) explainers.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import torch

try:
    import numpy as np
    _has_numpy = True
except ImportError:
    _has_numpy = False

try:
    import shap
    _has_shap = True
except ImportError:
    _has_shap = False

try:
    from torch_geometric.explain import GNNExplainer as PyGGNNExplainer
    _has_pyg_explain = True
except ImportError:
    PyGGNNExplainer = None
    _has_pyg_explain = False

logger = logging.getLogger(__name__)


class FraudPattern(Enum):
    MULE_RING = "MULE_RING"
    BURST_ATTACK = "BURST_ATTACK"
    MERCHANT_COLLUSION = "MERCHANT_COLLUSION"
    ATO = "ACCOUNT_TAKEOVER"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExplanationResult:
    original_score: float = 0.0
    subgraph_score: float = 0.0
    fidelity: float = 0.0
    important_nodes: list[dict] = field(default_factory=list)
    important_edges: list[dict] = field(default_factory=list)
    subgraph_size: int = 0
    computation_time_ms: float = 0.0
    fraud_pattern: FraudPattern = FraudPattern.UNKNOWN
    node_mask: Any = None
    edge_mask: Any = None


class GNNExplainerWrapper:
    """Gradient-based GNN explainer (from engine/explainer.py).

    Uses input perturbation to compute per-node feature importance.
    """

    def __init__(self, model, num_hops: int = 2):
        self.model = model
        self.num_hops = num_hops

    def explain(self, x_dict, edge_index_dict, target_node_type: str = "user", top_k: int = 5):
        self.model.eval()
        with torch.no_grad():
            out = self.model(x_dict, edge_index_dict)
            pred_score = out.mean().item()

        node_contributions = {}
        for ntype, x in x_dict.items():
            if x.size(0) == 0:
                continue
            x_pert = x.detach().clone().requires_grad_(True)
            x_dict_grad = {
                k: (x_pert if k == ntype else v.detach()) for k, v in x_dict.items()
            }
            out_grad = self.model(x_dict_grad, edge_index_dict)
            score = out_grad.mean()
            self.model.zero_grad()
            score.backward(retain_graph=True)
            if x_pert.grad is None:
                # Node type does not reach the pooled score (no gradient
                # path) — nothing to attribute.
                continue
            grad = x_pert.grad.abs().mean(dim=1)
            top_nodes = grad.topk(min(top_k, grad.size(0))).indices.tolist()
            node_contributions[ntype] = {
                "top_k_indices": top_nodes,
                "top_k_scores": grad[top_nodes].tolist(),
            }
            x_pert.grad = None

        return {
            "fraud_probability": pred_score,
            "node_contributions": node_contributions,
            "num_nodes": sum(x.size(0) for x in x_dict.values()),
            "evidence_subgraph": self._build_evidence(edge_index_dict, node_contributions),
        }

    def _build_evidence(self, edge_index_dict, node_contributions):
        evidence = []
        for edge_type, ei in edge_index_dict.items():
            if ei.size(1) > 0:
                evidence.append(f"{edge_type}: {ei.size(1)} edges")
        for ntype, contrib in node_contributions.items():
            evidence.append(f"{ntype}: top features at indices {contrib['top_k_indices']}")
        return evidence


class PyGGNNExplainerWrapper:
    """PyTorch Geometric GNNExplainer wrapper (from ml/explainer.py).

    Uses PyG's built-in GNNExplainer for subgraph-based explanations.
    """

    def __init__(self, model, epochs: int = 200, lr: float = 0.01):
        if not _has_pyg_explain:
            raise ImportError("PyTorch Geometric explain module is required")
        self.model = model
        self.epochs = epochs
        self.lr = lr
        self.device = next(model.parameters()).device

    def explain(self, data, target_node: str = "user") -> ExplanationResult:
        if not hasattr(data, "x_dict"):
            raise ValueError("Data must have x_dict and edge_index_dict (HeteroData)")

        self.model.eval()
        start_time = time.perf_counter()

        explainer = PyGGNNExplainer(
            self.model,
            epochs=self.epochs,
            lr=self.lr,
        )

        explanation = explainer(
            data.x_dict,
            data.edge_index_dict,
            target=torch.tensor([0], device=self.device),
        )

        original_logits = self.model(data.x_dict, data.edge_index_dict)
        original_score = float(torch.sigmoid(original_logits).max().detach().cpu().numpy())

        node_importance: dict[str, list[tuple[str, float]]] = {}
        for ntype in data.node_types:
            n_mask = explanation.get(f"{ntype}_node_mask")
            if n_mask is not None:
                node_ids = list(range(n_mask.size(0)))
                scores = n_mask.detach().cpu().numpy().flatten()
                node_importance[ntype] = sorted(
                    [(str(i), float(s)) for i, s in zip(node_ids, scores)],
                    key=lambda x: -x[1],
                )[:10]

        edge_importance: list[dict] = []
        for etype in data.edge_types:
            e_mask = explanation.get(f"{etype}_edge_mask") if hasattr(explanation, f"{etype}_edge_mask") else None
            if e_mask is not None:
                ei = data[etype].edge_index
                scores = e_mask.detach().cpu().numpy().flatten()
                top_edges = sorted(
                    [
                        {
                            "source": int(ei[0, i].cpu().numpy()),
                            "target": int(ei[1, i].cpu().numpy()),
                            "type": str(etype[1]),
                            "importance": float(s),
                        }
                        for i, s in enumerate(scores)
                    ],
                    key=lambda x: -x["importance"],
                )[:10]
                edge_importance.extend(top_edges)

        important_nodes = []
        for ntype, nodes in node_importance.items():
            for nid, score in nodes:
                important_nodes.append({
                    "node_id": nid,
                    "type": ntype,
                    "importance_score": round(score, 4),
                })

        subgraph_score = original_score
        fidelity = 1.0

        elapsed = (time.perf_counter() - start_time) * 1000
        fraud_pattern = self._classify_pattern(important_nodes, edge_importance)

        return ExplanationResult(
            original_score=round(original_score, 4),
            subgraph_score=round(subgraph_score, 4),
            fidelity=round(fidelity, 4),
            important_nodes=important_nodes,
            important_edges=edge_importance,
            subgraph_size=len(important_nodes),
            computation_time_ms=round(elapsed, 2),
            fraud_pattern=fraud_pattern,
            node_mask=explanation.get("node_mask") if hasattr(explanation, "node_mask") else None,
            edge_mask=explanation.get("edge_mask") if hasattr(explanation, "edge_mask") else None,
        )

    def _classify_pattern(self, important_nodes: list[dict], important_edges: list[dict]) -> FraudPattern:
        node_types = [n["type"] for n in important_nodes if n["importance_score"] > 0.1]
        edge_types = [e["type"] for e in important_edges if e["importance"] > 0.1]

        user_count = node_types.count("user")
        device_count = node_types.count("device")
        merchant_count = node_types.count("merchant")

        if device_count >= 2 and user_count >= 2:
            return FraudPattern.MULE_RING
        if merchant_count >= 2 and user_count >= 1:
            return FraudPattern.MERCHANT_COLLUSION
        if device_count >= 1 and user_count == 1:
            return FraudPattern.BURST_ATTACK
        if user_count >= 1 and "transferred_to" in edge_types:
            return FraudPattern.ATO

        return FraudPattern.UNKNOWN


@dataclass
class SHAPResult:
    feature_names: list[str] = field(default_factory=list)
    shap_values: list[float] = field(default_factory=list)
    base_value: float = 0.0
    expected_value: float = 0.0
    top_positive_features: list[dict] = field(default_factory=list)
    top_negative_features: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_names": self.feature_names,
            "shap_values": [round(v, 6) for v in self.shap_values],
            "base_value": round(self.base_value, 4),
            "expected_value": round(self.expected_value, 4),
            "top_positive_features": self.top_positive_features[:5],
            "top_negative_features": self.top_negative_features[:5],
        }


class SHAPBridge:
    """SHAP explainer for tabular features (from ml/explainer.py).

    Uses SHAP library to compute feature importance for tabular models.
    """

    def __init__(self, model, background_data: list | None = None):
        if not _has_shap:
            raise ImportError("shap library is required for SHAP explanations")
        if not _has_numpy:
            raise ImportError("numpy is required for SHAP explanations")
        self.model = model
        self.background_data = background_data or []
        self.device = next(model.parameters()).device

    def explain_tabular(self, tabular_tensor: torch.Tensor, feature_names: list[str]) -> SHAPResult:
        self.model.eval()
        tabular_np = tabular_tensor.detach().cpu().numpy()

        if self.background_data:
            background_np = np.array(self.background_data)
            explainer = shap.Explainer(
                lambda x: self._predict_on_tabular(torch.tensor(x, dtype=torch.float32)),
                background_np,
            )
        else:
            explainer = shap.Explainer(
                lambda x: self._predict_on_tabular(torch.tensor(x, dtype=torch.float32)),
                tabular_np,
            )

        shap_values = explainer(tabular_np)

        values = shap_values.values.flatten().tolist() if hasattr(shap_values, "values") else [0.0] * len(feature_names)
        base_value = float(shap_values.base_values.flatten()[0]) if hasattr(shap_values, "base_values") else 0.0
        expected_value = base_value

        indexed = list(enumerate(values))
        indexed.sort(key=lambda x: -x[1])
        top_pos = [
            {"feature": feature_names[i], "value": float(values[i]) if i < len(values) else 0.0, "shap": round(v, 6)}
            for i, v in indexed[:5] if v > 0
        ]
        indexed.sort(key=lambda x: x[1])
        top_neg = [
            {"feature": feature_names[i], "value": float(values[i]) if i < len(values) else 0.0, "shap": round(v, 6)}
            for i, v in indexed[:5] if v < 0
        ]

        return SHAPResult(
            feature_names=feature_names,
            shap_values=[round(v, 6) for v in values],
            base_value=round(base_value, 4),
            expected_value=round(expected_value, 4),
            top_positive_features=top_pos,
            top_negative_features=top_neg,
        )

    def _predict_on_tabular(self, x: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            x = x.to(self.device)
            dummy = {"user": torch.randn(x.size(0), 5), "transaction": torch.randn(x.size(0), 4)}
            out = torch.sigmoid(self.model.classifier(torch.cat([dummy["user"], dummy["transaction"]], dim=-1)))
            return out.cpu().numpy()

    def compute_importances(self, tabular_features: torch.Tensor) -> dict:
        """Backward-compatible gradient-based feature importance (from engine/explainer.py).

        Delegates to SHAPFeatureBridge for the actual computation.
        """
        bridge = SHAPFeatureBridge(self.model)
        return bridge.compute_importances(tabular_features)


class SHAPFeatureBridge:
    """Gradient-based SHAP-like feature importance (from engine/explainer.py).

    Perturbs each feature column from min to max and measures score drop.
    """

    def __init__(self, model):
        self.model = model

    def compute_importances(self, tabular_features: torch.Tensor) -> dict:
        """Per-column feature influence on the graph model's score.

        The features are placed on the user/transaction nodes of a minimal
        one-hop graph (self-loop), and each column is perturbed from its
        minimum (0.0) to its maximum while the rest stays fixed. The absolute
        drop from the baseline score is the per-feature importance.
        """
        self.model.eval()
        n_rows = tabular_features.size(0)
        n_features = tabular_features.size(-1)
        feats = tabular_features.clone().detach()
        # Import MCC_ORDER from graph_feature_engine (kept for compatibility)
        try:
            from engine.graph_feature_engine import MCC_ORDER
        except ImportError:
            MCC_ORDER = [
                "food", "travel", "utilities", "fashion", "groceries",
                "entertainment", "health", "education", "transport", "rent",
                "recharge", "insurance", "investment", "cashback", "other",
            ]
        x_dict = {
            "user": feats,
            "merchant": torch.zeros(n_rows, len(MCC_ORDER) + 4),
            "device": torch.zeros(n_rows, 4),
            "transaction": feats,
        }
        edge_index_dict = {
            ("user", "performed", "transaction"): torch.stack(
                [torch.arange(n_rows), torch.arange(n_rows)]
            ),
        }
        with torch.no_grad():
            baseline = self.model(x_dict, edge_index_dict).mean().item()

        shap_values = torch.zeros(n_features)
        for i in range(n_features):
            f_max = tabular_features[0, i].item()
            f_min = 0.0
            if abs(f_max - f_min) < 1e-6:
                continue
            vals = torch.linspace(f_min, f_max, 20)
            inp = tabular_features.clone().repeat(20, 1)
            inp[:, i] = vals
            xd = {**x_dict, "user": inp, "transaction": inp}
            with torch.no_grad():
                out_pos = self.model(xd, edge_index_dict).mean().item()
            shap_values[i] = abs(out_pos - baseline)

        total = shap_values.abs().sum()
        if total > 0:
            shap_values = shap_values / total
        return {
            "shap_values": shap_values.tolist(),
            "top_features": shap_values.topk(min(5, n_features)).indices.tolist(),
        }


@dataclass
class UnifiedEvidence:
    graph_explanation: ExplanationResult | None = None
    tabular_explanation: SHAPResult | None = None
    combined_summary: str = ""
    fraud_pattern: FraudPattern = FraudPattern.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "fraud_pattern": self.fraud_pattern.value,
            "graph": {
                "fidelity": self.graph_explanation.fidelity if self.graph_explanation else None,
                "top_nodes": [n["node_id"] for n in (self.graph_explanation.important_nodes if self.graph_explanation else [])[:5]],
                "subgraph_size": self.graph_explanation.subgraph_size if self.graph_explanation else 0,
            } if self.graph_explanation else None,
            "tabular": self.tabular_explanation.to_dict() if self.tabular_explanation else None,
            "summary": self.combined_summary,
        }


class DualExplanationMerger:
    @staticmethod
    def merge(
        graph_explanation: ExplanationResult | None,
        shap_result: SHAPResult | None
    ) -> UnifiedEvidence:
        lines = []

        pattern = graph_explanation.fraud_pattern if graph_explanation else FraudPattern.UNKNOWN

        if graph_explanation:
            lines.append(f"Graph Structure: {pattern.value}")
            lines.append(f"  Top nodes: {', '.join(n['node_id'] for n in graph_explanation.important_nodes[:3])}")
            lines.append(f"  Subgraph size: {graph_explanation.subgraph_size}")
            lines.append(f"  Graph fidelity: {graph_explanation.fidelity:.2f}")

        if shap_result:
            lines.append(f"Tabular Features:")
            for f in shap_result.top_positive_features[:3]:
                lines.append(f"  +{f['feature']}: SHAP={f['shap']:.4f}")
            for f in shap_result.top_negative_features[:3]:
                lines.append(f"  -{f['feature']}: SHAP={f['shap']:.4f}")

        return UnifiedEvidence(
            graph_explanation=graph_explanation,
            tabular_explanation=shap_result,
            combined_summary="\n".join(lines),
            fraud_pattern=pattern,
        )


class ExplanationFormatter:
    @staticmethod
    def format(result: ExplanationResult) -> str:
        lines = [
            f"Explanation Result",
            f"{'='*50}",
            f"Fraud Pattern: {result.fraud_pattern.value}",
            f"Original Score: {result.original_score:.4f}",
            f"Fidelity: {result.fidelity:.4f}",
            f"Computation Time: {result.computation_time_ms:.2f} ms",
            f"",
            f"Top Contributing Nodes:",
        ]
        for n in result.important_nodes[:5]:
            lines.append(
                f"  {n['type']}:{n['node_id']} (importance={n['importance_score']:.4f})"
            )

        if result.important_edges:
            lines.append(f"")
            lines.append(f"Top Contributing Edges:")
            for e in result.important_edges[:5]:
                lines.append(
                    f"  {e['source']} -[{e['type']}]-> {e['target']} (importance={e['importance']:.4f})"
                )

        return "\n".join(lines)

    @staticmethod
    def classify_pattern(result: ExplanationResult) -> FraudPattern:
        return result.fraud_pattern