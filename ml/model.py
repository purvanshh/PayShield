import logging
import math

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

try:
    from torch_geometric.nn import HeteroConv, SAGEConv
    _has_pyg = True
except ImportError:
    HeteroConv = None
    SAGEConv = None
    _has_pyg = False


class PayShieldGNN(torch.nn.Module):
    def __init__(self, edge_types: list[tuple[str, str, str]], hidden_channels: int = 64,
                 out_channels: int = 2, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        if not _has_pyg:
            raise ImportError("PyTorch Geometric is required")

        self.edge_types = edge_types
        self.hidden_channels = hidden_channels
        self.num_layers = num_layers
        self.dropout = dropout

        self.convs = torch.nn.ModuleList()
        for i in range(num_layers):
            conv = HeteroConv(
                {
                    et: SAGEConv((-1, -1), hidden_channels, aggr="mean")
                    for et in edge_types
                },
                aggr="mean",
            )
            self.convs.append(conv)

        self.classifier = torch.nn.Sequential(
            torch.nn.Linear(hidden_channels * 2, hidden_channels),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_channels, out_channels),
        )

        self._init_weights()

    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, torch.nn.Linear):
                torch.nn.init.xavier_uniform_(module.weight, gain=1.0)
                if module.bias is not None:
                    torch.nn.init.zeros_(module.bias)

    def forward(self, x_dict: dict[str, torch.Tensor],
                edge_index_dict: dict[tuple[str, str, str], torch.Tensor]) -> torch.Tensor:
        x_dict_out = x_dict

        for i, conv in enumerate(self.convs):
            x_dict_out = conv(x_dict_out, edge_index_dict)
            x_dict_out = {key: F.relu(x) for key, x in x_dict_out.items()}
            x_dict_out = {key: F.dropout(x, p=self.dropout, training=self.training) for key, x in x_dict_out.items()}

        user_emb = x_dict_out.get("user", torch.zeros((1, self.hidden_channels)))
        txn_emb = x_dict_out.get("transaction", torch.zeros((1, self.hidden_channels)))

        if user_emb.dim() == 2 and user_emb.size(0) > 1:
            user_emb = user_emb.mean(dim=0, keepdim=True)
        if txn_emb.dim() == 2 and txn_emb.size(0) > 1:
            txn_emb = txn_emb.mean(dim=0, keepdim=True)

        graph_emb = torch.cat([user_emb, txn_emb], dim=-1)
        return self.classifier(graph_emb)

    @torch.no_grad()
    def predict_proba(self, x_dict: dict[str, torch.Tensor],
                      edge_index_dict: dict[tuple[str, str, str], torch.Tensor]) -> torch.Tensor:
        """Return P(fraud) = sigmoid of the trained fraud logit (column 0).

        The model is trained with BCEWithLogitsLoss on ``out[:, :1]`` only,
        so column 1 is an untrained placeholder; softmax over both logits
        would corrupt the probability. Output shape is (batch, 1).
        """
        self.eval()
        logits = self.forward(x_dict, edge_index_dict)
        return torch.sigmoid(logits[:, 0:1])

    @torch.no_grad()
    def predict_proba_safe(self, x_dict: dict[str, torch.Tensor],
                           edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
                           timeout_ms: float = 20.0) -> tuple[float, bool]:
        """CPU inference guarded by an in-process timeout.

        Returns (fraud_probability, timed_out). Inference runs in a worker
        thread; if it does not finish within ``timeout_ms`` the caller gets
        ``(0.0, True)`` and must fall back to L1-only fusion.
        """
        import asyncio
        import threading

        result: dict[str, float] = {}
        error: list[Exception] = []

        def _run():
            try:
                probs = self.predict_proba(x_dict, edge_index_dict)
                result["prob"] = float(probs[0, 0])
            except Exception as e:  # pragma: no cover - defensive
                error.append(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_ms / 1000.0)

        if error:
            raise error[0]
        if thread.is_alive():
            return 0.0, True
        return result.get("prob", 0.0), False

    def forward_with_attention(self, x_dict: dict[str, torch.Tensor],
                               edge_index_dict: dict[tuple[str, str, str], torch.Tensor]) -> tuple[torch.Tensor, dict]:
        x_dict_out = x_dict
        attention_weights = {}

        for i, conv in enumerate(self.convs):
            x_dict_out = conv(x_dict_out, edge_index_dict)
            x_dict_out = {key: F.relu(x) for key, x in x_dict_out.items()}
            attention_weights[f"layer_{i}"] = {
                key: x.detach().cpu() for key, x in x_dict_out.items()
            }

        user_emb = x_dict_out.get("user", torch.zeros((1, self.hidden_channels)))
        txn_emb = x_dict_out.get("transaction", torch.zeros((1, self.hidden_channels)))

        if user_emb.dim() == 2 and user_emb.size(0) > 1:
            user_emb = user_emb.mean(dim=0, keepdim=True)
        if txn_emb.dim() == 2 and txn_emb.size(0) > 1:
            txn_emb = txn_emb.mean(dim=0, keepdim=True)

        graph_emb = torch.cat([user_emb, txn_emb], dim=-1)
        logits = self.classifier(graph_emb)

        return logits, attention_weights

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def get_param_stats(self) -> dict:
        total = 0
        stats = {}
        for name, param in self.named_parameters():
            num = param.numel()
            stats[name] = num
            total += num
        stats["total"] = total
        return stats

    def summary(self) -> str:
        lines = []
        lines.append(f"PayShieldGNN (hidden={self.hidden_channels}, layers={self.num_layers}, dropout={self.dropout})")
        lines.append(f"  Edge types: {len(self.edge_types)}")
        lines.append(f"  Trainable parameters: {self.count_parameters():,}")
        for name, param in self.named_parameters():
            lines.append(f"    {name}: {list(param.shape)} = {param.numel()}")
        return "\n".join(lines)


class FraudClassifier(torch.nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 64, output_dim: int = 2, dropout: float = 0.3):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(input_dim, hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)
