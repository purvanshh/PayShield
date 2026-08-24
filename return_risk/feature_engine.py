"""Return-risk feature extraction (Track 02 - Phase 13).

Extracts and computes features for return-risk scoring from the Redis
feature store, mirroring the shapes documented in
``docs/reference/return_risk_redis_schema.md``:

- user history   ``return_risk:user:{user_id}`` (hash) + ``:returns`` (zset)
- merchant stats ``return_risk:merchant:{merchant_id}`` (hash) +
  ``:category`` (zset of category baselines)
- transaction context (computed at scoring time)

Every feature carries a ``source`` tag (``redis_hash``, ``computed``,
``default_new_user``, ``lookup_table``, ``placeholder``) so the merchant -
or a judge - can always answer "where does this number come from?".
"""

from __future__ import annotations  # PEP 563: forward-referenced FeatureRegistry in annotations

# ruff: noqa: ARG002 -- interface parity: extraction profile mirrors the
# plan's signature so every caller pipes (user, merchant, txn) consistently.
import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np

CATEGORY_BASELINES = {
    "fashion": 0.32,
    "electronics": 0.12,
    "groceries": 0.04,
    "home": 0.18,
    "beauty": 0.15,
    "sports": 0.20,
    "footwear": 0.25,
    "furniture": 0.055,
    "default": 0.15,
}

DEFAULT_PRIOR = 0.15  # population return-rate prior for histories we haven't seen
DEFAULT_MERCHANT_RETURN_RATE = DEFAULT_PRIOR
DEFAULT_RESOLUTION_HOURS = 72.0
AMOUNT_SATURATION_INR = 50_000.0  # log-amount normalisation saturates at ₹50k


