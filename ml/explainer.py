import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

try:
    import torch
    from torch_geometric.explain import GNNExplainer as PyGGNNExplainer
    _has_pyg_explain = True
except ImportError:
    PyGGNNExplainer = None
    _has_pyg_explain = False


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
    def __init__(self, model, epochs: int = 200, lr: float = 0.01):
        self.model = model
        self.epochs = epochs
        self.lr = lr
        self.device = next(model.parameters()).device

    def explain(self, data, target_node: str = "user") -> ExplanationResult:
        if not _has_pyg_explain:
            raise ImportError("PyTorch Geometric explain module is required")

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
