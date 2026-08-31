#!/usr/bin/env python3
"""Train XGBoost on LIVE-pipeline features (Option B — close the calibration gap).

The production scorer runs the evaluated 7-feature Stage 1 model on features
computed by ``ReturnRiskFeatureEngine`` from Redis. This script trains a model
on the **exact feature vector the live API computes** — by running the real
feature engine over curated Redis archetype profiles — so the model is
calibrated to the live feature distribution (``device_fingerprint_match`` is
always the neutral 0.5, ``days_since_last_order`` comes from the profile's
``last_activity``, return rates come from the Redis hash, and
``amount_vs_user_aov_ratio`` is clamped to ``[0.15, 4.0]``), rather than to the
offline DGP's independent draws.

Labels are **feature-driven**: the DGP's ``_return_probability`` is applied to
the *live-computed* feature values plus hidden confounders plus label noise, so
the model genuinely has learnable signal — a Bernoulli(user-rate) label would
reproduce the ~0.52 ceiling documented in
``docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md``.

The split and training protocol are identical to
``scripts/train_xgb_return_risk.py``: per-user chronological 60/20/20 and the
same conservative XGBoost hyperparameters, so the numbers are directly
comparable to the DGP model (PR-AUC 0.7991 floor).

Decision gate (from the execution plan):
  test PR-AUC >= 0.7991 -> proceed with Option B (ship this as the production
                            scorer model + full re-anchor)
  test PR-AUC <  0.7900 -> Option A (keep the DGP model, align live features)

Writes:
    models/live_features_results.json   (metrics + operating curve + this doc's decision)
    models/return_risk_xgb_live.json    (the trained model, when --save is set)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.return_risk_generator import (  # noqa: E402
    CATEGORY_BASELINES,
    COD_SHARE,
    LABEL_NOISE_STD,
    RATE30_NOISE,
    RATE90_NOISE,
    _hidden_features,
    _return_probability,
)
from return_risk.feature_engine import ReturnRiskFeatureEngine  # noqa: E402
from scripts.train_xgb_return_risk import (  # noqa: E402
    Dummy,
    HandWeightedScorer,
    chronological_split,
    evaluate,
    operating_curve,
    train_xgb,
)
from tests.fake_redis import FakeRedis  # noqa: E402

FEATURES = [
    "user_return_rate_30d",
    "user_return_rate_90d",
    "amount_vs_user_aov_ratio",
    "category_return_baseline",
    "payment_method_risk",
    "device_fingerprint_match",
    "days_since_last_order",
]

# Live-market archetypes expressed as the Redis profiles the feature engine
# reads. ``latent`` is the user's true propensity (drives the noisy rate
# features and the label); ``aov`` is the per-user average order value.
ARCHETYPES = {
    "honest": {"latent": 0.15, "aov": 65000, "orders": 20, "returns": 3},
    "casual_returner": {"latent": 0.28, "aov": 72000, "orders": 20, "returns": 6},
    "serial_returner": {"latent": 0.48, "aov": 80000, "orders": 20, "returns": 11},
    "fraud_returner": {"latent": 0.62, "aov": 88000, "orders": 20, "returns": 13},
    "new_user": {"latent": 0.24, "aov": 40000, "orders": 2, "returns": 0},
}

_CATEGORY_WEIGHTS = {
    "fashion": 3.0, "electronics": 2.0, "groceries": 1.5, "home": 1.2,
    "beauty": 1.2, "sports": 1.0, "footwear": 1.0, "furniture": 0.6,
}
_PAYMENT_WEIGHTS = {"UPI": 0.55, "CARD": 0.25, "WALLET": 0.10, "NETBANKING": 0.10}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


async def _write_profile(redis, user_id: str, archetype: dict[str, Any], latent: float,
                         order_index: int, order_ts: datetime, rng: random.Random) -> None:
    """Mirror seed_demo_data: a user hash the feature engine reads."""
    await redis.hmset(
        f"return_risk:user:{user_id}",
        {
            "total_orders": str(archetype["orders"]),
            "total_returns": str(archetype["returns"]),
            "return_rate_30d": f"{_clamp(latent + rng.gauss(0.0, RATE30_NOISE), 0.02, 0.90):.4f}",
            "return_rate_90d": f"{_clamp(latent + rng.gauss(0.0, RATE90_NOISE), 0.02, 0.90):.4f}",
            "avg_order_value": str(int(archetype["aov"])),
            "avg_return_value": str(int(archetype["aov"] * 0.4)),
            "cod_refusals": "1",
            "cod_orders": "3",
        },
    )
    # Per-order recency: the first order has no prior activity (live default
    # -> days_since 60); later orders carry a realistic inter-order gap (the
    # live engine reads last_activity from the profile, relative to this order).
    if order_index > 0:
        gap = int(min(rng.expovariate(1 / 12.0), 60))
        await redis.hmset(
            f"return_risk:user:{user_id}",
            {"last_activity": (order_ts - timedelta(days=gap)).isoformat()},
        )


async def _seed_merchant(redis, merchant_id: str) -> None:
    await redis.hmset(f"return_risk:merchant:{merchant_id}", {"return_rate_30d": "0.25"})
    await redis.zadd(
        f"return_risk:merchant:{merchant_id}:category",
        {cat: float(base) for cat, base in CATEGORY_BASELINES.items() if cat != "default"},
    )


def _payment_method(rng: random.Random) -> tuple[str, bool]:
    if rng.random() < COD_SHARE:
        return "COD", True
    return rng.choices(list(_PAYMENT_WEIGHTS), weights=list(_PAYMENT_WEIGHTS.values()))[0], False


async def _live_features_async(engine, user_id: str, merchant_id: str, category: str,
                               amount: float, cod_flag: bool, ts: datetime, method: str) -> dict[str, float]:
    feats = await engine.extract_features(
        user_id=user_id, merchant_id=merchant_id, category=category,
        amount=amount, cod_flag=cod_flag, timestamp=ts, payment_method=method,
    )

    def _v(name: str) -> float:
        return float(feats[name]["value"])

    return {
        "user_return_rate_30d": _v("user_return_rate_30d"),
        "user_return_rate_90d": _v("user_return_rate_90d"),
        "amount_vs_user_aov_ratio": _v("txn_amount_vs_user_aov_ratio"),
        "category_return_baseline": _v("txn_category_return_baseline"),
        "payment_method_risk": _v("txn_payment_method_risk"),
        "device_fingerprint_match": _v("txn_device_fingerprint_match"),
        "days_since_last_order": _v("txn_days_since_last_order"),
    }


def _label(features: dict[str, float], latent: float, rng: random.Random) -> int:
    hidden = _hidden_features(rng)
    p = _return_probability(features, latent, hidden, noise=rng.gauss(0.0, LABEL_NOISE_STD))
    return 1 if rng.random() < p else 0


def generate_dataset(n_orders: int = 10000, seed: int = 42) -> pd.DataFrame:
    """Build a flat table whose seven features are EXACTLY the live pipeline's."""
    rng = random.Random(seed)
    redis = FakeRedis()
    engine = ReturnRiskFeatureEngine(redis)

    async def _generate() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        user_counter = 0
        categories = [c for c in CATEGORY_BASELINES if c != "default"]
        end = datetime.utcnow() - timedelta(days=7)
        while len(rows) < n_orders:
            utype = rng.choices(list(ARCHETYPES), weights=[1.0] * len(ARCHETYPES))[0]
            archetype = ARCHETYPES[utype]
            user_counter += 1
            user_id = f"U_{user_counter:05d}"
            merchant_id = f"M_{utype}"
            latent = _clamp(rng.gauss(archetype["latent"], 0.05), 0.02, 0.85)
            await _seed_merchant(redis, merchant_id)

            for i in range(archetype["orders"]):
                if len(rows) >= n_orders:
                    break
                ts = end - timedelta(days=2 * i + rng.randint(0, 1))
                await _write_profile(redis, user_id, archetype, latent, i, ts, rng)
                category = rng.choices(categories, weights=[_CATEGORY_WEIGHTS[c] for c in categories])[0]
                method, cod_flag = _payment_method(rng)
                ratio = _clamp(math.exp(rng.gauss(0.0, 0.5)), 0.15, 4.0)
                amount = float(archetype["aov"]) * ratio

                live = await _live_features_async(engine, user_id, merchant_id, category, amount, cod_flag, ts, method)
                returned = _label(live, latent, rng)

                rows.append({
                    "user_id": user_id,
                    "merchant_id": merchant_id,
                    "order_id": f"ORD_{user_id}_{i:03d}",
                    "category": category,
                    "amount": round(amount, 2),
                    "payment_method": method,
                    "timestamp": ts,
                    "returned": returned,
                    **live,
                })
        return rows

    return pd.DataFrame(asyncio.run(_generate()))


