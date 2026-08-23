"""Return-risk feature drift monitoring (Track 2 - Phase 39).

Extends the existing PSI machinery (``population_stability_index``) to the
return-risk feature surface. Feature values are sampled at scoring time into
``return_risk:drift:{feature}`` zsets (member ``{ts}:{value}``, score = ts,
30-day window); the monitor compares the last 24h distribution against the
previous 30-day baseline per feature and aggregates a status.

Thresholds mirror the existing drift convention: > 0.25 DRIFT,
> 0.10 WARNING, else STABLE.
"""

import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from observability.drift import population_stability_index

DT = 86400.0
PSI_DRIFT = 0.25
PSI_WARNING = 0.10

RETURN_RISK_FEATURES = [
    "user_return_rate_30d",
    "user_return_rate_90d",
    "user_return_velocity_7d",
    "merchant_return_rate_30d",
    "txn_amount_risk",
    "user_cod_refusal_rate",
]

PREFIX = "return_risk:drift:"


async def record_return_risk_samples(redis, breakdown: dict[str, Any]) -> None:
    """Best-effort sample recording for the scored order (hot path safe).

    ``breakdown`` is the scorer's feature_breakdown: only numeric values
    are stored; a Redis hiccup is swallowed (scoring already happened).
    """
    try:
        now = time.time()
        pipe = await redis.pipeline()
        for name in RETURN_RISK_FEATURES:
            entry = breakdown.get(name)
            if not entry:
                continue
            value = entry.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            pipe.zadd(f"{PREFIX}{name}", {f"{now}:{float(value)}": now})
            pipe.zremrangebyscore(f"{PREFIX}{name}", 0, now - 30 * DT)
        await pipe.execute()
    except Exception:  # nosec B112 - sampling is best-effort; never affect the score
        return


class ReturnRiskDriftMonitor:
    """Compares the last 24h of each return-risk feature to its 30-day baseline."""

    def __init__(self, redis, features: list[str] | None = None):
        self.redis = redis
        self.features = features or RETURN_RISK_FEATURES

    async def check(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "features": {},
            "overall_status": "STABLE",
        }
        now = time.time()
        for feature in self.features:
            samples = await self._samples(feature, now)
            current = np.array([v for ts, v in samples if ts > now - DT])
            baseline = np.array([v for ts, v in samples if ts <= now - DT])
            psi = population_stability_index(baseline, current) if baseline.size and current.size else 0.0
            status = "DRIFT" if psi > PSI_DRIFT else "WARNING" if psi > PSI_WARNING else "STABLE"
            report["features"][feature] = {
                "psi": round(float(psi), 4),
                "status": status,
                "samples": int(len(current)),
                "baseline_samples": int(len(baseline)),
            }
            if status == "DRIFT":
                report["overall_status"] = "DRIFT"
            elif status == "WARNING" and report["overall_status"] == "STABLE":
                report["overall_status"] = "WARNING"
        return report

    async def _samples(self, feature: str, now: float) -> list[tuple[float, float]]:
        try:
            raw = await self.redis.zrangebyscore(f"{PREFIX}{feature}", 0, now)
        except Exception:  # nosec B112 - monitor is read-only and degrades silently
            return []
        samples: list[tuple[float, float]] = []
        for member in raw:
            try:
                ts_s, value_s = member.split(":", 1)
                samples.append((float(ts_s), float(value_s)))
            except (ValueError, TypeError):
                continue
        return samples

    @staticmethod
    def _ts_range() -> tuple[float, float]:
        base = datetime.utcnow() - timedelta(days=1)
        return base.timestamp(), base.timestamp() + DT
