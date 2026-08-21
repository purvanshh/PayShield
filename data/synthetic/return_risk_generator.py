"""Synthetic return-risk dataset generator (Track 02 - Phase 4).

Mirrors the style of :class:`data.synthetic.generator.SyntheticUPIGenerator`
but produces orders with return outcomes driven by the researched Indian
e-commerce patterns (docs/reference/return_risk_patterns.md):

- serial returners (return_rate > 50%, >= 3 orders)
- COD-refusal users
- category-dependent baselines (fashion 25-40%, electronics 8-15%, ...)
- size/fit-abuse buyers (fast consecutive same-category returns)

The generator returns:

- list of user profiles as Redis-ready dicts (``api/schemas/return_risk.py``)
  with a ``user_id`` and a computed ``return_rate_30d`` consistent with the
  simulated order history;
- merchant profiles (global and per-category return baselines);
- a pandas DataFrame of orders with a ``returned`` label column so Phase 19's
  precision/recall measurement has a held-out truth table.

Usage::

    from data.synthetic.return_risk_generator import ReturnRiskSyntheticGenerator

    gen = ReturnRiskSyntheticGenerator(n_users=500, n_merchants=40, n_orders=5000, seed=7)
    profiles, merchants, orders = gen.generate()
    gen.save_to_parquet(orders, "data/return_risk_orders.parquet")

"""

import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORY_BASELINES = {
    "fashion": 0.32,
    "footwear": 0.25,
    "electronics": 0.12,
    "grocery": 0.035,
    "beauty": 0.15,
    "furniture": 0.055,
}

RETURN_REASONS = ["SIZE_ISSUE", "CHANGED_MIND", "DEFECTIVE", "QUALITY_ISSUE", "NOT_AS_DESCRIBED", "LATE_DELIVERY"]

USER_TYPES = ["normal", "serial_returner", "cod_refusal", "size_abuser", "good"]


