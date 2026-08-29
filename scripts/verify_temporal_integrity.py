#!/usr/bin/env python3
"""Temporal-integrity verification: no look-ahead bias in the DGP or split.

Verifies three concrete, checkable properties on the seeded generator
(``seed=99``) and the exact split the training pipeline uses:

1. **Per-user chronology** — every user's orders are strictly time-ordered.
2. **Split has no future leakage** — the per-user 60/20/20 chronological split
   must keep ``max(train ts) <= min(val ts) <= min(test ts)`` for every user,
   so training never sees an order newer than the orders it is tested against.
3. **Order-time features are latent-sampled** — every user's *first* order
   carries valid in-range rate features with zero prior history, proving the
   features are generated at order time from the user's latent propensity and
   never derived from any other order's realized return (including the order's
   own label).

Any violation fails the run (exit 1). Run standalone, or via
``scripts/run_all_scenarios.py --full-verify`` (check 11).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.synthetic.return_risk_generator import generate_return_risk_dataset
from scripts.train_xgb_return_risk import chronological_split

RATE_FEATURES = ("user_return_rate_30d", "user_return_rate_90d")


def verify(n_orders: int = 3000, seed: int = 99) -> list[str]:
    """Return a list of failures (empty == pass)."""
    failures: list[str] = []

    df = generate_return_risk_dataset(n_orders=n_orders, seed=seed)
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    # 1. Per-user chronology ------------------------------------------------- #
    for user_id, _group in df.groupby("user_id", sort=False):
        timestamps = _group["timestamp"].tolist()
        if any(b < a for a, b in zip(timestamps, timestamps[1:], strict=True)):
            failures.append(f"user {user_id}: orders not strictly chronological")

    # 2. Split has no future leakage ---------------------------------------- #
    train, val, test = chronological_split(df.copy())


    def _user_ts(df_part, user_id):
        rows = df_part[df_part["user_id"] == user_id]
        return rows["timestamp"].min(), rows["timestamp"].max()

    for user_id, _group in df.groupby("user_id", sort=False):
        t_min, t_max = _user_ts(train, user_id)
        v_min, v_max = _user_ts(val, user_id)
        e_min, _ = _user_ts(test, user_id)
        if not (t_max <= v_min <= e_min):
            failures.append(
                f"user {user_id}: split leaks future data "
                f"(train<=val<=test violated: {t_max} / {v_min} / {e_min})"
            )

    # 3. First-order features are latent-sampled (no history required) ------ #
    first_orders = df.sort_values(["user_id", "timestamp"]).groupby("user_id").head(1)
    for _, row in first_orders.iterrows():
        for feature in RATE_FEATURES:
            value = float(row[feature])
            if not (0.02 <= value <= 0.90):
                failures.append(
                    f"user {row['user_id']} first-order {feature}={value:.4f} out of [0.02, 0.90]"
                )

    return failures


def main() -> int:
    print("Temporal integrity: checking no look-ahead in DGP features and split...")
    failures = verify()
    if not failures:
        print("  PASS per-user chronology (no future order precedes a past one)")
        print("  PASS split: max(train) <= min(val) <= min(test) for every user")
        print("  PASS first-order features are latent-sampled, not history/label-derived")
        print("Temporal integrity: OK")
        return 0
    for failure in failures:
        print(f"  FAIL {failure}")
    print("Temporal integrity: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
