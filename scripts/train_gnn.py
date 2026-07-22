import argparse
import time

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc
from torch.optim import Adam
from torch_geometric.loader import DataLoader

from data.synthetic_upi import SyntheticUPIGenerator
from data.graph_builder import HeterogeneousGraphBuilder
from engine.graph_model import PayShieldGNN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--pos-weight", type=float, default=10.0)
    parser.add_argument("--n-users", type=int, default=2000)
    parser.add_argument("--n-txns", type=int, default=20000)
    args = parser.parse_args()

    print("Generating synthetic data...")
    gen = SyntheticUPIGenerator(
        n_users=args.n_users,
        n_transactions=args.n_txns,
        fraud_ratio=0.05,
    )
    df = gen.generate()

    print(f"Generated {len(df)} transactions ({df['is_fraud'].sum()} fraud)")

    print("Building graph...")
    builder = HeterogeneousGraphBuilder()
    builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
    builder.add_p2p_edges(df)
    builder.add_device_sharing_edges()
    pyg_data = builder.to_pyg_data()

    node_types = list(pyg_data.node_types)
    print(f"Node types: {node_types}")
    for nt in node_types:
        x = pyg_data[nt].x
        print(f"  {nt}: {x.shape}")

    for et in pyg_data.edge_types:
        ei = pyg_data[et].edge_index
        print(f"  {et}: {ei.shape}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PayShieldGNN(hidden_channels=args.hidden, num_layers=args.layers).to(device)
    optimizer = Adam(model.parameters(), lr=args.lr)

    labels = torch.tensor(df["is_fraud"].values, dtype=torch.float32)
    n_fraud = labels.sum().item()
    n_normal = len(labels) - n_fraud
    pos_weight = torch.tensor([n_normal / max(n_fraud, 1)])

    x_dict = {nt: pyg_data[nt].x.to(device) for nt in node_types}
    edge_index_dict = {et: pyg_data[et].edge_index.to(device) for et in pyg_data.edge_types}

    split = int(len(df) * 0.8)
    train_mask = torch.zeros(len(df), dtype=torch.bool)
    train_mask[:split] = True
    val_mask = torch.zeros(len(df), dtype=torch.bool)
    val_mask[split:] = True

    best_val_auc = 0.0
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad()
        out = model(x_dict, edge_index_dict)

        loss = F.binary_cross_entropy(
            out[train_mask[:len(out)]],
            labels[train_mask[:len(labels)]],
            pos_weight=pos_weight.to(device),
        )
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_out = out[val_mask[:len(out)]]
            val_labels = labels[val_mask[:len(labels)]]
            if len(val_labels.unique()) > 1:
                val_auc = roc_auc_score(val_labels.cpu(), val_out.cpu())
                precision, recall, _ = precision_recall_curve(val_labels.cpu(), val_out.cpu())
                val_pr_auc = auc(recall, precision)
            else:
                val_auc = 0.5
                val_pr_auc = 0.0

        if val_auc > best_val_auc:
            best_val_auc = val_auc
            torch.save(model.state_dict(), "models/payshield_gnn_v1.pt")

        if (epoch + 1) % 5 == 0:
            print(f"Epoch {epoch+1:2d}/{args.epochs} | Loss: {loss.item():.4f} | Val AUC: {val_auc:.4f} | Val PR-AUC: {val_pr_auc:.4f}")

    print(f"\nTraining complete. Best val AUC: {best_val_auc:.4f}")
    print("Model saved to models/payshield_gnn_v1.pt")


if __name__ == "__main__":
    main()
