import argparse
import asyncio
import logging
import statistics
import time
import uuid

from store.baselines import BehavioralBaselineStore, BehavioralFeatureExtractor
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark behavioral baselines")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--n-updates", type=int, default=500)
    args = parser.parse_args()

    client = AsyncRedisClient(host=args.host, port=args.port)
    store = BehavioralBaselineStore(client)
    extractor = BehavioralFeatureExtractor(store)

    ping_ok = await client.ping()
    print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")
    if not ping_ok:
        return

    user_id = f"bench_user_{uuid.uuid4().hex[:8]}"

    print(f"\nUpdating baseline ({args.n_updates} updates)...")
    latencies = []
    for i in range(args.n_updates):
        start = time.perf_counter()
        await store.update_baseline(
            user_id=user_id,
            amount=round(50 + (i % 100) * 2.5, 2),
            merchant_id=f"merchant_{i % 20}",
            country="US" if i % 3 == 0 else "GB" if i % 3 == 1 else "DE",
            device_id=f"device_{i % 3}",
        )
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nUpdate latency ({args.n_updates} updates):")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  avg:   {statistics.mean(latencies):.3f} ms")

    print(f"\nComputing deviation for current transaction...")
    start = time.perf_counter()
    features = await extractor.extract(
        user_id=user_id,
        amount=9999.99,
        merchant_id="merchant_unknown",
        country="RU",
    )
    elapsed = (time.perf_counter() - start) * 1000
    print(f"Compute latency: {elapsed:.3f} ms")
    print(f"\nDeviation features:")
    for k, v in features.items():
        print(f"  {k}: {v}")

    baseline = await store.get_baseline(user_id)
    if baseline:
        print(f"\nBaseline profile:")
        print(f"  txn_count:       {baseline.txn_amount_stats.n}")
        print(f"  amount_mean:     {baseline.txn_amount_stats.mean:.2f}")
        print(f"  amount_std:      {baseline.txn_amount_stats.std:.2f}")
        print(f"  merchant_div:    {baseline.merchant_diversity}")
        print(f"  country_div:     {baseline.country_diversity}")
        print(f"  device_count:    {baseline.device_count}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