class ReturnRiskFeatureEngine:
    """Extracts return-risk features from the Redis feature store."""

    def __init__(self, redis: Any, registry: FeatureRegistry | None = None):
        self.redis = redis
        registry = registry or FeatureRegistry()
        self.default_prior = registry.default_prior
        self.category_prior = {**CATEGORY_BASELINES, **registry.default_priors}

    # ------------------------------------------------------------------ #
    # extraction                                                          #
    # ------------------------------------------------------------------ #

    async def extract_features(
        self,
        user_id: str,
        merchant_id: str,
        category: str,
        amount: Decimal,
        cod_flag: bool,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Extract user, merchant and transaction features.

        Returns ``{feature_name: {"value", "source"}}`` plus ``_meta`` with
        extraction metadata.
        """
        timestamp = timestamp or datetime.utcnow()

        user_features, merchant_features = await asyncio.gather(
            self._extract_user_features(user_id, timestamp),
            self._extract_merchant_features(merchant_id, category, timestamp),
        )

        txn_features = self._compute_transaction_features(
            category=category,
            amount=amount,
            cod_flag=cod_flag,
            timestamp=timestamp,
            merchant_features=merchant_features,
        )

        return {
            **user_features,
            **merchant_features,
            **txn_features,
            "_meta": {
                "extracted_at": timestamp.isoformat(),
                "user_id": user_id,
                "merchant_id": merchant_id,
            },
        }

    async def _extract_user_features(
        self, user_id: str, timestamp: datetime
    ) -> dict[str, Any]:
        user_key = f"return_risk:user:{user_id}"
        data = await self._safe_redis(self.redis.hgetall(user_key), default=None)

        if data is None or not data:
            # New user (or unreadable store): neutral features, never
            # zero-risk-by-default. ``default_redis_error`` marks the
            # degraded path so responses can carry an honest warning.
            # Return-rate features default to the population prior (the
            # market baseline, not zero) so first-time buyers are treated as
            # average-risk rather than risk-free.
            source = "default_redis_error" if data is None else "default_new_user"
            return {
                "user_return_rate_30d": {"value": self.default_prior, "source": source},
                "user_return_rate_90d": {"value": self.default_prior, "source": source},
                "user_return_rate_lifetime": {"value": self.default_prior, "source": source},
                "user_total_orders": {"value": 0, "source": source},
                "user_total_returns": {"value": 0, "source": source},
                "user_serial_returner_flag": {"value": False, "source": source},
                "user_return_velocity_7d": {"value": 0, "source": source},
                "user_cod_refusal_rate": {"value": 0.0, "source": source},
                "user_cod_orders": {"value": 0, "source": source},
                "user_avg_return_value": {"value": 0.0, "source": source},
                "user_return_reason_distribution": {"value": {}, "source": source},
                "user_is_new": {"value": True, "source": "inferred"},
            }

        total_orders = int(data.get("total_orders", 0))
        total_returns = int(data.get("total_returns", 0))
        return_rate_lifetime = total_returns / total_orders if total_orders > 0 else 0.0

        cod_refusals = int(data.get("cod_refusals", 0))
        cod_orders = int(data.get("cod_orders", 0) or cod_refusals)
        cod_refusal_rate = cod_refusals / cod_orders if cod_orders > 0 else 0.0

        serial_returner = return_rate_lifetime > 0.50 and total_orders >= 3
        returns_7d = await self._count_returns_in_window(user_id, days=7)

        reasons_raw = data.get("return_reason_distribution", "{}")
        try:
            reasons = json.loads(reasons_raw) if isinstance(reasons_raw, str) else reasons_raw
        except Exception:  # nosec B112 - unparseable reason JSON degrades to empty distribution
            reasons = {}

        return {
            "user_return_rate_30d": {"value": float(data.get("return_rate_30d", 0.0)), "source": "redis_hash"},
            "user_return_rate_90d": {"value": float(data.get("return_rate_90d", 0.0)), "source": "redis_hash"},
            "user_return_rate_lifetime": {"value": round(return_rate_lifetime, 4), "source": "computed"},
            "user_total_orders": {"value": total_orders, "source": "redis_hash"},
            "user_total_returns": {"value": total_returns, "source": "redis_hash"},
            "user_serial_returner_flag": {"value": serial_returner, "source": "computed"},
            "user_return_velocity_7d": {"value": returns_7d, "source": "redis_zset"},
            "user_cod_refusal_rate": {"value": round(cod_refusal_rate, 4), "source": "computed"},
            "user_cod_orders": {"value": cod_orders, "source": "redis_hash"},
            "user_avg_return_value": {"value": float(data.get("avg_return_value", 0.0)), "source": "redis_hash"},
            "user_return_reason_distribution": {"value": reasons, "source": "redis_hash"},
            "user_is_new": {"value": False, "source": "inferred"},
        }

    async def _extract_merchant_features(
        self, merchant_id: str, category: str, timestamp: datetime
    ) -> dict[str, Any]:
        merchant_key = f"return_risk:merchant:{merchant_id}"
        data = await self._safe_redis(self.redis.hgetall(merchant_key), default=None)

        if not data:
            degraded = data is None
            return {
                "merchant_return_rate_30d": {
                    "value": self.default_prior,
                    "source": "default_redis_error" if degraded else "default",
                },
                "merchant_return_fraud_rate": {
                    "value": 0.0,
                    "source": "default_redis_error" if degraded else "default",
                },
                "merchant_avg_resolution_time": {
                    "value": DEFAULT_RESOLUTION_HOURS,
                    "source": "default_redis_error" if degraded else "default",
                },
                "merchant_category_return_rate": {
                    "value": self._category_prior(category),
                    "source": "lookup_table",
                },
            }

        return {
            "merchant_return_rate_30d": {
                "value": float(data.get("return_rate_30d", DEFAULT_MERCHANT_RETURN_RATE)),
                "source": "redis_hash",
            },
            "merchant_return_fraud_rate": {
                "value": float(data.get("fraud_rate", data.get("return_fraud_rate", 0.0))),
                "source": "redis_hash",
            },
            "merchant_avg_resolution_time": {
                "value": float(
                    data.get("avg_resolution_time", data.get("avg_resolution_hours", DEFAULT_RESOLUTION_HOURS))
                ),
                "source": "redis_hash",
            },
"merchant_category_return_rate": {
                    "value": await self._merchant_category_rate(merchant_id, category),
                    "source": "redis_zset",
                },
        }

    async def _merchant_category_rate(self, merchant_id: str, category: str) -> float:
        """Merchant-specific baseline for this category (zset override)."""
        try:
            zkey = f"return_risk:merchant:{merchant_id}:category"
            score = await self.redis.zscore(zkey, category)
            if score is not None:
                return float(score)
        except Exception:  # nosec B110 - zset read failure falls back to lookup table
            pass
        return self._category_prior(category)

    @staticmethod
    async def _safe_redis(awaitable: Any, default: Any) -> Any:
        """Await a redis call, degrading to ``default`` on any failure.

        The risk scorer is a checkout-time decision path: a Redis outage
        must degrade to neutral defaults (with provenance tags) — never
        raise, never retry-loop. Callers distinguish degradation via the
        ``default_redis_error`` feature source.
        """
        try:
            result = awaitable
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception:  # nosec B112 - store outage degrades, never raises
            return default

    @staticmethod
    def _category_baseline(category: str) -> float:
        return float(CATEGORY_BASELINES.get(category, CATEGORY_BASELINES["default"]))

    def _category_prior(self, category: str) -> float:
        """Per-category return prior (registry overrides the built-in table)."""
        return float(self.category_prior.get(category, self.category_prior["default"]))

    def _compute_transaction_features(
        self,
        category: str,
        amount: Decimal,
        cod_flag: bool,
        timestamp: datetime,
        merchant_features: dict[str, Any],
    ) -> dict[str, Any]:
        # category baseline prefers the merchant's own per-category rate
        merchant_rate = merchant_features.get("merchant_category_return_rate", {})
        category_baseline = float(merchant_rate.get("value", self._category_prior(category)))

        amount_float = float(amount)
        # Log-normalised amount risk: a ₹50k order is 1.0, but high-AOV
        # markets no longer saturate every order to a constant 1.0 the way
        # the old linear `amount/10000` did.
        amount_risk = float(min(1.0, np.log1p(amount_float) / np.log1p(AMOUNT_SATURATION_INR)))

        hour = timestamp.hour
        time_risk = 0.3 if hour >= 23 or hour <= 5 else 0.0

        return {
            "txn_category_return_baseline": {
                "value": round(category_baseline, 4),
                "source": merchant_rate.get("source", "lookup_table"),
            },
            "txn_amount_risk": {"value": round(amount_risk, 4), "source": "computed"},
            "txn_cod_flag": {"value": cod_flag, "source": "input"},
            "txn_time_of_day_risk": {"value": time_risk, "source": "computed"},
            "txn_is_salary_day": {"value": self._is_salary_day(timestamp), "source": "computed"},
            "txn_user_merchant_interaction_count": {"value": 0, "source": "placeholder"},
        }

    async def _count_returns_in_window(self, user_id: str, days: int) -> int:
        key = f"return_risk:user:{user_id}:returns"
        cutoff_ts = (datetime.utcnow() - timedelta(days=days)).timestamp()
        returns = await self._safe_redis(
            self.redis.zrangebyscore(key, cutoff_ts, float("inf")), default=[]
        )
        return len(returns)

    @staticmethod
    def _is_salary_day(timestamp: datetime) -> bool:
        """Salary-day reuse: 1st and 15th of month (existing PayShield signal)."""
        return timestamp.day in (1, 15)

    # ------------------------------------------------------------------ #
    # write path (order placed / return initiated)                        #
    # ------------------------------------------------------------------ #

    async def update_user_profile(
        self,
        user_id: str,
        order_id: str,
        amount: Decimal,
        category: str = "",
        cod_flag: bool = False,
        returned: bool = False,
        return_reason: str | None = None,
    ) -> None:
        """Keep the user Redis profile fresh after order/return events.

        Called on order placement (or return initiation) so subsequent
        scores use current counts/averages/velocity. Idempotent by order id
        for the zset; counts are simple increments.
        """
        user_key = f"return_risk:user:{user_id}"
        await self.redis.hincrby(user_key, "total_orders", 1)
        if cod_flag:
            await self.redis.hincrby(user_key, "cod_orders", 1)

        if returned:
            await self.redis.hincrby(user_key, "total_returns", 1)
            return_key = f"return_risk:user:{user_id}:returns"
            now_ts = datetime.utcnow().timestamp()
            await self.redis.zadd(return_key, {order_id: now_ts})

            if return_reason:
                await self.redis.hincrby(f"return_risk:user:{user_id}:reasons", return_reason, 1)

            profile = await self.redis.hgetall(user_key)
            total_returns = int(profile.get("total_returns", 1))
            avg_return_value = float(profile.get("avg_return_value", 0.0))
            new_avg = (avg_return_value * (total_returns - 1) + float(amount)) / total_returns
            await self.redis.hmset(user_key, {"avg_return_value": str(round(new_avg, 2))})

        await self.redis.hmset(user_key, {"last_activity": datetime.utcnow().isoformat()})

    # ------------------------------------------------------------------ #
    # provenance                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_provenance(features: dict[str, Any]) -> list[str]:
        """Return the list of features missing a ``source`` tag (debug aid)."""
        return [
            name
            for name, value in features.items()
            if not name.startswith("_") and isinstance(value, dict) and "source" not in value
        ]


class FeatureRegistry:
    """Loads ``configs/feature_registry_return.yaml`` (registry + weights + priors)."""

    def __init__(self, path: str = "configs/feature_registry_return.yaml"):
        from pathlib import Path

        self.path = Path(path)
        self.composite_weights: dict[str, float] = {}
        self.features: list[dict[str, Any]] = []
        self.version: str = "1.0.0"
        self.default_prior: float = DEFAULT_PRIOR
        self.default_priors: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        import yaml

        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.version = str(data.get("version", "1.0.0"))
        self.composite_weights = data.get("composite_weights", {})
        self.features = data.get("features", [])
        self.default_prior = float(data.get("default_prior", DEFAULT_PRIOR))
        self.default_priors = {
            str(key): float(value) for key, value in (data.get("default_priors") or {}).items()
        }

    def by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [f for f in self.features if f.get("kind") == kind]

    def weight(self, feature_name: str) -> float:
        return float(self.composite_weights.get(feature_name, 0.0))
