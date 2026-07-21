import torch
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, SAGEConv


class PayShieldGNN(torch.nn.Module):
    def __init__(self, hidden_channels: int = 64, num_layers: int = 2):
        super().__init__()
        self.convs = torch.nn.ModuleList()
        for _ in range(num_layers):
            conv = HeteroConv(
                {
                    ("user", "performed", "transaction"): SAGEConv((-1, -1), hidden_channels),
                    ("transaction", "to", "merchant"): SAGEConv((-1, -1), hidden_channels),
                    ("user", "used", "device"): SAGEConv((-1, -1), hidden_channels),
                    ("user", "transfer", "user"): SAGEConv((-1, -1), hidden_channels),
                    ("device", "shared_by", "user"): SAGEConv((-1, -1), hidden_channels),
                },
                aggr="mean",
            )
            self.convs.append(conv)

        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(hidden_channels * 2, 32),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.3),
            torch.nn.Linear(32, 1),
        )

    def forward(self, x_dict, edge_index_dict):
        for conv in self.convs:
            x_dict = conv(x_dict, edge_index_dict)
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}

        user_emb = x_dict["user"].mean(dim=0, keepdim=True)
        txn_emb = x_dict["transaction"].mean(dim=0, keepdim=True)
        out = self.mlp(torch.cat([user_emb, txn_emb], dim=-1))
        return torch.sigmoid(out).squeeze()
