"""PSI drift report between rolling 24h windows of scored features.

Features are recorded by the scoring route into `drift:feat:{name}` zsets
(member "{ts}:{value}", score = timestamp). This module compares yesterday's
distribution against today's per feature using a robust Population Stability
Index: shared quantile bin edges on the combined distribution, bin count
scaled to sample size, and Laplace smoothing (see observability.drift).
"""

import inspect
import logging
import math
import time
from datetime import datetime, timezone

import numpy as np

from observability.drift import population_stability_index

logger = logging.getLogger(__name__)

DRIFT_PREFIX = "drift:feat:"
WINDOW_SECONDS = 24 * 3600
FEATURE_KEYS = [
    "txn_count_5m",
    "txn_count_1h",
    "amount_total_1h",
    "device_txn_count_24h",
    "distinct_users_last_24h",
    "distinct_merchants_1h",
]


def interpret_psi(psi: float) -> str:
    if psi < 0.1:
        return "STABLE"
    if psi <= 0.25:
        return "MODERATE"
    return "DRIFT"


async def compute_psi_report(redis_client) -> dict:
    now = time.time()
    today_start = now - WINDOW_SECONDS
    yesterday_start = now - 2 * WINDOW_SECONDS

    async def fetch(key: str):
        result = redis_client.zrangebyscore_withscores(f"{DRIFT_PREFIX}{key}", 0, now)
        if inspect.isawaitable(result):
            result = await result
        return result or []

    features: dict[str, dict] = {}
    for key in FEATURE_KEYS:
        try:
            samples = await fetch(key)
            parsed = []
            for member, ts in samples:
                try:
                    value = float(member.split(":", 1)[1])
                    parsed.append((value, float(ts)))
                except (ValueError, TypeError, IndexError):
                    continue
            if not parsed:
                continue
            expected = np.array([v for v, ts in parsed if yesterday_start <= ts < today_start])
            actual = np.array([v for v, ts in parsed if ts >= today_start])
            n_bins = min(10, max(3, min(int(expected.size), int(actual.size)) // 5))
            if expected.size == 0 or actual.size == 0:
                features[key] = {"psi": None, "status": "INSUFFICIENT_DATA",
                                 "expected_samples": int(expected.size), "actual_samples": int(actual.size)}
                continue
            if expected.var() == 0 and actual.var() == 0 and float(expected[0]) == float(actual[0]):
                features[key] = {"psi": 0.0, "status": "STABLE", "n_bins": n_bins,
                                 "expected_samples": int(expected.size), "actual_samples": int(actual.size)}
                continue
            psi = population_stability_index(expected, actual, n_bins=n_bins)
            if not math.isfinite(psi):
                features[key] = {"psi": None, "status": "CONSTANT", "n_bins": n_bins,
                                 "expected_samples": int(expected.size), "actual_samples": int(actual.size)}
                continue
            features[key] = {
                "psi": round(psi, 4),
                "status": interpret_psi(psi),
                "n_bins": n_bins,
                "expected_samples": int(expected.size),
                "actual_samples": int(actual.size),
            }
        except Exception as e:
            logger.warning(f"drift computation failed for {key}: {e}")

    drifted = [k for k, v in features.items() if v.get("status") == "DRIFT"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_expected": "yesterday (T-24h to T-48h)",
        "window_actual": "today (T-24h to T)",
        "method": "PSI — shared quantile bins (scaled to sample size) + Laplace smoothing",
        "threshold": {"stable": 0.1, "drift": 0.25},
        "features": features,
        "drifted_features": drifted,
        "status": "DRIFT_DETECTED" if drifted else "NO_DRIFT_DETECTED",
    }
