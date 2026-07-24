import argparse
import asyncio
import logging
import statistics
import time
import uuid

from store.redis_client import AsyncRedisClient
from store.velocity import VelocityEngine, VelocityFeatureExtractor

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark velocity counters")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--n-txns", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    client = AsyncRedisClient(host=args.host, port=args.port)
    engine = VelocityEngine(client)
    extractor = VelocityFeatureExtractor(engine)
    user_id = f"bench_user_{uuid.uuid4().hex[:8]}"

    ping_ok = await client.ping()
    print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")
    if not ping_ok:
        return

    print(f"\nRecording {args.n_txns} transactions for user {user_id}...")

    latencies = []
    for i in range(args.n_txns):
        txn_id = uuid.uuid4().hex
        start = time.perf_counter()
        await engine.record_transaction(
            user_id=user_id,
            txn_id=txn_id,
            amount=round(10 + (i % 1000) * 0.01, 2),
            merchant_id=f"merchant_{i % 50}",
            country="US" if i % 2 == 0 else "GB",
        )
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nRecord latency ({args.n_txns} txns):")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  avg:   {statistics.mean(latencies):.3f} ms")

    print(f"\nExtracting velocity features...")
    start = time.perf_counter()
    features = await extractor.extract(user_id)
    elapsed = (time.perf_counter() - start) * 1000

    print(f"Extract latency: {elapsed:.3f} ms")
    print(f"\nFeatures:")
    for k, v in features.items():
        print(f"  {k}: {v}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