class ReturnRiskSyntheticGenerator:
    def __init__(
        self,
        n_users: int = 500,
        n_merchants: int = 40,
        n_orders: int = 5000,
        seed: int = 42,
    ):
        self.n_users = n_users
        self.n_merchants = n_merchants
        self.n_orders = n_orders
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.categories = list(CATEGORY_BASELINES)

    def generate(self):
        profiles = self._generate_user_profiles()
        merchants = self._generate_merchant_profiles()
        orders = self._generate_orders(profiles, merchants)
        return profiles, merchants, orders

    def _generate_user_profiles(self) -> list[dict]:
        profiles = []
        for i in range(self.n_users):
            uid = f"U{str(i).zfill(6)}"
            user_type = self.np_rng.choice(USER_TYPES, p=[0.55, 0.08, 0.07, 0.10, 0.20])
            total_orders = int(self.np_rng.integers(3, 40))
            if user_type == "good":
                return_rate = self.rng.uniform(0.0, 0.05)
            elif user_type == "serial_returner":
                total_orders = max(total_orders, 5)
                return_rate = self.rng.uniform(0.5, 0.85)
            elif user_type == "cod_refusal":
                return_rate = self.rng.uniform(0.1, 0.35)
            elif user_type == "size_abuser":
                return_rate = self.rng.uniform(0.3, 0.6)
            else:
                return_rate = self.rng.uniform(0.05, 0.25)

            total_returns = max(1, int(total_orders * return_rate))
            reason_counts = {
                reason: int(self.np_rng.integers(0, max(1, total_returns)))
                for reason in RETURN_REASONS
            }
            overflow = total_returns - sum(reason_counts.values())
            if overflow > 0:
                reason_counts["SIZE_ISSUE" if user_type == "size_abuser" else "CHANGED_MIND"] += overflow

            cod_flag = user_type == "cod_refusal"
            cod_refusals = int(self.np_rng.integers(1, 6)) if cod_flag else 0
            cod_orders = max(cod_refusals, 1)
            profiles.append(
                {
                    "user_id": uid,
                    "user_type": user_type,
                    "total_orders": total_orders,
                    "total_returns": total_returns,
                    "return_rate_30d": round(return_rate, 4),
                    "return_rate_90d": round(return_rate * self.rng.uniform(0.8, 1.1), 4),
                    "return_rate_lifetime": round(return_rate, 4),
                    "avg_return_value": round(float(self.np_rng.integers(500, 6500)), 2),
                    "max_return_value": round(float(self.np_rng.integers(1500, 12000)), 2),
                    "return_reason_distribution": reason_counts,
                    "cod_refusal_rate": round(min(1.0, cod_refusals / cod_orders), 4),
                    "cod_refusals": cod_refusals,
                    "serial_returner_flag": return_rate > 0.5 and total_orders >= 3,
                    "return_velocity_7d": int(self.np_rng.integers(0, 5 if return_rate > 0.4 else 2)),
                    "first_return_days": int(self.np_rng.integers(1, 60)),
                    "return_pattern_score": round(0.1 + min(0.9, reason_counts.get("SIZE_ISSUE", 0) / max(1, total_returns)) * 0.75, 4),
                    "last_return_ts": (datetime.utcnow() - timedelta(days=int(self.np_rng.integers(0, 30)))).isoformat(),
                }
            )
        return profiles

    def _generate_merchant_profiles(self) -> list[dict]:
        merchants = []
        for i in range(self.n_merchants):
            mid = f"M{str(i).zfill(5)}"
            base_rate = self.rng.uniform(0.03, 0.22)
            by_category = {
                cat: round(min(0.6, base_rate * self.rng.uniform(0.6, 2.2)), 4)
                for cat in self.categories
            }
            merchants.append(
                {
                    "merchant_id": mid,
                    "merchant_category": self.rng.choice(self.categories),
                    "return_rate_30d": round(base_rate, 4),
                    "return_rate_by_category": by_category,
                    "avg_resolution_hours": round(self.rng.uniform(12, 72), 1),
                    "return_fraud_rate": round(self.rng.uniform(0.0, 0.08), 4),
                }
            )
        return merchants

    def _generate_orders(self, profiles: list[dict], merchants: list[dict]) -> pd.DataFrame:
        rows = []
        total_weight = [1.0 / self.n_users] * self.n_users
        for i in range(self.n_orders):
            profile = self.rng.choices(profiles, weights=total_weight)[0]
            merchant = self.rng.choice(merchants)
            category = self.rng.choice(self.categories)
            baseline = min(0.6, merchant["return_rate_by_category"].get(category, CATEGORY_BASELINES[category]))
            amount = round(float(self.np_rng.integers(199, 12000)), 2)
            cod = self.rng.random() < 0.35
            hour = int(self.rng.choices([0, 1, 12, 14, 18, 20, 23], weights=[5, 5, 10, 10, 20, 15, 8])[0])
            ts = datetime.utcnow() - timedelta(days=int(self.np_rng.integers(0, 60)), hours=hour)

            personal_rate = profile["return_rate_30d"]
            fraud_bad = profile["user_type"] == "serial_returner" or profile["user_type"] == "size_abuser"
            base_ret = max(0.0, 0.25 * personal_rate + 0.55 * baseline + (0.05 if fraud_bad else 0.0))
            if category == "fashion" and personal_rate > 0.4:
                base_ret += 0.15
            if cod and profile["user_type"] == "cod_refusal":
                base_ret = min(0.95, base_ret + 0.35)

            returned = self.rng.random() < min(0.97, base_ret)
            reason = "SIZE_ISSUE" if returned and category in ("fashion", "footwear") and personal_rate > 0.3 else self.rng.choice(RETURN_REASONS)
            rows.append(
                {
                    "order_id": f"ORD-{str(i).zfill(7)}",
                    "user_id": profile["user_id"],
                    "merchant_id": merchant["merchant_id"],
                    "category": category,
                    "amount": amount,
                    "payment_method": "COD" if cod else "UPI",
                    "cod_flag": cod,
                    "timestamp": ts,
                    "returned": returned,
                    "return_reason": reason if returned else "",
                    "days_to_return": int(self.np_rng.integers(1, 15)) if returned else 0,
                }
            )
        return pd.DataFrame(rows)

    def save_to_parquet(self, orders: pd.DataFrame, path: str | Path):
        orders.to_parquet(path, index=False)
        return path
