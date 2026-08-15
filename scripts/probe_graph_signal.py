#!/usr/bin/env python3
"""
Graph-signal probe: quantify the data ceiling for the L2 GNN.

Extracts hand-crafted statistics from each user's ego-graph (mirroring what
the GNN can see) and trains Random Forest / Logistic Regression on them —
no message passing, no learned embeddings. The resulting test PR-AUC is a
probe of how much fraud signal exists in the current graph schema:

  * probe PR-AUC > ~0.4  → the data carries signal the GNN is failing to
    extract (under-fitting / architectural defect) — capacity fixes pay off.
  * probe PR-AUC ≈ GNN PR-AUC (~0.2) → the data itself is the ceiling;
    feature/pattern enrichment (merchant shell flags, velocity, geo) is a
    prerequisite before capacity fixes.

The label matches the GNN benchmark exactly: 1 if the user has any fraud
transaction among their last 10 transactions.

Usage:
    python scripts/probe_graph_signal.py [--users 10000 --merchants 1000
                                         --txns 30000 --seed 42]
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from data.synthetic.generator import SyntheticUPIGenerator

MAX_HISTORY = 10          # mirrors EgoGraphDataset.max_txns
MIN_HISTORY = 3           # mirrors EgoGraphDataset.min_history
MAX_NEIGHBORS = 5         # mirrors EgoGraphDataset.max_neighbors
MAX_MERCHANT_AGE = 1500.0 # mirrors merchant_features() normalizer
MAX_AMOUNT = 20000.0      # mirrors transaction_features() normalizer


def _seconds(ts) -> float:
    return ts.timestamp() if hasattr(ts, "timestamp") else float(ts)


def build_user_stats(df, users, merchants, devices) -> tuple[list[list[float]], list[int]]:
    """Compute per-user feature rows and labels over the last MAX_HISTORY txns.

    Returns (features, labels) aligned by the same user order the GNN
    benchmark uses (any user with >= MIN_HISTORY transactions).
    """
    txn_by_user: dict[str, list] = defaultdict(list)
    for row in df.itertuples(index=False):
        txn_by_user[row.user_id].append(row)
    for uid in txn_by_user:
        txn_by_user[uid].sort(key=lambda r: _seconds(r.timestamp))

    device_users: dict[str, set[str]] = defaultdict(set)
    for uid, txns in txn_by_user.items():
        for r in txns:
            device_users[r.device_fingerprint].add(uid)

    fraud_users = set(df.loc[df["is_fraud"], "user_id"])

    features: list[list[float]] = []
    labels: list[int] = []

    for uid, txns in txn_by_user.items():
        if len(txns) < MIN_HISTORY:
            continue
        txns = txns[-MAX_HISTORY:]
        last_ts = _seconds(txns[-1].timestamp)

        devices_used = {r.device_fingerprint for r in txns}
        merchants_used = {r.merchant_id for r in txns}

        has_emulator = any(bool(devices.get(d, {}).get("is_emulator", False)) for d in devices_used)

        has_shell = any(bool(merchants.get(m, {}).get("is_shell", False)) for m in merchants_used)

        neighbor_fraud = 0
        for d in devices_used:
            for other in device_users.get(d, set()) - {uid}:
                if other in fraud_users:
                    neighbor_fraud += 1
                    if neighbor_fraud >= MAX_NEIGHBORS:
                        break
            if neighbor_fraud >= MAX_NEIGHBORS:
                break

        window_start = last_ts
        vel_5m = sum(1 for r in txns if window_start - _seconds(r.timestamp) <= 300)
        vel_1h = sum(1 for r in txns if window_start - _seconds(r.timestamp) <= 3600)

        amounts = [float(r.amount) for r in txns]
        round_share = sum(1 for a in amounts if a % 100 == 0.0) / len(amounts)

        ages = [float(merchants.get(m, {}).get("account_age_days", 1500.0)) for m in merchants_used]
        min_age = min(ages) if ages else 1500.0
        max_age = max(ages) if ages else 1500.0

        u = users.get(uid, {})
        row_feats = [
            float(has_emulator),
            float(has_shell),
            float(neighbor_fraud),
            vel_5m,
            vel_1h,
            round_share,
            min_age / MAX_MERCHANT_AGE,
            max_age / MAX_MERCHANT_AGE,
            min(sum(amounts) / len(amounts) / MAX_AMOUNT, 1.0),
            (sum((a - sum(amounts) / len(amounts)) ** 2 for a in amounts) / len(amounts)) ** 0.5 / MAX_AMOUNT,
            float(u.get("credit_score", 700.0)) / 900.0,
            min(float(u.get("account_age_days", 365.0)) / 1200.0, 1.0),
            float(u.get("kyc_tier", 1)) / 3.0,
            min(float(u.get("avg_monthly_txn_count", 20.0)) / 100.0, 1.0),
            min(float(u.get("device_count", 1)) / 3.0, 1.0),
        ]
        features.append(row_feats)
        labels.append(1 if any(bool(r.is_fraud) for r in txns) else 0)

    return features, labels


FEATURE_NAMES = [
    "has_emulator_device",
    "has_shell_merchant",
    "num_neighbor_fraud_flags",
    "txn_velocity_5m",
    "txn_velocity_1h",
    "round_amount_share",
    "min_merchant_age",
    "max_merchant_age",
    "mean_amount_10",
    "amount_std_10",
    "credit_score",
    "account_age_days",
    "kyc_tier",
    "avg_monthly_txn_count",
    "device_count",
]


def main():
    ap = argparse.ArgumentParser(description="Quantify the PR-AUC ceiling of the current graph schema")
    ap.add_argument("--users", type=int, default=10000)
    ap.add_argument("--merchants", type=int, default=1000)
    ap.add_argument("--txns", type=int, default=30000)
    ap.add_argument("--fraud-ratio", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default="models/probe_results.json")
    args = ap.parse_args()

    t0 = time.time()
    gen = SyntheticUPIGenerator(
        n_users=args.users, n_merchants=args.merchants,
        n_transactions=args.txns, fraud_ratio=args.fraud_ratio, seed=args.seed,
    )
    df = gen.generate()
    print(f"generated {len(df)} txns ({int(df['is_fraud'].sum())} fraud) in {time.time() - t0:.1f}s")

    features, labels = build_user_stats(df, gen.users, gen.merchants, gen.devices)
    n_pos = sum(labels)
    print(f"samples: {len(labels)} users (positives: {n_pos}, rate {n_pos / len(labels):.3f})")

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=args.seed, stratify=labels,
    )

    results = {"features": FEATURE_NAMES}

    for name, clf in (
        ("rf", RandomForestClassifier(n_estimators=100, random_state=args.seed, n_jobs=-1)),
        ("lr", LogisticRegression(random_state=args.seed, max_iter=2000, class_weight="balanced")),
    ):
        clf.fit(x_train, y_train)
        probs = clf.predict_proba(x_test)[:, 1]
        pr_auc = average_precision_score(y_test, probs)
        roc_auc = roc_auc_score(y_test, probs)
        results[name] = {"pr_auc": round(pr_auc, 4), "roc_auc": round(roc_auc, 4)}
        print(f"{name.upper():>3}: PR-AUC={pr_auc:.4f}  ROC-AUC={roc_auc:.4f}")

    results.update({
        "generated_at": datetime.now(UTC).isoformat(),
        "data": {"users": args.users, "merchants": args.merchants,
                 "transactions": args.txns, "fraud_ratio": args.fraud_ratio, "seed": args.seed},
        "label": "user has any fraud txn in last 10 (same as benchmark_gnn.py)",
        "ceiling_reading": (
            "signal present (probe PR-AUC > 0.4): GNN is under-extracting; architectural fixes will pay"
            if results["rf"]["pr_auc"] > 0.4
            else "data-limited (probe PR-AUC ~<= 0.4): enrich features (shell/velocity/geo) before capacity fixes"
        ),
    })

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nresults saved to {args.output}")


if __name__ == "__main__":
    main()
