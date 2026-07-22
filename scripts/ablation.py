import argparse
import time

import numpy as np
import torch
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import cross_val_score

from data.synthetic_upi import SyntheticUPIGenerator
from data.graph_builder import HeterogeneousGraphBuilder
from engine.graph_model import PayShieldGNN


def extract_tabular_features(df: pd.DataFrame) -> np.ndarray:
    features = []
    for _, row in df.iterrows():
        feats = [
            row["amount"],
            row["amount"] / 500.0,
            float(hash(row["mcc_code"]) % 100) / 100.0,
        ]
        features.append(feats)
    return np.array(features)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-users", type=int, default=500)
    parser.add_argument("--n-txns", type=int, default=5000)
    parser.add_argument("--no-xgb", action="store_true")
    parser.add_argument("--no-gnn", action="store_true")
    args = parser.parse_args()

    print("Generating data...")
    gen = SyntheticUPIGenerator(n_users=args.n_users, n_transactions=args.n_txns, fraud_ratio=0.05)
    df = gen.generate()
    labels = df["is_fraud"].values

    results = {}

    if not args.no_xgb:
        print("\n--- XGBoost (Tabular Only) ---")
        X_tab = extract_tabular_features(df)
        xgb = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42
        )
        start = time.time()
        scores = cross_val_score(xgb, X_tab, labels, cv=3, scoring="roc_auc")
        elapsed = time.time() - start
        xgb.fit(X_tab, labels)
        xgb_pred = xgb.predict_proba(X_tab)[:, 1]
        xgb_pr_auc = average_precision_score(labels, xgb_pred)
        results["XGBoost (tabular)"] = {
            "AUC-ROC": f"{scores.mean():.4f} ± {scores.std():.4f}",
            "PR-AUC": f"{xgb_pr_auc:.4f}",
            "Train time": f"{elapsed:.1f}s",
        }
        print(f"  AUC-ROC: {scores.mean():.4f} ± {scores.std():.4f}")
        print(f"  PR-AUC:  {xgb_pr_auc:.4f}")

    if not args.no_gnn:
        print("\n--- HeteroConv GraphSAGE (Full) ---")
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
        builder.add_p2p_edges(df)
        builder.add_device_sharing_edges()
        pyg_data = builder.to_pyg_data()

        device = torch.device("cpu")
        model = PayShieldGNN(hidden_channels=32, num_layers=2).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

        x_dict = {nt: pyg_data[nt].x.to(device) for nt in pyg_data.node_types}
        edge_index_dict = {et: pyg_data[et].edge_index.to(device) for et in pyg_data.edge_types}
        labels_t = torch.tensor(labels, dtype=torch.float32)

        start = time.time()
        model.train()
        for epoch in range(20):
            optimizer.zero_grad()
            out = model(x_dict, edge_index_dict)
            loss = torch.nn.functional.binary_cross_entropy(out, labels_t[:len(out)])
            loss.backward()
            optimizer.step()
        elapsed = time.time() - start

        model.eval()
        with torch.no_grad():
            gnn_pred = model(x_dict, edge_index_dict).numpy()
        gnn_auc = roc_auc_score(labels[:len(gnn_pred)], gnn_pred)
        gnn_pr_auc = average_precision_score(labels[:len(gnn_pred)], gnn_pred)
        results["HeteroConv GraphSAGE"] = {
            "AUC-ROC": f"{gnn_auc:.4f}",
            "PR-AUC": f"{gnn_pr_auc:.4f}",
            "Train time": f"{elapsed:.1f}s",
        }
        print(f"  AUC-ROC: {gnn_auc:.4f}")
        print(f"  PR-AUC:  {gnn_pr_auc:.4f}")

    print(f"\n{'─' * 50}")
    print("Ablation Study Results")
    print(f"{'─' * 50}")
    for name, metrics in results.items():
        print(f"\n  {name}")
        for k, v in metrics.items():
            print(f"    {k}: {v}")
    print(f"{'─' * 50}")


if __name__ == "__main__":
    main()
