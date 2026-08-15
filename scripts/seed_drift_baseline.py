"""Seed the "yesterday" window of the drift:feat:* zsets for PSI analysis.

The scoring route records feature samples under timestamps (zset scores).
PSI compares yesterday (T-24h..T-48h) against today (T-24h..T) and only
evaluates features that have >= min_samples samples in each window (see
observability.drift_report.compute_psi_report).

A fresh demo run only produces a handful of live samples, so this script:
  1. reads the monitored feature list + thresholds from the feature registry
     (monitoring: true entries under their drift_key, plus legacy L0 keys)
  2. replays every recorded live sample into yesterday's window (spread evenly)
  3. pads both windows to >= min_samples+20 by resampling recorded values with
     small multiplicative noise (per-feature default distributions on a
     pristine stack with no traffic yet) so the report has data to evaluate
  4. by default shifts one feature's yesterday baseline to demonstrate a
     flagged drift (PSI > threshold)

Usage:
    python scripts/seed_drift_baseline.py [--shift amount_total_1h 0.5]
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store.sync_redis import SyncRedisClient
from observability.drift_report import DRIFT_PREFIX, WINDOW_SECONDS, load_monitored_features


def main():
    parser = argparse.ArgumentParser(description="Seed yesterday window for PSI drift demo")
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--shift", nargs=2, metavar=("FEATURE", "FRACTION"),
                        default=["amount_total_1h", "0.5"],
                        help="feature to shift in the yesterday baseline (default: amount_total_1h 0.5)")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for deterministic padding")
    args = parser.parse_args()

    feature_keys, thresholds = load_monitored_features()
    min_samples = thresholds["min_samples"]
    pad_target = min_samples + 20

    redis = SyncRedisClient(host=args.redis_host, port=args.redis_port, db=0)
    now = time.time()
    today_start = now - WINDOW_SECONDS
    yesterday_start = now - 2 * WINDOW_SECONDS

    shift_feature, shift_frac = args.shift
    shift = float(shift_frac)
    rng = random.Random(args.seed)

    # Representative value ranges for a brand-new stack (no traffic yet). Used
    # only when a monitored key has zero recorded samples, so the PSI report
    # has data to evaluate even on first boot.
    DEFAULT_RANGES = {
        "txn_count_5m": (0, 8),
        "txn_count_1h": (0, 20),
        "amount_total_1h": (2000, 15000),
        "device_txn_count_24h": (0, 40),
        "distinct_users_last_24h": (1, 5),
        "distinct_merchants_1h": (1, 10),
        "inter_arrival_gap_min": (1, 480),
        "loc_dist_km": (0, 800),
        "merchant_round_share": (0.0, 1.0),
        "is_shell": (0, 1),
    }

    def sample_value(name: str) -> float:
        lo, hi = DEFAULT_RANGES.get(name, (0.0, 100.0))
        return rng.uniform(lo, hi)

    total = 0
    for name in feature_keys:
        key = f"{DRIFT_PREFIX}{name}"
        samples = redis.zrangebyscore_withscores(key, 0, now)
        values = []
        for member, ts in samples:
            try:
                values.append(float(member.split(":", 1)[1]))
            except (ValueError, TypeError, IndexError):
                continue

        def draw() -> float:
            return rng.choice(values) * rng.uniform(0.9, 1.1) if values else sample_value(name)

        def fill(ts_lo: float, ts_hi: float, count: int) -> dict[str, float]:
            mapping = {}
            for _ in range(count):
                value = draw()
                ts = rng.uniform(ts_lo, ts_hi)
                mapping[f"{ts}:{value}"] = ts
            return mapping

        yesterday_count = max(pad_target, len(values))
        today_count = max(pad_target, len(values))
        yesterday_map = fill(yesterday_start, yesterday_start + WINDOW_SECONDS - 900, yesterday_count)
        today_map = fill(today_start, today_start + WINDOW_SECONDS - 900, today_count)

        if name == shift_feature:
            shifted = {}
            for member, ts in yesterday_map.items():
                value = float(member.split(":", 1)[1]) * (1.0 + shift)
                shifted[f"{ts}:{value}"] = ts
            yesterday_map = shifted

        mapping = {**yesterday_map, **today_map}
        redis.zadd(key, mapping)
        total += len(mapping)
        print(f"  {name}: seeded {len(mapping)} samples "
              f"({yesterday_count} yesterday / {today_count} today)")

    print(f"seeded yesterday baseline: {total} samples across {len(feature_keys)} features")
    print(f"  min_samples gate: {min_samples}")
    if shift:
        print(f"  {shift_feature} yesterday baseline shifted by +{shift_frac} (drift demo)")


if __name__ == "__main__":
    main()