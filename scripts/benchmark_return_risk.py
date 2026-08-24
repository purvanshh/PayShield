#!/usr/bin/env python3
"""Return-risk scorer benchmark (Track 02 - Phase 19).

Measures precision, recall, F1, PR-AUC and ROC-AUC of the return-risk
scorer against synthetic ground truth, following the hold-out pattern used
for the GNN benchmark (scripts/benchmark_gnn.py):

- dataset: 100 users per archetype x 20 orders = 10,000 orders (seed 42);
- split: chronological per user - the first 80% of a user's orders seed the
  profile window, the remaining 20% are scored as held-out orders (a user
  an order score must never use future returns);
- labels: ``high_risk`` = serial_returner / fraud_returner archetype;
- positive class = risk tier HIGH (threshold 0.7).

Runs fully hermetic against an in-memory Redis by default (``--redis`` to
use the live store instead).

Usage:
    python scripts/benchmark_return_risk.py
    python scripts/benchmark_return_risk.py --redis --users-per-type 100
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_scorer(redis):
    from return_risk.feature_engine import ReturnRiskFeatureEngine
    from return_risk.rules_engine import RulesEngine
    from return_risk.scorer import ReturnRiskScorer

    return ReturnRiskScorer(
        feature_engine=ReturnRiskFeatureEngine(redis),
        rules_engine=RulesEngine(),
    )


async def _seed_train(redis, users, orders, labels):  # noqa: ARG001 - seeded window implies labels
    """Seed user/merchant profiles from the training window only."""
    by_user: dict[str, list] = {}
    for order in orders:
        by_user.setdefault(order["user_id"], []).append(order)

    for user in users:
        train_orders = by_user.get(user["user_id"], [])
        total_orders = len(train_orders)
        total_returns = sum(1 for o in train_orders if o["returned"])
        return_rate = total_returns / total_orders if total_orders else 0.0

        user_key = f"return_risk:user:{user['user_id']}"
        await redis.hmset(
            user_key,
            {
                "total_orders": str(total_orders),
                "total_returns": str(total_returns),
                "return_rate_30d": str(round(return_rate, 4)),
                "return_rate_90d": str(round(return_rate, 4)),
                "avg_return_value": str(user["avg_order_value"]),
                "serial_returner": str(return_rate > 0.50 and total_orders >= 3).lower(),
            },
        )
        return_key = f"return_risk:user:{user['user_id']}:returns"
        velocity = {}
        for order in train_orders:
            if order["returned"] and order["return_date"]:
                velocity[order["order_id"]] = datetime.fromisoformat(order["return_date"]).timestamp()
        if velocity:
            await redis.zadd(return_key, velocity)


async def _run(args) -> dict:
    from data.synthetic.return_generator import ReturnRiskSyntheticGenerator
    from tests.fake_redis import FakeRedis

    generator = ReturnRiskSyntheticGenerator(seed=args.seed)
    print("[1/5] Generating synthetic dataset (10k orders)...")
    dataset = generator.generate_dataset(
        num_users_per_type=args.users_per_type, orders_per_user=args.orders_per_user
    )
    users, orders, labels = dataset["users"], dataset["orders"], dataset["labels"]

    train_orders, test_orders, test_users = _chronological_split(orders)
    print(f"  users={len(users)} train_orders={len(train_orders)} test_orders={len(test_orders)}")

    redis = FakeRedis() if not args.redis else _live_redis()
    print("[2/5] Seeding user profiles from the training window...")
    await _seed_train(redis, users, train_orders, labels)

    merchant_rates = {}
    for merchant in dataset["merchants"]:
        merchant_key = f"return_risk:merchant:{merchant['merchant_id']}"
        await redis.hmset(merchant_key, {"return_rate_30d": str(merchant["return_rate"])})
        await redis.zadd(
            f"return_risk:merchant:{merchant['merchant_id']}:category",
            {merchant["category"]: merchant["return_rate"]},
        )
        merchant_rates[merchant["merchant_id"]] = merchant["return_rate"]

    scorer = _make_scorer(redis)
    # Review gate is config-driven: configs/return_risk_rules.yaml sets
    # ``operating_point.medium_review_threshold`` (0.50 on high-return
    # verticals, 0.30-0.35 on low-return ones).
    medium_threshold = float(
        scorer.rules_engine.operating_point.get("medium_review_threshold", 0.30)
    )
    print("[3/5] Scoring held-out orders...")
    scores, truths, preds = [], [], []
    for order in test_orders:
        result = await scorer.score(
            user_id=order["user_id"],
            merchant_id=order["merchant_id"],
            order_id=order["order_id"],
            amount=Decimal(str(order["amount"])),
            category=order["category"],
            cod_flag=order["cod_flag"],
            timestamp=datetime.fromisoformat(order["order_date"]),
        )
        scores.append(result["return_risk_score"])
        truths.append(1 if labels[order["order_id"]]["high_risk"] else 0)
        preds.append(1 if result["risk_tier"] == "HIGH" else 0)

    y_true = np.array(truths)
    y_scores = np.array(scores)
    y_pred = np.array(preds)

    print("[4/5] Computing metrics...")
    metrics = {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_scores)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_scores)), 4),
        "num_positive": int(sum(y_true)),
        "num_negative": int(len(y_true) - sum(y_true)),
        "positive_rate": float(round(sum(y_true) / max(1, len(y_true)), 4)),
    }

    y_pred_medium = (y_scores > medium_threshold).astype(int)  # MEDIUM+ = flag/review action
    metrics["medium_or_higher"] = {
        "threshold": round(medium_threshold, 2),
        "precision": round(float(precision_score(y_true, y_pred_medium, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred_medium, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred_medium, zero_division=0)), 4),
    }
    print(
        f"  HIGH(op 0.7): P={metrics['precision']:.4f} R={metrics['recall']:.4f} "
        f"F1={metrics['f1']:.4f} PR-AUC={metrics['pr_auc']:.4f} ROC-AUC={metrics['roc_auc']:.4f}"
    )
    medium = metrics["medium_or_higher"]
    print(
        f"  MEDIUM+(op {medium_threshold:.2f}): P={medium['precision']:.4f} R={medium['recall']:.4f} "
        f"F1={medium['f1']:.4f}"
    )

    analysis = _false_positive_analysis(test_orders, labels, y_pred, y_scores)
    tier_distribution = Counter(
        "HIGH" if s > 0.7 else "MEDIUM" if s > medium_threshold else "LOW" for s in scores
    )
    print("[5/5] Saving results...")
    results = {
        "benchmark_type": "return_risk",
        "timestamp": datetime.utcnow().isoformat(),
        "dataset": {
            "total_orders": len(orders),
            "train_orders": len(train_orders),
            "test_orders": len(test_orders),
            "positive_rate": metrics["positive_rate"],
        },
        "metrics": metrics,
        "thresholds_note": f"HIGH tier threshold 0.7 (block/prepaid); "
        f"MEDIUM+ review gate {medium_threshold:.2f} (config-driven "
        f"operating_point.medium_review_threshold) - both reported honestly",
        "tier_distribution_on_test": dict(tier_distribution),
        "false_positive_analysis": analysis,
        "config": {"feature_weights": scorer.weights, "risk_tiers": scorer.risk_tiers},
    }
    import asyncio
    import pathlib

    def _save_results():
        pathlib.Path("models").mkdir(exist_ok=True)
        with open("models/return_risk_benchmark_results.json", "w") as f:
            json.dump(results, f, indent=2)

    await asyncio.to_thread(_save_results)
    print("  Results saved to models/return_risk_benchmark_results.json")
    print("=" * 60)
    return metrics


def _chronological_split(orders):
    """80/20 chronological split per user (train profile, score the rest)."""
    by_user: dict[str, list[dict]] = {}
    for order in orders:
        by_user.setdefault(order["user_id"], []).append(order)

    train, test = [], []
    test_user_ids = set()
    for user_orders in by_user.values():
        user_orders.sort(key=lambda o: o["order_date"])
        split = max(1, int(len(user_orders) * 0.8))
        train.extend(user_orders[:split])
        for o in user_orders[split:]:
            test.append(o)
            test_user_ids.add(o["user_id"])
    return train, test, test_user_ids


def _false_positive_analysis(test_orders, labels, y_pred, y_scores):  # noqa: ARG001 - labels companion window
    """Breakdown of misclassified orders by user archetype (honesty section)."""
    misclassified = Counter()
    false_positives = Counter()
    for i, order in enumerate(test_orders):
        label = labels[order["order_id"]]
        user_type = label["user_type"]
        if label["high_risk"] and y_pred[i] != 1:
            misclassified[f"false_negative:{user_type}"] += 1
        elif not label["high_risk"] and y_pred[i] == 1:
            false_positives[f"false_positive:{user_type}"] += 1
    return {
        "false_negatives_by_user_type": dict(misclassified),
        "false_positives_by_user_type": dict(false_positives),
        "note": "serial/fraud returners scored below HIGH are misses; "
        "casual/new users scored HIGH are false positives",
    }


def _live_redis():
    from store.redis_client import create_redis

    return create_redis(mode="async")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", action="store_true", help="use a live Redis store")
    parser.add_argument("--users-per-type", type=int, default=100)
    parser.add_argument("--orders-per-user", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import asyncio

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
