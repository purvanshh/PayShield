"""PSI drift report: yesterday vs today feature distributions.

Usage:
    python scripts/run_drift_report.py [--redis-host HOST] [--redis-port PORT]

Reads `drift:feat:*` zsets written by the scoring route, computes PSI per
feature between rolling 24h windows, prints a report, and writes
`observability/reports/drift_YYYYMMDD.json`.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store.sync_redis import SyncRedisClient
from observability.drift_report import compute_psi_report


def main():
    parser = argparse.ArgumentParser(description="PSI drift report (yesterday vs today)")
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    args = parser.parse_args()

    redis = SyncRedisClient(host=args.redis_host, port=args.redis_port, db=0)
    if not redis.ping():
        print("ERROR: cannot reach Redis", file=sys.stderr)
        sys.exit(1)

    report = asyncio.run(compute_psi_report(redis))

    print("=" * 60)
    print("PSI DRIFT REPORT — yesterday vs today")
    print(f"generated_at: {report['generated_at']}")
    print(f"method: {report['method']} | thresholds: {report['threshold']}")
    print("=" * 60)
    for name, f in report["features"].items():
        psi = f"{f['psi']:.4f}" if f.get("psi") is not None else "n/a"
        print(f"  {name:<28} PSI={psi:<8} status={f['status']:<18} "
              f"(expected={f['expected_samples']}, actual={f['actual_samples']})")
    print("-" * 60)
    print(f"drifted_features: {report['drifted_features'] or 'none'}")
    print(f"overall: {report['status']}")

    out_dir = "observability/reports"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"drift_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"report saved: {out_path}")


if __name__ == "__main__":
    main()
