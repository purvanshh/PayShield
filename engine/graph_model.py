import torch
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, SAGEConv, global_mean_pool


class PayShieldGNN(torch.nn.Module):
    def __init__(self, hidden_channels: int = 64, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.hidden_channels = hidden_channels
        self.num_layers = num_layers
        self.dropout = dropout
        self.convs = torch.nn.ModuleList()

        for _ in range(num_layers):
            conv = HeteroConv(
                {
                    ("user", "performed", "transaction"): SAGEConv(
                        (-1, -1), hidden_channels, aggr="mean"
                    ),
                    ("transaction", "to", "merchant"): SAGEConv(
                        (-1, -1), hidden_channels, aggr="mean"
                    ),
                    ("user", "used", "device"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                    ("user", "transferred_to", "user"): SAGEConv(
                        (-1, -1), hidden_channels, aggr="mean"
                    ),
                    ("device", "shared_by", "user"): SAGEConv(
                        (-1, -1), hidden_channels, aggr="mean"
                    ),
                },
                aggr="mean",
            )
            self.convs.append(conv)

        self.lin1 = torch.nn.Linear(hidden_channels * 2, 32)
        self.lin2 = torch.nn.Linear(32, 1)
        # Readout attention over the target user's transactions (mirrors
        # ml/model.py — the trained artifact). Unused under the legacy
        # graph-level pooling path.
        self.txn_attn = torch.nn.Linear(hidden_channels, 1)
        self._projections: dict[str, torch.nn.Linear] = {}

    def _project(self, key: str, x: torch.Tensor) -> torch.Tensor:
        """Map raw node features to hidden dim for types never touched by a
        conv (a node type only ever appears as a source in the edge set)."""
        if x.size(-1) == self.lin1.in_features // 2:
            return x
        proj = self._projections.get(key)
        if proj is None:
            proj = torch.nn.Linear(x.size(-1), self.lin1.in_features // 2)
            self._projections[key] = proj
        return proj(x)

    def forward(
        self,
        x_dict,
        edge_index_dict,
        batch_dict=None,
        target_user_idx=None,
        target_txn_starts=None,
        target_txn_n=None,
    ):
        x_dict = {key: x for key, x in x_dict.items() if x.size(0) > 0}
        # Drop empty edge types: SAGEConv crashes on zero-edge tensors in
        # newer torch_geometric releases, and no edges means no message pass.
        # Also drop edges whose src/dst node type has no features in this
        # graph — those types simply stay out of the pooling.
        edge_index_dict = {
            et: ei
            for et, ei in edge_index_dict.items()
            if ei.numel() > 0 and et[0] in x_dict and et[2] in x_dict
        }
        for conv in self.convs:
            updated = conv(x_dict, edge_index_dict)
            # HeteroConv only emits destination node types; carry the other
            # types' features forward so every SAGEConv keeps valid inputs
            # (a conv whose src node type was never updated would receive
            # None features and crash).
            x_dict = {key: (updated[key] if key in updated else x_dict[key]) for key in x_dict}
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}
            x_dict = {
                key: F.dropout(x, p=self.dropout, training=self.training)
                for key, x in x_dict.items()
            }
        x_dict = {key: self._project(key, x) for key, x in x_dict.items()}

        if (
            target_user_idx is not None
            and target_user_idx.numel() > 0
            and "user" in x_dict
            and x_dict["user"].size(0) > 0
        ):
            batch_size = target_user_idx.numel()
            device = x_dict["user"].device
            user_emb = x_dict["user"][target_user_idx]  # [B, H]
            if (
                "transaction" in x_dict
                and x_dict["transaction"].size(0) > 0
                and target_txn_starts is not None
                and target_txn_n is not None
            ):
                txn_reps = []
                for b in range(batch_size):
                    sl = x_dict["transaction"][
                        target_txn_starts[b] : target_txn_starts[b] + target_txn_n[b]
                    ]
                    if sl.size(0) == 0:
                        txn_reps.append(torch.zeros(self.lin1.in_features // 2, device=device))
                        continue
                    scores = self.txn_attn(sl)
                    weights = torch.softmax(scores, dim=0)
                    txn_reps.append((weights * sl).sum(dim=0))
                txn_emb = torch.stack(txn_reps, dim=0)  # [B, H]
            else:
                txn_fallback = self._pool_txn(x_dict, batch_dict)
                txn_emb = txn_fallback.expand(batch_size, -1)
        else:
            user_emb = self._pool_user(x_dict, batch_dict)
            txn_emb = self._pool_txn(x_dict, batch_dict)

        h = torch.cat([user_emb, txn_emb], dim=-1)
        h = F.relu(self.lin1(h))
        h = F.dropout(h, p=self.dropout, training=self.training)
        out = self.lin2(h)
        return torch.sigmoid(out).squeeze(-1)

    def _pool_user(self, x_dict, batch_dict) -> torch.Tensor:
        if "user" in x_dict and x_dict["user"].size(0) > 0:
            if batch_dict and "user" in batch_dict:
                return global_mean_pool(x_dict["user"], batch_dict["user"])
            return x_dict["user"].mean(dim=0, keepdim=True)
        return torch.zeros(1, self.lin1.in_features // 2)

    def _pool_txn(self, x_dict, batch_dict) -> torch.Tensor:
        if "transaction" in x_dict and x_dict["transaction"].size(0) > 0:
            if batch_dict and "transaction" in batch_dict:
                return global_mean_pool(x_dict["transaction"], batch_dict["transaction"])
            return x_dict["transaction"].mean(dim=0, keepdim=True)
        return torch.zeros(1, self.lin1.in_features // 2)

    @torch.no_grad()
    def predict_proba(self, x_dict, edge_index_dict, batch_dict=None) -> torch.Tensor:
        self.eval()
        return self.forward(x_dict, edge_index_dict, batch_dict)

    @classmethod
    def from_checkpoint(
        cls,
        path,
        fallback_hidden: int = 64,
        fallback_layers: int = 2,
        fallback_dropout: float = 0.3,
    ) -> "PayShieldGNN":
        """Construct the serving model from a benchmark/training artifact.

        The checkpoint metadata (saved by scripts/benchmark_gnn.py --save-model)
        carries the hyperparameters the model was trained with; reading them
        here keeps serving dimensions in lockstep with the trained artifact
        instead of relying on caller-supplied defaults.
        """
        state = torch.load(path, map_location="cpu", weights_only=False)
        if not isinstance(state, dict) or "state_dict" not in state:
            raise ValueError(f"unexpected checkpoint layout in {path}")
        meta = state
        model = cls(
            hidden_channels=meta.get("hidden_channels", fallback_hidden),
            num_layers=meta.get("num_layers", fallback_layers),
            dropout=meta.get("dropout", fallback_dropout),
        )
        model.load_state_dict(meta["state_dict"])
        model.eval()
        return model
