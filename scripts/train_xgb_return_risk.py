#!/usr/bin/env python3
"""Train an XGBoost return-risk model and evaluate against naive baselines.

Phase 1 of the return-risk ML pipeline. Run this first; ablation and tuning
depend on its conventions (the per-user chronological split, the hand-weighted
baseline and the ``--scenario`` DGP dispatch).

Progressive Merchant Maturity scenarios (``--scenario``):
    basic    : Stage 1 - 7 visible features, HIDDEN_SCALE=26, noise=0.10 (floor).
    enriched : Stage 2 - 9 visible features (rating + delivery observed),
               HIDDEN_SCALE=18, noise=0.08.
    premium  : Stage 3 - 9 visible features, HIDDEN_SCALE=10, noise=0.05.

The split, model architecture and evaluation protocol are IDENTICAL across
scenarios; only the data source changes. ROC-AUC is *measured* via
``roc_auc_score`` (never hardcoded) - fixing Mistake 1 from
``MISTAKES_AND_LEARNINGS.md``.

Writes:
    models/return_risk_xgb_v1.json            (basic, default-hyperparameter model)
    models/xgb_evaluation.json                (basic, 4-model comparison - kept for compat)
    models/return_risk_results_{scenario}.json (per-scenario metrics + operating curve)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    auc,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic import (
    return_risk_generator,
    return_risk_generator_enriched,
    return_risk_generator_premium,
)

# Scenario -> (generator module, default seed). Seed 99 stays reserved for the
# independent hold-out used by ``scripts/ablation_study.py`` (constraint 6).
SCENARIOS = {
    "basic": (return_risk_generator, 42),
    "enriched": (return_risk_generator_enriched, 42),
    "premium": (return_risk_generator_premium, 123),
}

# --------------------------------------------------------------------------- #
# Hand-weighted scorer (production-style baseline). Mirrors the weights in
# return_risk/scorer.FEATURE_WEIGHTS mapped onto the seven model features so
# the "current production approach" comparison is fair and referenceable.
# --------------------------------------------------------------------------- #


class HandWeightedScorer:
    """Weighted, normalised sum over the visible features (no ML).

    Weights are the production composite weights re-mapped onto the model's
    feature surface. Features are normalised to [0,1] the same way the
    production scorer normalises before weighting (device match is inverted:
    a *match* is low risk). For the enriched/premium scenarios the two
    newly-observed features (product_rating, delivery_speed_days) get their own
    weights, renormalised so the weights still sum to 1 - keeping the baseline
    comparison fair across scenarios.
    """

    # Stage 1 weights (7 features, sum=1.0).
    WEIGHTS_BASIC = {
        "user_return_rate_30d": 0.25,
        "user_return_rate_90d": 0.20,
        "amount_vs_user_aov_ratio": 0.10,
        "category_return_baseline": 0.15,
        "payment_method_risk": 0.10,
        "device_fingerprint_match": 0.10,
        "days_since_last_order": 0.10,
    }
    # Stage 2/3 weights (9 features, sum=1.0). The two new features take a
    # share proportional to their signal; the rest are scaled down to compensate.
    WEIGHTS_ENRICHED = {
        "user_return_rate_30d": 0.20,
        "user_return_rate_90d": 0.16,
        "amount_vs_user_aov_ratio": 0.08,
        "category_return_baseline": 0.12,
        "payment_method_risk": 0.08,
        "device_fingerprint_match": 0.08,
        "days_since_last_order": 0.08,
        "product_rating": 0.12,
        "delivery_speed_days": 0.08,
    }

    def __init__(self, scenario: str = "basic") -> None:
        self.weights = (
            self.WEIGHTS_ENRICHED if scenario in ("enriched", "premium") else self.WEIGHTS_BASIC
        )
        assert abs(sum(self.weights.values()) - 1.0) < 1e-9

    def _normalize(self, feature: str, value: float) -> float:
        v = float(value)
        if feature == "device_fingerprint_match":
            return 1.0 - min(1.0, max(0.0, v))
        if feature == "days_since_last_order":
            return min(1.0, v / 45.0)
        if feature == "amount_vs_user_aov_ratio":
            return min(1.0, max(0.0, v - 1.0))
        if feature == "product_rating":
            return (5.0 - min(5.0, max(1.0, v))) / 4.0
        if feature == "delivery_speed_days":
            return min(1.0, max(0.0, (v - 1.0) / 6.0))
        return min(1.0, max(0.0, v))

    def score(self, row: dict) -> dict:
        total = sum(self.weights[f] * self._normalize(f, row[f]) for f in self.weights)
        return {"score": float(min(1.0, max(0.0, total)))}


# --------------------------------------------------------------------------- #
# Data handling
# --------------------------------------------------------------------------- #


def chronological_split(df: pd.DataFrame, train_frac: float = 0.6, val_frac: float = 0.2):
    """Per-user chronological 60/20/20 split. No future-data leakage.

    Each user's orders are sorted by time; the first 60% train, next 20%
    validate, last 20% test. A user's validation/test orders always come
    after all of their training orders.
    """
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []
    for _, user_df in df.groupby("user_id", sort=False):
        n = len(user_df)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        positions = user_df.index.tolist()
        train_idx.extend(positions[:n_train])
        val_idx.extend(positions[n_train : n_train + n_val])
        test_idx.extend(positions[n_train + n_val :])
    return df.loc[train_idx], df.loc[val_idx], df.loc[test_idx]


# --------------------------------------------------------------------------- #
# Training / evaluation
# --------------------------------------------------------------------------- #


def train_xgb(train_df: pd.DataFrame, val_df: pd.DataFrame, features: list[str], seed: int = 42,
              scale_pos_weight: float = 2.0):
    """Train with conservative hyperparameters to prevent overfitting.

    ``features`` is passed in (7 for basic, 9 for enriched/premium) so the same
    trainer serves every scenario. ``scale_pos_weight`` defaults to 2.0 (the
    DGP scenarios are minority-positive at ~40-42% base rate); the live-features
    trainer passes 1.0 because its distribution is near-balanced (~49%).
    """
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        random_state=seed,
        n_jobs=8,
        tree_method="hist",
        eval_metric="logloss",
        early_stopping_rounds=20,
    )
    model.fit(
        train_df[features],
        train_df["returned"],
        eval_set=[(val_df[features], val_df["returned"])],
        verbose=False,
    )
    return model


def evaluate(model, test_df: pd.DataFrame, features: list[str], gate: float = 0.50) -> dict:
    """Unified evaluation: PR-AUC, ROC-AUC, AP, precision/recall/F1 at gate, CM.

    ``model`` must expose ``predict_proba`` (an XGBClassifier or the Dummy
    wrapper used for baselines). ``features`` is the model's feature surface
    (7 for basic, 9 for enriched/premium) - passed explicitly so the same
    function serves every scenario.

    PR-AUC is computed two ways: trapezoidal ``auc(r, p)`` (kept for continuity
    with the published 0.8067 floor) and ``average_precision_score`` (the
    stepwise form). ROC-AUC is measured via ``roc_auc_score`` - never hardcoded.
    """
    x_test = test_df[features]
    y_true = test_df["returned"].values
    scores = model.predict_proba(x_test)[:, 1]

    p_curve, r_curve, _ = precision_recall_curve(y_true, scores)
    pr_auc = auc(r_curve, p_curve)
    ap = average_precision_score(y_true, scores)
    roc_auc = roc_auc_score(y_true, scores)

    y_pred = (scores >= gate).astype(int)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "pr_auc": float(pr_auc),
        "average_precision": float(ap),
        "roc_auc": float(roc_auc),
        "precision_at_gate": float(prec),
        "recall_at_gate": float(rec),
        "f1_at_gate": float(f1),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def operating_curve(model, test_df: pd.DataFrame, features: list[str], gates: list[float] | None = None) -> dict:
    """Flag-rate / precision / recall at each gate - consumed by the cost model.

    Replaces the hardcoded ``_XGB_OPERATING_CURVE`` in the cost calculator so
    the ₹ figures track the *measured* model, not a stale constant. Each entry:
    ``{flag_rate, precision, recall}`` computed at the gate threshold on the
    held-out test set.
    """
    gates = gates or [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70]
    scores = model.predict_proba(test_df[features])[:, 1]
    y_true = test_df["returned"].values
    curve: dict[str, dict] = {}
    for g in gates:
        y_pred = (scores >= g).astype(int)
        n = len(y_true)
        flagged = int(y_pred.sum())
        tp = int(((y_pred == 1) & (y_true == 1)).sum())
        fn = int(((y_pred == 0) & (y_true == 1)).sum())
        pos = int(y_true.sum())
        flag_rate = flagged / n if n else 0.0
        precision = tp / flagged if flagged else 0.0
        recall = tp / pos if pos else 0.0
        curve[f"{g:.2f}"] = {
            "flag_rate": round(flag_rate, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }
    return curve


class Dummy:
    """Wraps a constant/rule score vector as a predict_proba model."""

    def __init__(self, scores: np.ndarray):
        self.scores = np.asarray(scores, dtype=float)

    def predict_proba(self, X) -> np.ndarray:  # noqa: N803, ARG002
        s = np.clip(self.scores, 0.0, 1.0)
        return np.column_stack([1.0 - s, s])


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #


def run(scenario: str = "basic", n_orders: int = 10000, gate: float = 0.50) -> tuple:
    """Generate -> split -> train -> evaluate -> save for one scenario."""
    gen_module, default_seed = SCENARIOS[scenario]
    features = list(gen_module.FEATURES)
    seed = default_seed

    print(f"\n{'=' * 70}")
    print(f"PayShield Return-Risk Scorer | Stage: {scenario}")
    print(f"{'=' * 70}")
    meta = gen_module.get_scenario_metadata() if hasattr(gen_module, "get_scenario_metadata") else {
        "stage": scenario, "visible_features": features, "num_features": len(features),
        "hidden_scale": None, "label_noise_std": None, "seed": seed,
    }
    print(f"  features={len(features)}  seed={seed}  target_pr_auc={meta.get('target_pr_auc', '~0.81')}")

    print(f"Generating {n_orders} orders (scenario={scenario}, seed={seed})...")
    full_df = gen_module.generate_return_risk_dataset(n_orders=n_orders, seed=seed)
    print(f"  base rate={full_df['returned'].mean():.3f}  rows={len(full_df)}")

    print("Splitting (60/20/20, per-user chronological)...")
    train_df, val_df, X_test_labelled = chronological_split(full_df)
    print(f"  Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(X_test_labelled)}")

    print("Training XGBoost (default hyperparameters)...")
    model = train_xgb(train_df, val_df, features, seed=seed)

    print("Evaluating XGBoost...")
    xgb_results = evaluate(model, X_test_labelled, features, gate=gate)
    xgb_results["name"] = "XGBoost (default)"
    xgb_results["feature_importance"] = dict(zip(features, model.feature_importances_.tolist(), strict=True))

    print("Evaluating hand-weighted baseline...")
    hw = HandWeightedScorer(scenario=scenario)
    hw_scores = X_test_labelled.apply(lambda r: hw.score(r.to_dict())["score"], axis=1).values
    hw_result = evaluate(Dummy(hw_scores), X_test_labelled, features, gate=gate)
    hw_result["name"] = "Hand-weighted (current)"

    print("Evaluating naive baselines...")
    s1 = np.zeros(len(X_test_labelled))
    mask = (
        (X_test_labelled["payment_method"] == "COD")
        & (X_test_labelled["amount"] > 3000)
        & (X_test_labelled["category"].isin(["fashion", "beauty"]))
    )
    s1[mask] = 0.6
    b1 = evaluate(Dummy(s1), X_test_labelled, features, gate=gate)
    b1["name"] = "Naive: COD+HighAOV"

    s2 = (X_test_labelled["user_return_rate_90d"] > 0.4).astype(float).values * 0.7
    b2 = evaluate(Dummy(s2), X_test_labelled, features, gate=gate)
    b2["name"] = "Naive: SerialReturner"

    all_results = [xgb_results, hw_result, b2, b1]
    _print_results(all_results, scenario=scenario)

    print(f"\n{'=' * 70}")
    print("XGBoost FEATURE IMPORTANCE")
    print("=" * 70)
    for feat, imp in sorted(xgb_results["feature_importance"].items(), key=lambda kv: -kv[1]):
        print(f"  {feat}: {imp:.4f}")

    # Operating curve for the cost model (replaces the hardcoded constant).
    op_curve = operating_curve(model, X_test_labelled, features)

    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    # Per-scenario results (new - never overwrites other scenarios).
    scenario_payload = {
        "scenario": scenario,
        "gate": gate,
        "seed": seed,
        "n_orders": n_orders,
        "scenario_metadata": meta,
        "base_rate": float(full_df["returned"].mean()),
        "num_features": len(features),
        "features": features,
        "operating_curve": op_curve,
        "models": all_results,
    }
    with open(models_dir / f"return_risk_results_{scenario}.json", "w") as f:
        json.dump(scenario_payload, f, indent=2)

    # Backward-compatible artifacts for the basic scenario only.
    if scenario == "basic":
        model.save_model(str(models_dir / "return_risk_xgb_v1.json"))
        with open(models_dir / "xgb_evaluation.json", "w") as f:
            json.dump({"gate": gate, "models": all_results}, f, indent=2)
        print("\nSaved: models/return_risk_xgb_v1.json, models/xgb_evaluation.json")
    print(f"Saved: models/return_risk_results_{scenario}.json")
    return model, all_results, scenario_payload


def _print_results(all_results: list[dict], scenario: str = "basic") -> None:
    print(f"\n{'=' * 70}")
    print(f"RESULTS (Stage: {scenario} | test set - per-user chronological hold-out, gate 0.50)")
    print("=" * 70)
    for r in all_results:
        cm = r["confusion_matrix"]
        print(f"\n{r['name']}")
        print(f"  PR-AUC (trapezoidal): {r['pr_auc']:.4f}")
        print(f"  PR-AUC (AP):          {r['average_precision']:.4f}")
        print(f"  ROC-AUC:              {r['roc_auc']:.4f}")
        print(f"  Precision @ 0.50:     {r['precision_at_gate']:.4f}")
        print(f"  Recall @ 0.50:        {r['recall_at_gate']:.4f}")
        print(f"  F1 @ 0.50:            {r['f1_at_gate']:.4f}")
        print(f"  CM: TN={cm['tn']} FP={cm['fp']} FN={cm['fn']} TP={cm['tp']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train XGBoost return-risk model per scenario")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="basic",
                        help="basic | enriched | premium (merchant maturity stage)")
    parser.add_argument("--n-orders", type=int, default=10000)
    parser.add_argument("--gate", type=float, default=0.50)
    args = parser.parse_args()
    run(scenario=args.scenario, n_orders=args.n_orders, gate=args.gate)


if __name__ == "__main__":
    main()