def _print_feature_diagnostics(df: pd.DataFrame) -> None:
    print("  LIVE-feature diagnostics (should match the real pipeline's ranges):")
    for f in FEATURES:
        col = df[f]
        print(f"    {f:<28} min={col.min():.3f}  mean={col.mean():.3f}  max={col.max():.3f}")


def run(n_orders: int = 10000, seed: int = 42, gate: float = 0.50, save: bool = False) -> tuple:
    print("\n" + "=" * 70)
    print("PayShield Return-Risk | LIVE-feature pipeline (Option B)")
    print("=" * 70)
    print(f"  features={len(FEATURES)}  seed={seed}  orders={n_orders}")

    full_df = generate_dataset(n_orders=n_orders, seed=seed)
    print(f"  base rate={full_df['returned'].mean():.3f}  rows={len(full_df)}")
    _print_feature_diagnostics(full_df)

    print("Splitting (60/20/20, per-user chronological)...")
    train_df, val_df, test_df = chronological_split(full_df)
    print(f"  Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")

    print("Training XGBoost (default hyperparameters) on LIVE features...")
    # The live distribution is near-balanced (~49% base rate), so the DGP
    # trainer's scale_pos_weight=2.0 default is inappropriate — pass 1.0.
    model = train_xgb(train_df, val_df, FEATURES, seed=seed, scale_pos_weight=1.0)

    print("Evaluating XGBoost...")
    xgb_results = evaluate(model, test_df, FEATURES, gate=gate)
    xgb_results["name"] = "XGBoost (live features)"
    xgb_results["feature_importance"] = dict(zip(FEATURES, model.feature_importances_.tolist(), strict=True))

    print("Evaluating hand-weighted baseline...")
    hw = HandWeightedScorer(scenario="basic")
    hw_scores = test_df.apply(lambda r: hw.score(r.to_dict())["score"], axis=1).values
    hw_result = evaluate(Dummy(hw_scores), test_df, FEATURES, gate=gate)
    hw_result["name"] = "Hand-weighted (current)"

    pr_auc = xgb_results["pr_auc"]
    print(f"\n  >>> HELD-OUT TEST PR-AUC: {pr_auc:.4f}  (gate: >= 0.7991 -> Option B, < 0.79 -> Option A)")
    decision = "Option B — ship live-features model + full re-anchor" if pr_auc >= 0.7991 else (
        "Option A — keep DGP model, align live features"
    )
    print(f"  >>> DECISION: {decision}")

    op_curve = operating_curve(model, test_df, FEATURES)
    payload = {
        "name": "live-features",
        "gate": gate,
        "seed": seed,
        "n_orders": n_orders,
        "features": FEATURES,
        "base_rate": float(full_df["returned"].mean()),
        "test_pr_auc": float(pr_auc),
        "test_roc_auc": float(xgb_results["roc_auc"]),
        "decision_gate": 0.7991,
        "decision": decision,
        "operating_curve": op_curve,
        "models": [xgb_results, hw_result],
    }
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    with open(models_dir / "live_features_results.json", "w") as f:
        json.dump(payload, f, indent=2)
    if save:
        model.save_model(str(models_dir / "return_risk_xgb_live.json"))
        print("Saved: models/return_risk_xgb_live.json")
    print("Saved: models/live_features_results.json")
    return model, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train XGBoost on live-pipeline features")
    parser.add_argument("--n-orders", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gate", type=float, default=0.50)
    parser.add_argument("--save", action="store_true", help="also write models/return_risk_xgb_live.json")
    args = parser.parse_args()
    run(n_orders=args.n_orders, seed=args.seed, gate=args.gate, save=args.save)


if __name__ == "__main__":
    main()
