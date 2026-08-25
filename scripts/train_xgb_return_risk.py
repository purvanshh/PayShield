#!/usr/bin/env python3
"""Train an XGBoost return-risk model and evaluate against naive baselines.

Phase 1 of the return-risk ML pipeline. Run this first; ablation and tuning
depend on its conventions (``data/synthetic/return_risk_generator.FEATURES``,
the per-user chronological split, and the hand-weighted baseline).

Writes:
    models/return_risk_xgb_v1.json   (default-hyperparameter model)
    models/xgb_evaluation.json       (4-model comparison on the test set)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    auc,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.return_risk_generator import FEATURES, generate_return_risk_dataset

# --------------------------------------------------------------------------- #
# Hand-weighted scorer (production-style baseline). Mirrors the weights in
# return_risk/scorer.FEATURE_WEIGHTS mapped onto the seven model features so
# the "current production approach" comparison is fair and referenceable.
# --------------------------------------------------------------------------- #


class HandWeightedScorer:
    """Weighted, normalised sum over the seven features (no ML).

    Weights are the production composite weights re-mapped onto the model's
    feature surface. Features are normalised to [0,1] the same way the
    production scorer normalises before weighting (device match is inverted:
    a *match* is low risk).
    """

    WEIGHTS = {
        "user_return_rate_30d": 0.25,
        "user_return_rate_90d": 0.20,
        "amount_vs_user_aov_ratio": 0.10,
        "category_return_baseline": 0.15,
        "payment_method_risk": 0.10,
        "device_fingerprint_match": 0.10,
        "days_since_last_order": 0.10,
    }

    def __init__(self) -> None:
        assert abs(sum(self.WEIGHTS.values()) - 1.0) < 1e-9

    def _normalize(self, feature: str, value: float) -> float:
        v = float(value)
        if feature == "device_fingerprint_match":
            return 1.0 - min(1.0, max(0.0, v))
        if feature == "days_since_last_order":
            return min(1.0, v / 45.0)
        if feature == "amount_vs_user_aov_ratio":
            return min(1.0, max(0.0, v - 1.0))
        return min(1.0, max(0.0, v))

    def score(self, row: dict) -> dict:
        total = sum(self.WEIGHTS[f] * self._normalize(f, row[f]) for f in self.WEIGHTS)
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


def train_xgb(train_df: pd.DataFrame, val_df: pd.DataFrame, seed: int = 42):
    """Train with conservative hyperparameters to prevent overfitting."""
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=2.0,
        random_state=seed,
        n_jobs=8,
        tree_method="hist",
        eval_metric="logloss",
        early_stopping_rounds=20,
    )
    model.fit(
        train_df[FEATURES],
        train_df["returned"],
        eval_set=[(val_df[FEATURES], val_df["returned"])],
        verbose=False,
    )
    return model


def evaluate(model, test_df: pd.DataFrame, gate: float = 0.50) -> dict:
    """Unified evaluation: PR-AUC, precision/recall/F1 at gate, confusion matrix.

    ``model`` must expose ``predict_proba`` (an XGBClassifier or the Dummy
    wrapper used for baselines).
    """
    x_test = test_df[FEATURES]
    y_true = test_df["returned"].values
    scores = model.predict_proba(x_test)[:, 1]

    p_curve, r_curve, _ = precision_recall_curve(y_true, scores)
    pr_auc = auc(r_curve, p_curve)

    y_pred = (scores >= gate).astype(int)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "pr_auc": float(pr_auc),
        "precision_at_gate": float(prec),
        "recall_at_gate": float(rec),
        "f1_at_gate": float(f1),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


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


def run(seed: int = 42, n_orders: int = 10000) -> tuple:
    """Generate -> split -> train -> evaluate -> save."""
    print(f"Generating {n_orders} orders (seed={seed})...")
    full_df = generate_return_risk_dataset(n_orders=n_orders, seed=seed)
    print(f"  base rate={full_df['returned'].mean():.3f}  rows={len(full_df)}")

    print("Splitting (60/20/20, per-user chronological)...")
    train_df, val_df, test_df = chronological_split(full_df)
    print(f"  Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")

    print("Training XGBoost...")
    model = train_xgb(train_df, val_df, seed=seed)

    print("Evaluating XGBoost...")
    xgb_results = evaluate(model, test_df)
    xgb_results["name"] = "XGBoost (default)"
    xgb_results["feature_importance"] = dict(zip(FEATURES, model.feature_importances_.tolist(), strict=True))

    print("Evaluating hand-weighted baseline...")
    hw = HandWeightedScorer()
    hw_scores = test_df.apply(lambda r: hw.score(r.to_dict())["score"], axis=1).values
    hw_result = evaluate(Dummy(hw_scores), test_df)
    hw_result["name"] = "Hand-weighted (current)"

    print("Evaluating naive baselines...")
    s1 = np.zeros(len(test_df))
    mask = (
        (test_df["payment_method"] == "COD")
        & (test_df["amount"] > 3000)
        & (test_df["category"].isin(["fashion", "beauty"]))
    )
    s1[mask] = 0.6
    b1 = evaluate(Dummy(s1), test_df)
    b1["name"] = "Naive: COD+HighAOV"

    s2 = (test_df["user_return_rate_90d"] > 0.4).astype(float).values * 0.7
    b2 = evaluate(Dummy(s2), test_df)
    b2["name"] = "Naive: SerialReturner"

    all_results = [xgb_results, hw_result, b2, b1]

    _print_results(all_results)

    print(f"\n{'=' * 70}")
    print("XGBoost FEATURE IMPORTANCE")
    print("=" * 70)
    for feat, imp in sorted(xgb_results["feature_importance"].items(), key=lambda kv: -kv[1]):
        print(f"  {feat}: {imp:.4f}")

    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    model.save_model(str(models_dir / "return_risk_xgb_v1.json"))
    with open(models_dir / "xgb_evaluation.json", "w") as f:
        json.dump({"gate": 0.50, "models": all_results}, f, indent=2)

    print("\nSaved: models/return_risk_xgb_v1.json, models/xgb_evaluation.json")
    return model, all_results


def _print_results(all_results: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print("RESULTS (test set - per-user chronological hold-out, gate 0.50)")
    print("=" * 70)
    for r in all_results:
        cm = r["confusion_matrix"]
        print(f"\n{r['name']}")
        print(f"  PR-AUC: {r['pr_auc']:.4f}")
        print(f"  Precision @ 0.50: {r['precision_at_gate']:.4f}")
        print(f"  Recall @ 0.50: {r['recall_at_gate']:.4f}")
        print(f"  F1 @ 0.50: {r['f1_at_gate']:.4f}")
        print(f"  CM: TN={cm['tn']} FP={cm['fp']} FN={cm['fn']} TP={cm['tp']}")


if __name__ == "__main__":
    run()
