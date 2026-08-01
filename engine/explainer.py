import torch

from engine.graph_feature_engine import MCC_ORDER


class GNNExplainerWrapper:
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


class SHAPBridge:
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
