import torch
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, SAGEConv, global_mean_pool


class PayShieldGNN(torch.nn.Module):
    def __init__(self, hidden_channels: int = 64, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.dropout = dropout
        self.convs = torch.nn.ModuleList()

        for _ in range(num_layers):
            conv = HeteroConv(
                {
                    ("user", "performed", "transaction"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                    ("transaction", "to", "merchant"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                    ("user", "used", "device"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                    ("user", "transfer", "user"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                    ("device", "shared_by", "user"): SAGEConv((-1, -1), hidden_channels, aggr="mean"),
                },
                aggr="mean",
            )
            self.convs.append(conv)

        self.lin1 = torch.nn.Linear(hidden_channels * 2, 32)
        self.lin2 = torch.nn.Linear(32, 1)
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

    def forward(self, x_dict, edge_index_dict, batch_dict=None):
        x_dict = {key: x for key, x in x_dict.items() if x.size(0) > 0}
        # Drop empty edge types: SAGEConv crashes on zero-edge tensors in
        # newer torch_geometric releases, and no edges means no message pass.
        # Also drop edges whose src/dst node type has no features in this
        # graph — those types simply stay out of the pooling.
        edge_index_dict = {
            et: ei for et, ei in edge_index_dict.items()
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
            x_dict = {key: F.dropout(x, p=self.dropout, training=self.training) for key, x in x_dict.items()}
        x_dict = {key: self._project(key, x) for key, x in x_dict.items()}

        if "user" in x_dict and x_dict["user"].size(0) > 0:
            if batch_dict and "user" in batch_dict:
                user_emb = global_mean_pool(x_dict["user"], batch_dict["user"])
            else:
                user_emb = x_dict["user"].mean(dim=0, keepdim=True)
        else:
            user_emb = torch.zeros(1, self.lin1.in_features // 2)

        if "transaction" in x_dict and x_dict["transaction"].size(0) > 0:
            if batch_dict and "transaction" in batch_dict:
                txn_emb = global_mean_pool(x_dict["transaction"], batch_dict["transaction"])
            else:
                txn_emb = x_dict["transaction"].mean(dim=0, keepdim=True)
        else:
            txn_emb = torch.zeros(1, self.lin1.in_features // 2)

        if user_emb.size(0) == 1 and txn_emb.size(0) > 1:
            user_emb = user_emb.expand(txn_emb.size(0), -1)
        elif txn_emb.size(0) == 1 and user_emb.size(0) > 1:
            txn_emb = txn_emb.expand(user_emb.size(0), -1)

        h = torch.cat([user_emb, txn_emb], dim=-1)
        h = F.relu(self.lin1(h))
        h = F.dropout(h, p=self.dropout, training=self.training)
        out = self.lin2(h)
        return torch.sigmoid(out).squeeze(-1)

    @torch.no_grad()
    def predict_proba(self, x_dict, edge_index_dict, batch_dict=None) -> torch.Tensor:
        self.eval()
        return self.forward(x_dict, edge_index_dict, batch_dict)
