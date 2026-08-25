#!/usr/bin/env python3
"""Hyperparameter tuning for the XGBoost return-risk model.

Phase 3 of the return-risk ML pipeline. Exhaustive grid search over the
four parameters that most affect XGBoost capacity and class balance on seed
42 data with a per-user chronological split. The best configuration is
selected on the validation set (never the test set), then the final model
is retrained and evaluated once on the held-out test set to report an
unbiased PR-AUC.

Writes:
    models/return_risk_xgb_best.json   (best-configuration model)
    models/xgb_tuning_results.json     (full grid + best params + test PR-AUC)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import xgboost as xgb
from sklearn.metrics import auc, precision_recall_curve

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.return_risk_generator import FEATURES, generate_return_risk_dataset
from scripts.train_xgb_return_risk import chronological_split


def _pr_auc(model, x, y) -> float:
    scores = model.predict_proba(x)[:, 1]
    p, r, _ = precision_recall_curve(y, scores)
    return float(auc(r, p))


def _make(**params) -> xgb.XGBClassifier:
    base = {
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 42,
        "n_jobs": 8,
        "tree_method": "hist",
        "eval_metric": "logloss",
        "early_stopping_rounds": 20,
    }
    base.update(params)
    return xgb.XGBClassifier(**base)


def _fit(model, x_train, y_train, x_val, y_val) -> xgb.XGBClassifier:
    model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
    return model


def grid_search() -> dict:
    """Search max_depth x n_estimators x learning_rate x scale_pos_weight."""
    print("Generating data (seed=42)...")
    full_df = generate_return_risk_dataset(n_orders=10000, seed=42)
    train_df, val_df, test_df = chronological_split(full_df)
    x_train, y_train = train_df[FEATURES], train_df["returned"]
    x_val, y_val = val_df[FEATURES], val_df["returned"]

    param_grid = {
        "max_depth": [3, 4, 5, 6],
        "n_estimators": [100, 200, 300],
        "learning_rate": [0.05, 0.1, 0.15],
        "scale_pos_weight": [1.5, 2.0, 2.5, 3.0],
    }

    total = 1
    for v in param_grid.values():
        total *= len(v)
    print(f"Grid size: {total} combinations...")

    results: list[dict] = []
    best_pr_auc = -1.0
    best_params: dict | None = None

    for max_depth in param_grid["max_depth"]:
        for n_estimators in param_grid["n_estimators"]:
            for lr in param_grid["learning_rate"]:
                for spw in param_grid["scale_pos_weight"]:
                    model = _make(
                        max_depth=max_depth,
                        n_estimators=n_estimators,
                        learning_rate=lr,
                        scale_pos_weight=spw,
                    )
                    _fit(model, x_train, y_train, x_val, y_val)
                    pr_auc = _pr_auc(model, x_val, y_val)
                    results.append(
                        {
                            "max_depth": max_depth,
                            "n_estimators": n_estimators,
                            "learning_rate": lr,
                            "scale_pos_weight": spw,
                            "pr_auc": pr_auc,
                        }
                    )
                    if pr_auc > best_pr_auc:
                        best_pr_auc = pr_auc
                        best_params = {
                            "max_depth": max_depth,
                            "n_estimators": n_estimators,
                            "learning_rate": lr,
                            "scale_pos_weight": spw,
                        }
                        print(
                            f"  NEW BEST: PR-AUC {pr_auc:.4f} | "
                            f"max_depth={max_depth} n_estimators={n_estimators} "
                            f"lr={lr} spw={spw}"
                        )

    print(f"\n{'=' * 60}")
    print("BEST PARAMETERS (validation PR-AUC)")
    print("=" * 60)
    print(f"Validation PR-AUC: {best_pr_auc:.4f}")
    print(f"Params: {best_params}")

    print("\nTraining final model with best params...")
    final_model = _make(**best_params)
    _fit(final_model, x_train, y_train, x_val, y_val)

    test_pr_auc = _pr_auc(final_model, test_df[FEATURES], test_df["returned"].values)
    print(f"Test set PR-AUC: {test_pr_auc:.4f}")

    out = {
        "best_params": best_params,
        "best_val_pr_auc": best_pr_auc,
        "test_pr_auc": test_pr_auc,
        "all_results": results,
    }
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    with open(models_dir / "xgb_tuning_results.json", "w") as f:
        json.dump(out, f, indent=2)

    final_model.save_model(str(models_dir / "return_risk_xgb_best.json"))
    print("Saved: models/return_risk_xgb_best.json, models/xgb_tuning_results.json")
    return out


if __name__ == "__main__":
    grid_search()
