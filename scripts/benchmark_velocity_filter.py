import argparse
import asyncio
import logging
import statistics
import time
import uuid

from engine.statistical_filter import VelocityFilter
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark velocity filter")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--n-evaluations", type=int, default=1000)
    args = parser.parse_args()

    redis_client = AsyncRedisClient(host=args.redis_host, port=args.redis_port)
    ping_ok = await redis_client.ping()
    print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")

    filter_engine = VelocityFilter(redis_client=redis_client if ping_ok else None)

    normal_features = {
        "txn_count_1m": 0,
        "txn_count_5m": 1,
        "txn_count_15m": 2,
        "txn_count_1h": 3,
        "txn_count_24h": 8,
        "amount_total_1h": 450.00,
        "amount_avg_1h": 150.00,
        "distinct_merchants_1h": 2,
        "burst_score": 1.2,
        "device_txn_count_24h": 3,
        "distinct_users_last_24h": 1,
        "ip_txn_count_5m": 1,
    }

    burst_features = {
        "txn_count_1m": 8,
        "txn_count_5m": 15,
        "txn_count_15m": 22,
        "txn_count_1h": 30,
        "txn_count_24h": 45,
        "amount_total_1h": 15000.00,
        "amount_avg_1h": 500.00,
        "distinct_merchants_1h": 12,
        "burst_score": 8.5,
        "device_txn_count_24h": 25,
        "distinct_users_last_24h": 4,
        "ip_txn_count_5m": 20,
    }

    deviations = {
        "amount_z_score": 0.5,
        "time_hour_z_score": 0.2,
        "baseline_txn_count_24h": 3,
        "median_amount_30d": 300,
    }

    print("\nTest: Normal transaction")
    result = await filter_engine.evaluate(normal_features, deviations)
    print(f"  Action: {result.action} | Confidence: {result.confidence} | Rules: {result.triggered_rules}")

    print("\nTest: Burst attack transaction")
    result = await filter_engine.evaluate(burst_features, deviations)
    print(f"  Action: {result.action} | Confidence: {result.confidence} | Rules: {result.triggered_rules}")

    print(f"\nBenchmarking {args.n_evaluations} evaluations...")
    latencies = []
    for i in range(args.n_evaluations):
        feats = burst_features if i % 10 == 0 else normal_features
        start = time.perf_counter()
        await filter_engine.evaluate(feats, deviations)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nEvaluation latency ({args.n_evaluations} runs):")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.6f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.6f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.6f} ms")
    print(f"  avg:   {statistics.mean(latencies):.6f} ms")

    await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
