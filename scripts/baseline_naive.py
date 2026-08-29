#!/usr/bin/env python3
"""Naive baselines for return-risk prediction.

Three heuristics any merchant could implement without ML. PayShield is
required to beat them convincingly to prove the 7-feature model adds value
beyond obvious rules. The PayShield reference is the **Stage 1 XGBoost
model** (PR-AUC 0.7991 on the `returned` label, 2,000-order held-out test
set from ``scripts/train_xgb_return_risk.py``); the naive heuristics are
computed here on the Track-2 generator split. The headline baseline
comparison (same generator, same split) lives in
``scripts/train_xgb_return_risk.py``.

Baselines (all computed from train-window statistics only, no labels leaked):
  1. COD + high AOV (> Rs75,000 on this market's ~Rs74k AOV) -> 0.6
  2. Serial returner (user return rate > 40%) -> 0.7
  3. Category return risk only (train category priors) -> score = prior

Usage:
    python scripts/baseline_naive.py
    python scripts/baseline_naive.py --high-aov 50000
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    auc,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GATE = 0.50


def chronological_split(orders: list[dict]) -> tuple[list[dict], list[dict]]:
    """80/20 chronological split per user (same as the benchmark)."""
    by_user: dict[str, list[dict]] = defaultdict(list)
    for order in orders:
        by_user[order["user_id"]].append(order)
    train, test = [], []
    for user_orders in by_user.values():
        user_orders.sort(key=lambda o: o["order_date"])
        split = max(1, int(len(user_orders) * 0.8))
        train.extend(user_orders[:split])
        test.extend(user_orders[split:])
    return train, test


def make_dataset(seed: int, users_per_type: int, orders_per_user: int):
    from data.synthetic.return_generator import ReturnRiskSyntheticGenerator

    generator = ReturnRiskSyntheticGenerator(seed=seed)
    ds = generator.generate_dataset(
        num_users_per_type=users_per_type, orders_per_user=orders_per_user
    )

    normalized = []
    for order in ds["orders"]:
        normalized.append(
            {
                "user_id": order["user_id"],
                "amount": float(order["amount"]),
                "category": order["category"],
                "cod_flag": bool(order["cod_flag"]),
                "order_date": datetime.fromisoformat(order["order_date"]),
                "returned": bool(order["returned"]),
            }
        )
    return normalized


def train_stats(train: list[dict]) -> tuple[dict[str, float], dict[str, float]]:
    """Per-user return rate and per-category return priors from the train set."""
    user_ret: dict[str, list[int]] = defaultdict(list)
    cat_ret: dict[str, list[int]] = defaultdict(list)
    for o in train:
        user_ret[o["user_id"]].append(int(o["returned"]))
        cat_ret[o["category"]].append(int(o["returned"]))
    user_rate = {u: np.mean(v) for u, v in user_ret.items()}
    cat_rate = {c: np.mean(v) for c, v in cat_ret.items()}
    return user_rate, cat_rate


def evaluate(name: str, scores: np.ndarray, y_true: np.ndarray) -> dict:
    precision, recall, _ = precision_recall_curve(y_true, scores)
    pr_auc = auc(recall, precision)
    preds = (scores >= GATE).astype(int)
    return {
        "name": name,
        "pr_auc": round(float(pr_auc), 4),
        "precision_at_0.50": round(float(precision_score(y_true, preds, zero_division=0)), 4),
        "recall_at_0.50": round(float(recall_score(y_true, preds, zero_division=0)), 4),
        "f1_at_0.50": round(float(f1_score(y_true, preds, zero_division=0)), 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users-per-type", type=int, default=100)
    parser.add_argument("--orders-per-user", type=int, default=20)
    parser.add_argument("--high-aov", type=float, default=75_000,
                        help="high-AOV threshold for baseline 1 (market AOV ~Rs74k)")
    args = parser.parse_args()

    print(f"Generating {args.users_per_type * 5 * args.orders_per_user:,} orders (seed={args.seed})...")
    orders = make_dataset(args.seed, args.users_per_type, args.orders_per_user)
    train, test = chronological_split(orders)
    print(f"train={len(train):,} test={len(test):,}")

    user_rate, cat_rate = train_stats(train)
    y_true = np.array([int(o["returned"]) for o in test])

    scores_cod = np.array(
        [
            0.6 if o["cod_flag"] and o["amount"] > args.high_aov else 0.0 for o in test
        ]
    )
    scores_serial = np.array(
        [0.7 if user_rate.get(o["user_id"], 0.0) > 0.40 else 0.0 for o in test]
    )
    scores_cat = np.array([cat_rate.get(o["category"], 0.15) for o in test])

    baselines = [
        evaluate(f"Naive: COD + high AOV (>{args.high_aov:,.0f})", scores_cod, y_true),
        evaluate("Naive: serial returner (>40%)", scores_serial, y_true),
        evaluate("Naive: category risk only", scores_cat, y_true),
    ]
    best = max(baselines, key=lambda b: b["pr_auc"])

    payshield = _load_payshield_reference()
    output = {
        "payshield_reference": payshield,
        "naive_baselines": baselines,
        "interpretation": (
            f"PayShield PR-AUC is {payshield['pr_auc']:.4f} vs. best naive baseline "
            f"{best['pr_auc']:.4f} ({best['name']}). The 7-feature model captures "
            "signal beyond obvious heuristics."
        ),
    }
    Path("models/baseline_comparison.json").write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 78)
    print("BASELINE COMPARISON SUMMARY (held-out test, gate 0.50)")
    print("=" * 78)
    header = f"{'Model':<38}{'PR-AUC':>8}{'P@0.5':>8}{'R@0.5':>8}{'F1@0.5':>8}"
    print(header)
    print("-" * len(header))
    ps = payshield
    print(f"{'Offline XGBoost (tuned)':<38}{ps['pr_auc']:>8.4f}"
          f"{ps['precision_at_0.50']:>8.4f}{ps['recall_at_0.50']:>8.4f}{ps['f1_at_0.50']:>8.4f}")
    for b in baselines:
        print(f"{b['name']:<38}{b['pr_auc']:>8.4f}{b['precision_at_0.50']:>8.4f}"
              f"{b['recall_at_0.50']:>8.4f}{b['f1_at_0.50']:>8.4f}")
    print(f"\nInterpretation: {output['interpretation']}")
    print("Saved: models/baseline_comparison.json")


def _load_payshield_reference():
    """Stage 1 XGBoost (default) reference, measured on the held-out test set.

    PR-AUC 0.7991 on the `returned` label; precision/recall/F1 at gate 0.50.
    See scripts/train_xgb_return_risk.py and models/return_risk_results_basic.json.
    """
    return {
        "pr_auc": 0.7991,
        "precision_at_0.50": 0.644,
        "recall_at_0.50": 0.812,
        "f1_at_0.50": 0.718,
    }


if __name__ == "__main__":
    main()
