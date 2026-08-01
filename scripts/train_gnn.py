"""Production GNN trainer — trains the L2 GNN, fits an isotonic calibrator
on the validation set, and persists both artifacts for the hot path:

    models/production/current.pt            (GNN state dict + config)
    models/production/calibrator_v1.pkl     (IsotonicRegression, joblib)
    models/registry/v0.1.0/model_card.json  (metrics snapshot)

Usage:
    PYTHONPATH=. python3 scripts/train_gnn.py [--epochs 60] [--users 10000]
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score

from scripts.benchmark_gnn import (
    EgoGraphDataset,
    EDGE_TYPES,
    train_loop,
)
from ml.model import PayShieldGNN

CALIBRATOR_PATH = Path("models/production/calibrator_v1.pkl")
MODEL_PATH = Path("models/production/current.pt")
CARD_PATH = Path("models/registry/v0.1.0/model_card.json")


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i < n_bins - 1:
            mask = (probs >= lo) & (probs < hi)
        else:
            mask = (probs >= lo) & (probs <= hi)
        if not np.any(mask):
            continue
        acc = float(np.mean(labels[mask]))
        conf = float(np.mean(probs[mask]))
        ece += len(probs[mask]) / len(probs) * abs(acc - conf)
    return round(ece, 4)


def fit_and_save_calibrator(probs: list[float], labels: list[int], path: Path = CALIBRATOR_PATH):
    import joblib
    path.parent.mkdir(parents=True, exist_ok=True)
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(probs, labels)
    joblib.dump(calibrator, path)
    return calibrator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=10000)
    ap.add_argument("--merchants", type=int, default=1000)
    ap.add_argument("--txns", type=int, default=30000)
    ap.add_argument("--fraud-ratio", type=float, default=0.05)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--from-artifact", action="store_true",
                    help="skip training; load models/production/current.pt and only fit the calibrator")
    args = ap.parse_args()

    from data.synthetic.generator import SyntheticUPIGenerator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"train_gnn: device={device}, users={args.users}, txns={args.txns}, epochs={args.epochs}")

    gen = SyntheticUPIGenerator(
        n_users=args.users, n_merchants=args.merchants, n_transactions=args.txns,
        fraud_ratio=args.fraud_ratio, seed=args.seed,
    )
    df = gen.generate()
    print(f"generated {len(df)} txns ({int(df['is_fraud'].sum())} fraud)")

    dataset = EgoGraphDataset(df, gen.users, gen.merchants, gen.devices)
    graphs = []
    for uid in sorted(df["user_id"].unique()):
        g = dataset.build(uid)
        if g is not None:
            graphs.append((uid, g))
    rng = torch.Generator().manual_seed(args.seed)
    perms = torch.randperm(len(graphs), generator=rng).tolist()
    n_tr = int(len(graphs) * 0.7)
    n_va = int(len(graphs) * 0.15)
    train = [graphs[i][1] for i in perms[:n_tr]]
    val = [graphs[i][1] for i in perms[n_tr:n_tr + n_va]]
    test = [graphs[i][1] for i in perms[n_tr + n_va:]]
    print(f"graphs: train {len(train)} val {len(val)} test {len(test)}")

    from torch_geometric.loader import DataLoader
    train_loader = DataLoader(train, batch_size=1, shuffle=True)
    val_loader = DataLoader(val, batch_size=1, shuffle=False)
    test_loader = DataLoader(test, batch_size=1, shuffle=False)

    gnn = PayShieldGNN(edge_types=EDGE_TYPES, hidden_channels=64, num_layers=2, dropout=0.3)
    gnn.to(device)
    with torch.no_grad():
        warm = train[0].to(device)
        gnn(warm.x_dict, warm.edge_index_dict)

    if args.from_artifact:
        ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
        gnn.load_state_dict(ckpt["state_dict"])
        gnn.to(device)
        best_val = ckpt["metrics"].get("auc_roc", 0.0)
        print(f"loaded artifact {MODEL_PATH} (val AUC {best_val:.4f}, trained {ckpt.get('trained_at', '?')})")
    else:
        t0 = time.time()
        best_val = train_loop(gnn, train_loader, val_loader, device, args.epochs)
        print(f"training done in {round(time.time() - t0, 1)}s (best val AUC {best_val:.4f})")

    val_probs, val_labels = [], []
    gnn.eval()
    with torch.no_grad():
        for g in val_loader:
            g = g.to(device)
            probs = gnn.predict_proba(g.x_dict, g.edge_index_dict)
            val_probs.append(float(probs[0, 0]))
            val_labels.append(int(g.label))
    calibrator = fit_and_save_calibrator(val_probs, val_labels)
    ece_before = expected_calibration_error(val_probs, val_labels)

    test_probs, test_labels = [], []
    with torch.no_grad():
        for g in test_loader:
            g = g.to(device)
            probs = gnn.predict_proba(g.x_dict, g.edge_index_dict)
            test_probs.append(float(probs[0, 0]))
            test_labels.append(int(g.label))
    calibrated_test = [float(calibrator.predict([p])[0]) for p in test_probs]
    ece_after = expected_calibration_error(calibrated_test, test_labels)

    auc_pr = round(average_precision_score(test_labels, test_probs), 4)
    auc_roc = round(roc_auc_score(test_labels, test_probs), 4)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": gnn.state_dict(),
        "hidden_channels": 64, "num_layers": 2, "dropout": 0.3,
        "edge_types": [list(et) for et in EDGE_TYPES],
        "metrics": {"auc_pr": auc_pr, "auc_roc": auc_roc, "ece_before": ece_before, "ece_after": ece_after},
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, MODEL_PATH)

    from ml.registry import ModelRegistry
    registry = ModelRegistry()
    card = {
        "model_version": "0.1.0",
        "architecture": "PayShieldGNN (HeteroConv + SAGEConv)",
        "parameters": gnn.count_parameters(),
        "metrics": {"pr_auc": auc_pr, "auc_roc": auc_roc,
                    "ece_before_calibration": ece_before, "ece_after_calibration": ece_after},
        "calibrator": str(CALIBRATOR_PATH),
        "artifact": str(MODEL_PATH),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_PATH.write_text(json.dumps(card, indent=2))

    print(f"\nmodel saved: {MODEL_PATH}")
    print(f"calibrator saved: {CALIBRATOR_PATH}")
    print(f"PR-AUC {auc_pr} | AUC-ROC {auc_roc} | ECE before {ece_before} -> after {ece_after}")
    print(f"model card: {CARD_PATH}")


if __name__ == "__main__":
    main()
