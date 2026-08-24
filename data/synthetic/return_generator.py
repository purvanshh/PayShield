"""Synthetic return-risk dataset generator (Track 02 - Phase 17).

Generates realistic synthetic data for return-risk scoring, modelling the
Indian e-commerce archetypes researched in
``docs/reference/return_risk_patterns.md`` and recalibrated against public
Indian e-commerce distributions (Amazon India 2025 category/PLP margins):

- return rates per category sit in the 31-34% band seen in the Amazon report
  (Books 33.9%, Electronics 33.1%, Clothing 32.5%, Beauty 31.8%,
  Home & Kitchen 31.3%);
- order value averages land around ~₹70-80k (Amazon AOV ≈ ₹74.5k);
- payment mix keeps COD ≈ 25.5% (Amazon COD share);
- order dates follow Amazon monthly seasonality (Aug/Dec peaks, Feb trough).

Five user archetypes (honest, casual returner, serial returner, fraud
returner, new user) keep their relative separation so precision/recall is
still measurable, but the *center* of the distribution matches the Indian
high-return market.
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

fake = Faker("en_IN")

# Amazon India 2025 monthly order counts (MONTHLY_SALES_TRENDS) -> seasonality
MONTHLY_COUNTS = {
    "January": 1276, "February": 1183, "March": 1226, "April": 1203,
    "May": 1267, "June": 1225, "July": 1306, "August": 1312,
    "September": 1248, "October": 1233, "November": 1225, "December": 1296,
}
SEASONALITY = [c / sum(MONTHLY_COUNTS.values()) for c in MONTHLY_COUNTS.values()]

COD_SHARE = 0.255  # Amazon India COD share of payments

USER_TYPES = {
    "honest": {
        "return_rate_mean": 0.15,
        "return_rate_std": 0.04,
        "order_frequency_days": 30,
        "avg_order_value": 65000,
        "return_reasons": {"DEFECTIVE": 0.4, "SIZE_ISSUE": 0.3, "CHANGED_MIND": 0.2, "OTHER": 0.1},
    },
    "casual_returner": {
        "return_rate_mean": 0.28,
        "return_rate_std": 0.05,
        "order_frequency_days": 21,
        "avg_order_value": 72000,
        "return_reasons": {"SIZE_ISSUE": 0.4, "CHANGED_MIND": 0.3, "DEFECTIVE": 0.2, "OTHER": 0.1},
    },
    "serial_returner": {
        "return_rate_mean": 0.48,
        "return_rate_std": 0.08,
        "order_frequency_days": 14,
        "avg_order_value": 80000,
        "return_reasons": {"CHANGED_MIND": 0.5, "SIZE_ISSUE": 0.3, "DEFECTIVE": 0.1, "OTHER": 0.1},
    },
    "fraud_returner": {
        "return_rate_mean": 0.62,
        "return_rate_std": 0.08,
        "order_frequency_days": 10,
        "avg_order_value": 88000,
        "return_reasons": {"EMPTY_BOX": 0.3, "DAMAGED": 0.3, "WRONG_ITEM": 0.2, "CHANGED_MIND": 0.2},
    },
    "new_user": {
        "return_rate_mean": 0.24,
        "return_rate_std": 0.10,
        "order_frequency_days": 45,
        "avg_order_value": 40000,
        "return_reasons": {"SIZE_ISSUE": 0.5, "CHANGED_MIND": 0.3, "DEFECTIVE": 0.2},
    },
}

# Amazon India 2025 return rate per category (RETURNS_BY_CATEGORY)
MERCHANT_TYPES = {
    "fashion_retailer": {"category": "fashion", "return_rate": 0.325, "avg_value": 78000},
    "electronics_store": {"category": "electronics", "return_rate": 0.331, "avg_value": 80000},
    "grocery_chain": {"category": "groceries", "return_rate": 0.32, "avg_value": 30000},
    "home_decor": {"category": "home", "return_rate": 0.313, "avg_value": 56000},
    "beauty_brand": {"category": "beauty", "return_rate": 0.318, "avg_value": 50000},
}


class ReturnRiskSyntheticGenerator:
    """Generates synthetic orders and returns with ground truth labels."""

    def __init__(self, seed: int = 42):
        random.seed(seed)
        fake.seed_instance(seed)
        self.seed = seed
        self.USER_TYPES = USER_TYPES
        self.MERCHANT_TYPES = MERCHANT_TYPES

    # ------------------------------------------------------------------ #
    # profile synthesis                                                  #
    # ------------------------------------------------------------------ #

    def generate_user(self, user_type: str, user_id: str | None = None) -> dict[str, Any]:
        archetype = self.USER_TYPES[user_type]
        return {
            "user_id": user_id or f"U_{fake.uuid4()[:8]}",
            "user_type": user_type,
            "name": fake.name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "city": fake.city(),
            "return_rate": max(0.0, random.gauss(archetype["return_rate_mean"], archetype["return_rate_std"])),
            "order_frequency_days": archetype["order_frequency_days"],
            "avg_order_value": archetype["avg_order_value"],
            "return_reason_distribution": archetype["return_reasons"],
        }

    def generate_merchant(self, merchant_type: str, merchant_id: str | None = None) -> dict[str, Any]:
        archetype = self.MERCHANT_TYPES[merchant_type]
        return {
            "merchant_id": merchant_id or f"M_{fake.uuid4()[:8]}",
            "merchant_type": merchant_type,
            "name": fake.company(),
            "category": archetype["category"],
            "return_rate": archetype["return_rate"],
            "avg_order_value": archetype["avg_value"],
        }

    def generate_order_history(
        self,
        user: dict[str, Any],
        merchant: dict[str, Any],
        num_orders: int = 20,
        start_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Order history for a single user-merchant pair (with return labels).

        Dates follow Amazon monthly seasonality (Aug/Dec peaks) spread over a
        one-year window and are returned sorted, so the chronological per-user
        split used by the benchmark stays meaningful. COD share follows the
        Indian market (≈25.5%).
        """
        start_date = start_date or (datetime.utcnow() - timedelta(days=365))
        dates = self._seasonal_dates(num_orders, start_date)
        orders = []
        for order_date in dates:
            return_prob = max(0.0, min(1.0, user["return_rate"] + random.gauss(0, 0.05)))
            was_returned = random.random() < return_prob
            return_reason = None
            if was_returned:
                reasons = list(user["return_reason_distribution"].keys())
                weights = list(user["return_reason_distribution"].values())
                return_reason = random.choices(reasons, weights=weights)[0]

            orders.append(
                {
                    "order_id": f"ORD_{uuid.uuid4().hex[:12]}",
                    "user_id": user["user_id"],
                    "merchant_id": merchant["merchant_id"],
                    "amount": round(random.gauss(user["avg_order_value"], user["avg_order_value"] * 0.2), 2),
                    "category": merchant["category"],
                    "cod_flag": random.random() < COD_SHARE,
                    "order_date": order_date.isoformat(),
                    "returned": was_returned,
                    "return_reason": return_reason,
                    "return_date": (order_date + timedelta(days=random.randint(1, 14))).isoformat()
                    if was_returned
                    else None,
                }
            )
        return orders

    @staticmethod
    def _seasonal_dates(num_orders: int, start: datetime) -> list[datetime]:
        """Draw ``num_orders`` dates weighted by Amazon monthly seasonality."""
        base = start.year * 12 + start.month - 1
        dates = []
        for _ in range(num_orders):
            month_idx = random.choices(range(12), weights=SEASONALITY)[0]
            year, month = divmod(base + month_idx, 12)
            day = random.randint(1, 28)
            dates.append(datetime(year, month + 1, day))
        dates.sort()
        return dates

    # ------------------------------------------------------------------ #
    # dataset                                                            #
    # ------------------------------------------------------------------ #

    def generate_dataset(self, num_users_per_type: int = 50, orders_per_user: int = 20) -> dict[str, Any]:
        """Full dataset: users, merchants, orders and ground-truth labels."""
        users = []
        merchants = []
        all_orders: list[dict[str, Any]] = []

        for mtype in self.MERCHANT_TYPES:
            merchants.append(self.generate_merchant(mtype))

        for user_type in self.USER_TYPES:
            for _ in range(num_users_per_type):
                user = self.generate_user(user_type)
                users.append(user)
                merchant = random.choice(merchants)
                all_orders.extend(self.generate_order_history(user, merchant, orders_per_user))

        labels = {}
        by_user = {u["user_id"]: u for u in users}
        for order in all_orders:
            user = by_user[order["user_id"]]
            labels[order["order_id"]] = {
                "high_risk": user["user_type"] in ("serial_returner", "fraud_returner"),
                "returned": order["returned"],
                "user_type": user["user_type"],
            }

        return {
            "users": users,
            "merchants": merchants,
            "orders": all_orders,
            "labels": labels,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "num_users": len(users),
                "num_orders": len(all_orders),
                "seed": self.seed,
            },
        }

    # ------------------------------------------------------------------ #
    # redis seeding                                                      #
    # ------------------------------------------------------------------ #

    def seed_redis_with_profiles(self, redis_client, dataset: dict[str, Any]) -> int:
        """Seed user profiles + return velocity from the dataset.

        Works with any client exposing ``hset``/``hgetall``/``zadd`` (the
        sync store client is fine - this is a script path, not the hot path).
        Returns the number of users seeded.
        """
        by_user: dict[str, list[dict[str, Any]]] = {}
        for order in dataset["orders"]:
            by_user.setdefault(order["user_id"], []).append(order)

        for user in dataset["users"]:
            orders = by_user.get(user["user_id"], [])
            total_orders = len(orders)
            returned = [o for o in orders if o["returned"]]
            total_returns = len(returned)
            return_rate = total_returns / total_orders if total_orders else 0.0

            user_key = f"return_risk:user:{user['user_id']}"
            fields = {
                "total_orders": str(total_orders),
                "total_returns": str(total_returns),
                "return_rate_30d": str(round(return_rate, 4)),
                "return_rate_90d": str(round(return_rate, 4)),
                "avg_return_value": str(user["avg_order_value"]),
                "serial_returner": str(return_rate > 0.50 and total_orders >= 3).lower(),
            }
            for key, value in fields.items():
                redis_client.hset(user_key, key, value)

            return_key = f"return_risk:user:{user['user_id']}:returns"
            for order in returned:
                ts = datetime.fromisoformat(order["return_date"]).timestamp()
                redis_client.zadd(return_key, {order["order_id"]: ts})

        for merchant in dataset["merchants"]:
            merchant_key = f"return_risk:merchant:{merchant['merchant_id']}"
            redis_client.hset(merchant_key, "return_rate_30d", str(merchant["return_rate"]))
        return len(dataset["users"])
