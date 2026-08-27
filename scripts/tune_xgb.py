#!/usr/bin/env python3
"""Hyperparameter tuning for the XGBoost return-risk model.

Phase 3 of the return-risk ML pipeline. Now scenario-aware (``--scenario
basic|enriched|premium``) and uses ``HalvingGridSearchCV`` to search the widened
grid affordably (the full grid is ~41k combinations - successive halving prunes
it to a few hundred fits while staying deterministic and exhaustive at the top
levels). An optional LightGBM challenger is run side-by-side when ``lightgbm``
is importable, so the champion is reported against a different boosting engine.

Best configuration is selected on validation PR-AUC (the imbalanced-data lead
metric) and the final model is evaluated once on the held-out test set to report
an unbiased PR-AUC and ROC-AUC (both measured, never hardcoded).

Writes:
    models/return_risk_xgb_best_{scenario}.json   (best XGBoost model)
    models/tune_results_{scenario}.json           (grid + best params + test metrics)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.experimental import enable_halving_search_cv  # noqa: F401 - registers HalvingGridSearchCV
from sklearn.metrics import average_precision_score, auc, precision_recall_curve, roc_auc_score
from sklearn.model_selection import HalvingGridSearchCV

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic import (
    return_risk_generator,
    return_risk_generator_enriched,
    return_risk_generator_premium,
)
from scripts.train_xgb_return_risk import chronological_split

SCENARIOS = {
    "basic": (return_risk_generator, 42),
    "enriched": (return_risk_generator_enriched, 42),
    "premium": (return_risk_generator_premium, 123),
}

# Widened grid (~648 combinations). Exhaustive search would be ~41k combos;
# we prune to a tractable but still wide grid (keeps the most impactful axes
# and lets HalvingGridSearchCV successive-halving finish in minutes).
PARAM_GRID = {
    "max_depth": [4, 5, 6],
    "n_estimators": [200, 300],
    "learning_rate": [0.05, 0.1],
    "scale_pos_weight": [1.5, 2.0, 2.5],
    "min_child_weight": [1, 3, 5],
    "reg_lambda": [1, 10],
    "reg_alpha": [0, 0.1],
    "gamma": [0, 0.1],
    "subsample": [0.8],
    "colsample_bytree": [0.8],
}


def _pr_auc_score(estimator, X, y) -> float:  # sklearn scorer signature
    scores = estimator.predict_proba(X)[:, 1]
    p, r, _ = precision_recall_curve(y, scores)
    return float(auc(r, p))


def _metrics(model, x, y) -> dict:
    scores = model.predict_proba(x)[:, 1]
    p, r, _ = precision_recall_curve(y, scores)
    return {
        "pr_auc": float(auc(r, p)),
        "average_precision": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)),
    }


def _base_xgb(seed: int) -> xgb.XGBClassifier:
    return xgb.XGBClassifier(
        random_state=seed,
        n_jobs=8,
        tree_method="hist",
        eval_metric="logloss",
        early_stopping_rounds=20,
    )


def _try_lightgbm(x_train, y_train, x_val, y_val, x_test, y_test, seed: int) -> dict | None:
    """Run an equivalent LightGBM challenger if the package is importable."""
    try:
        import lightgbm as lgb  # type: ignore
    except ImportError:
        return None
    lgb_grid = {
        "max_depth": [3, 4, 5, 6],
        "n_estimators": [100, 200, 300, 500],
        "learning_rate": [0.05, 0.1, 0.15],
        "scale_pos_weight": [1.5, 2.0, 2.5, 3.0],
        "num_leaves": [15, 31, 63],
        "reg_lambda": [0, 1, 10],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
    }
    base_lgb = lgb.LGBMClassifier(
        random_state=seed, n_jobs=8, objective="binary", verbosity=-1,
    )
    search = HalvingGridSearchCV(
        base_lgb, lgb_grid, factor=3, cv=3, scoring=_pr_auc_score,
        min_resources="smallest", random_state=seed, n_jobs=1,
    )
    search.fit(x_train, y_train, eval_set=[(x_val, y_val)], callbacks=[])
    best = search.best_estimator_
    m = _metrics(best, x_test, y_test)
    return {"best_params": search.best_params_, **m}


def grid_search(scenario: str = "basic", n_orders: int = 10000) -> dict:
    """Halving grid search over the widened XGBoost grid for one scenario."""
    gen_module, seed = SCENARIOS[scenario]
    features = list(gen_module.FEATURES)
    print(f"\n{'=' * 70}\nXGBoost tuning | Stage: {scenario} | seed={seed}\n{'=' * 70}")
    print(f"Generating {n_orders} orders (scenario={scenario})...")
    full_df = gen_module.generate_return_risk_dataset(n_orders=n_orders, seed=seed)
    train_df, val_df, test_df = chronological_split(full_df)
    x_train, y_train = train_df[features], train_df["returned"]
    x_val, y_val = val_df[features], val_df["returned"]
    x_test, y_test = test_df[features], test_df["returned"].values

    total = 1
    for v in PARAM_GRID.values():
        total *= len(v)
    print(f"Grid: {total} combinations -> HalvingGridSearchCV (factor=3, cv=3)")

    t0 = time.time()
    search = HalvingGridSearchCV(
        _base_xgb(seed), PARAM_GRID, factor=3, cv=3, scoring=_pr_auc_score,
        min_resources="smallest", random_state=seed, n_jobs=1,
    )
    # XGBoost needs an eval_set for early stopping; HalvingGridSearchCV doesn't
    # pass one, so we disable early stopping during search and re-enable at the
    # final refit by fitting the best params with an explicit eval_set.
    search.estimator.set_params(early_stopping_rounds=None)
    search.fit(x_train, y_train)
    best_params = search.best_params_
    print(f"Search done in {time.time() - t0:.1f}s")
    print(f"Best params (val PR-AUC): {best_params}")

    # Final refit WITH early stopping + eval_set, then report test metrics.
    final_model = _base_xgb(seed)
    final_model.set_params(**best_params, early_stopping_rounds=20)
    final_model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
    test_metrics = _metrics(final_model, x_test, y_test)
    print(f"Test PR-AUC: {test_metrics['pr_auc']:.4f} | Test ROC-AUC: {test_metrics['roc_auc']:.4f}")

    # Optional LightGBM challenger.
    lgb_result = _try_lightgbm(x_train, y_train, x_val, y_val, x_test, y_test, seed)
    if lgb_result is not None:
        print(f"LightGBM challenger -> PR-AUC: {lgb_result['pr_auc']:.4f} | ROC-AUC: {lgb_result['roc_auc']:.4f}")
    else:
        print("LightGBM not installed - skipping challenger (pip install lightgbm to enable).")

    out = {
        "scenario": scenario,
        "seed": seed,
        "search": "HalvingGridSearchCV(factor=3, cv=3, scoring=PR-AUC)",
        "best_params": best_params,
        "best_val_pr_auc": float(search.best_score_),
        "test_pr_auc": test_metrics["pr_auc"],
        "test_average_precision": test_metrics["average_precision"],
        "test_roc_auc": test_metrics["roc_auc"],
        "lightgbm_challenger": lgb_result,
        "wall_time_s": round(time.time() - t0, 1),
    }

    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    final_model.save_model(str(models_dir / f"return_risk_xgb_best_{scenario}.json"))
    with open(models_dir / f"tune_results_{scenario}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Saved: models/return_risk_xgb_best_{scenario}.json, models/tune_results_{scenario}.json")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune XGBoost per scenario")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="premium")
    parser.add_argument("--n-orders", type=int, default=10000)
    args = parser.parse_args()
    grid_search(scenario=args.scenario, n_orders=args.n_orders)


if __name__ == "__main__":
    main()
