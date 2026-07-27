import argparse
import statistics
import time
from datetime import datetime

from data.synthetic_upi import SyntheticUPIGenerator
from store.sync_redis import SyncRedisClient as RedisClient
from store.feature_store import FeatureStore
from store.graph_db import GraphDB
from engine.ensemble import EnsembleScorer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-requests", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    args = parser.parse_args()

    print("Generating synthetic data...")
    gen = SyntheticUPIGenerator(n_users=500, n_transactions=5000, fraud_ratio=0.05)
    df = gen.generate()
    print(f"Generated {len(df)} transactions")

    redis = RedisClient()
    feature_store = FeatureStore(redis)
    graph_db = GraphDB()
    ensemble = EnsembleScorer(graph_db)

    latencies = []
    txns = df.to_dict("records")

    print(f"Warmup: {args.warmup} requests...")
    for i in range(args.warmup):
        txn = txns[i % len(txns)]
        start = time.time()
        ensemble.score(txn, feature_store)
        elapsed = (time.time() - start) * 1000
        latencies.append(elapsed)

    print(f"Benchmark: {args.n_requests} requests...")
    latencies = []
    for i in range(args.n_requests):
        txn = txns[i % len(txns)]
        start = time.time()
        result = ensemble.score(txn, feature_store)
        elapsed = (time.time() - start) * 1000
        latencies.append(elapsed)

        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{args.n_requests} completed")

    latencies.sort()
    p50 = statistics.median(latencies)
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = statistics.mean(latencies)
    tps = 1000 / avg * 1000 if avg > 0 else 0

    print(f"\n{'─' * 50}")
    print(f"Latency Benchmark Results ({args.n_requests} requests)")
    print(f"{'─' * 50}")
    print(f"  Average: {avg:.2f} ms")
    print(f"  p50:     {p50:.2f} ms")
    print(f"  p90:     {p90:.2f} ms")
    print(f"  p95:     {p95:.2f} ms")
    print(f"  p99:     {p99:.2f} ms")
    print(f"  Min:     {min(latencies):.2f} ms")
    print(f"  Max:     {max(latencies):.2f} ms")
    print(f"  Est. TPS: {tps:.0f}")
    print(f"{'─' * 50}")

    redis.close()


if __name__ == "__main__":
    main()
