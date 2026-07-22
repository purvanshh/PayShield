import argparse

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_recall_curve, confusion_matrix,
)

from data.synthetic_upi import SyntheticUPIGenerator
from data.graph_builder import HeterogeneousGraphBuilder
from engine.graph_model import PayShieldGNN


def compute_fvar(df: pd.DataFrame, predictions: np.ndarray, threshold: float = 0.85,
                 avg_fraud_value: float = 15000.0, fp_cost: float = 50.0) -> dict:
    true_fraud = df["is_fraud"].values
    pred_fraud = predictions >= threshold

    tp = (true_fraud & pred_fraud).sum()
    fp = (~true_fraud & pred_fraud).sum()
    fn = (true_fraud & ~pred_fraud).sum()

    prevented_loss = tp * avg_fraud_value
    fp_penalty = fp * fp_cost
    missed_loss = fn * avg_fraud_value

    fvar = prevented_loss - fp_penalty - missed_loss

    return {
        "fvar_inr": round(fvar, 2),
        "prevented_loss_inr": round(prevented_loss, 2),
        "fp_penalty_inr": round(fp_penalty, 2),
        "missed_loss_inr": round(missed_loss, 2),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "false_negatives": int(fn),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="models/payshield_gnn_v1.pt")
    parser.add_argument("--n-users", type=int, default=500)
    parser.add_argument("--n-txns", type=int, default=5000)
    args = parser.parse_args()

    print("Generating evaluation data...")
    gen = SyntheticUPIGenerator(n_users=args.n_users, n_transactions=args.n_txns, fraud_ratio=0.05)
    df = gen.generate()

    print("Building graph...")
    builder = HeterogeneousGraphBuilder()
    builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
    builder.add_p2p_edges(df)
    builder.add_device_sharing_edges()
    pyg_data = builder.to_pyg_data()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PayShieldGNN().to(device)
    model.load_state_dict(torch.load(args.model_path, map_location=device))
    model.eval()

    x_dict = {nt: pyg_data[nt].x.to(device) for nt in pyg_data.node_types}
    edge_index_dict = {et: pyg_data[et].edge_index.to(device) for et in pyg_data.edge_types}

    with torch.no_grad():
        predictions = model(x_dict, edge_index_dict).cpu().numpy()

    labels = df["is_fraud"].values

    auc = roc_auc_score(labels, predictions)
    pr_auc = average_precision_score(labels, predictions)
    precision, recall, thresholds = precision_recall_curve(labels, predictions)

    print(f"\n{'─' * 50}")
    print(f"Evaluation Results")
    print(f"{'─' * 50}")
    print(f"  AUC-ROC:      {auc:.4f}")
    print(f"  PR-AUC:       {pr_auc:.4f}")
    print(f"  Fraud ratio:  {labels.mean():.4f}")
    print(f"  Total txns:   {len(df)}")

    for thresh in [0.5, 0.7, 0.85, 0.95]:
        fvar = compute_fvar(df, predictions, threshold=thresh)
        cm = confusion_matrix(labels, predictions >= thresh)
        tn, fp, fn, tp = cm.ravel()
        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        print(f"\n  Threshold: {thresh}")
        print(f"    TP: {tp}  FP: {fp}  FN: {fn}  TN: {tn}")
        print(f"    TPR: {tpr:.4f}  FPR: {fpr:.4f}")
        print(f"    FVaR: ₹{fvar['fvar_inr']:,.2f}")

    print(f"{'─' * 50}")


if __name__ == "__main__":
    main()
