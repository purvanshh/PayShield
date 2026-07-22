import torch


class GNNExplainerWrapper:
    def __init__(self, model, num_hops: int = 2):
        self.model = model
        self.num_hops = num_hops

    @torch.no_grad()
    def explain(self, x_dict, edge_index_dict, target_node_type: str = "user", top_k: int = 5):
        self.model.eval()
        out = self.model(x_dict, edge_index_dict)
        pred_score = out.mean().item()

        node_contributions = {}
        for ntype, x in x_dict.items():
            if x.size(0) == 0:
                continue
            grad = torch.zeros_like(x)
            x.requires_grad_(True)
            x_dict_grad = {ntype if k == ntype else k: (v.clone().detach() if k != ntype else v) for k, v in x_dict.items()}
            x_dict_grad[ntype] = x
            out_grad = self.model(x_dict_grad, edge_index_dict)
            score = out_grad.mean()
            score.backward(retain_graph=True)
            grad = x.grad.abs().mean(dim=1)
            top_nodes = grad.topk(min(top_k, grad.size(0))).indices.tolist()
            node_contributions[ntype] = {
                "top_k_indices": top_nodes,
                "top_k_scores": grad[top_nodes].tolist(),
            }
            x.detach_()
            x.grad = None

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
        self.model.eval()
        baseline = torch.zeros_like(tabular_features)
        n_features = tabular_features.size(-1)
        shap_values = torch.zeros(n_features)

        for i in range(n_features):
            f_max = tabular_features[0, i].item()
            f_min = 0.0
            if abs(f_max - f_min) < 1e-6:
                continue
            vals = torch.linspace(f_min, f_max, 20)
            inp_pos = tabular_features.clone().repeat(20, 1)
            inp_neg = baseline.clone().repeat(20, 1)
            inp_pos[:, i] = vals
            with torch.no_grad():
                out_pos = self.model(inp_pos.unsqueeze(1) if inp_pos.dim() == 2 else inp_pos)
                out_neg = self.model(inp_neg.unsqueeze(1) if inp_neg.dim() == 2 else inp_neg)
            shap_values[i] = (out_pos - out_neg).mean().item()

        total = shap_values.abs().sum()
        if total > 0:
            shap_values = shap_values / total
        return {
            "shap_values": shap_values.tolist(),
            "top_features": shap_values.topk(min(5, n_features)).indices.tolist(),
        }
