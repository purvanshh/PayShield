"""PSI drift report between rolling 24h windows of scored features.

Features are recorded by the scoring route into `drift:feat:{name}` zsets
(member "{ts}:{value}", score = timestamp). This module compares yesterday's
distribution against today's per feature using a robust Population Stability
Index: shared quantile bin edges on the combined distribution, bin count
scaled to sample size, and Laplace smoothing (see observability.drift).

Which features are monitored is driven by the global feature registry
(`configs/feature_registry.yaml`): every entry with `monitoring: true` is
reported under its `drift_key` (defaults to the feature name). The legacy
L0 velocity features recorded since before the registry are kept alongside.
"""

import inspect
import logging
import math
import os
import time
from datetime import datetime, timezone

import numpy as np
import yaml

from observability.drift import population_stability_index

logger = logging.getLogger(__name__)

DRIFT_PREFIX = "drift:feat:"
WINDOW_SECONDS = 24 * 3600
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs",
    "feature_registry.yaml",
)
# L0 velocity features recorded continuously since before the registry got
# `monitoring` flags — kept so historical drift coverage is not lost.
LEGACY_FEATURE_KEYS = [
    "amount_total_1h",
    "device_txn_count_24h",
    "distinct_users_last_24h",
    "distinct_merchants_1h",
]


def load_monitored_features(config_path: str = DEFAULT_CONFIG_PATH) -> tuple[list[str], dict]:
    """Return (drift keys to monitor, skew thresholds) from the feature registry.

    Every registry entry with `monitoring: true` contributes its `drift_key`
    (the zset actually written by the scoring route, defaulting to the feature
    name). Legacy L0 keys are appended. Skew thresholds come from
    `skew_detection` (psi_threshold, min_samples).
    """
    thresholds = {"psi_threshold": 0.25, "min_samples": 100}
    keys: list[str] = []
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        skew = data.get("skew_detection", {})
        thresholds["psi_threshold"] = float(skew.get("psi_threshold", 0.25))
        thresholds["min_samples"] = int(skew.get("min_samples", 100))
        for entry in data.get("features", []):
            if not entry.get("monitoring", False):
                continue
            key = entry.get("drift_key") or entry["name"]
            if key not in keys:
                keys.append(key)
    except Exception as e:
        logger.warning(f"drift config load failed ({config_path}): {e}")
    return [key for key in keys if key not in LEGACY_FEATURE_KEYS] + list(LEGACY_FEATURE_KEYS), thresholds


def interpret_psi(psi: float, drift_threshold: float = 0.25) -> str:
    if psi < 0.1:
        return "STABLE"
    if psi <= drift_threshold:
        return "MODERATE"
    return "DRIFT"


async def compute_psi_report(redis_client, config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    feature_keys, thresholds = load_monitored_features(config_path)
    psi_threshold = thresholds["psi_threshold"]
    min_samples = thresholds["min_samples"]
    now = time.time()
    today_start = now - WINDOW_SECONDS
    yesterday_start = now - 2 * WINDOW_SECONDS

    async def fetch(key: str):
        result = redis_client.zrangebyscore_withscores(f"{DRIFT_PREFIX}{key}", 0, now)
        if inspect.isawaitable(result):
            result = await result
        return result or []

    features: dict[str, dict] = {}
    for key in feature_keys:
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
            if expected.size < min_samples or actual.size < min_samples:
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
                "status": interpret_psi(psi, psi_threshold),
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
        "method": "PSI — shared quantile bins (scaled to sample size) + Laplace smoothing; exact-value binning for low-cardinality features",
        "threshold": {"stable": 0.1, "drift": psi_threshold, "min_samples": min_samples},
        "feature_registry": config_path,
        "features": features,
        "drifted_features": drifted,
        "status": "DRIFT_DETECTED" if drifted else "NO_DRIFT_DETECTED",
    }
