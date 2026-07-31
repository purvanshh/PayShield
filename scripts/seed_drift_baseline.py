"""Seed the "yesterday" window of the drift:feat:* zsets for PSI analysis.

The scoring route records feature samples under timestamps (zset scores).
PSI compares yesterday (T-24h..T-48h) against today (T-24h..T). This script
replays the currently recorded live samples as yesterday's baseline, and by
default shifts one feature's distribution to demonstrate drift detection.

Usage:
    python scripts/seed_drift_baseline.py [--shift amount_total_1h 0.5]
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store.sync_redis import SyncRedisClient
from observability.drift_report import FEATURE_KEYS, DRIFT_PREFIX, WINDOW_SECONDS


def main():
    parser = argparse.ArgumentParser(description="Seed yesterday window for PSI drift demo")
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--shift", nargs=2, metavar=("FEATURE", "FRACTION"),
                        default=["amount_total_1h", "0.5"],
                        help="feature to shift in the yesterday baseline (default: amount_total_1h 0.5)")
    args = parser.parse_args()

    redis = SyncRedisClient(host=args.redis_host, port=args.redis_port, db=0)
    now = time.time()
    yesterday_end = now - WINDOW_SECONDS
    yesterday_start = now - 2 * WINDOW_SECONDS

    shift_feature, shift_frac = args.shift
    shift = float(shift_frac)

    total = 0
    for name in FEATURE_KEYS:
        key = f"{DRIFT_PREFIX}{name}"
        samples = redis.zrangebyscore_withscores(key, 0, now)
        if not samples:
            continue
        # Replay today's recorded values into yesterday's window (spread evenly),
        # optionally shifting one feature to demonstrate drift detection
        shifted = 1.0 + (shift if name == shift_feature else 0.0)
        count = len(samples)
        mapping = {}
        for idx, (member, _ts) in enumerate(samples):
            try:
                value = float(member.split(":", 1)[1]) * shifted
                offset = int(idx * (WINDOW_SECONDS - 1800) / max(count, 1)) + 60
                ts = yesterday_start + offset
                mapping[f"{ts}:{value}"] = ts
            except (ValueError, TypeError, IndexError):
                continue
            total += 1
        redis.zadd(key, mapping)

    print(f"seeded yesterday baseline: {total} samples across {len(FEATURE_KEYS)} features")
    if shift:
        print(f"  {shift_feature} baseline shifted by +{shift_frac} (drift demo)")


if __name__ == "__main__":
    main()
