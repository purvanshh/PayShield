import argparse
import asyncio
import logging
import statistics
import time

from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark Redis operations")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--n-ops", type=int, default=10000)
    parser.add_argument("--value-size", type=int, default=128)
    args = parser.parse_args()

    client = AsyncRedisClient(host=args.host, port=args.port)

    ping_ok = await client.ping()
    print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")
    if not ping_ok:
        return

    value = "x" * args.value_size
    payload = {f"key_{i}": value for i in range(args.n_ops)}

    print(f"\nBenchmarking {args.n_ops} operations (value size: {args.value_size}B)...")

    latencies = []
    for i in range(args.n_ops):
        key = f"bench:set:{i}"
        start = time.perf_counter()
        await client.set(key, value, ttl=3600)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)
        if (i + 1) % 2000 == 0:
            print(f"  SET: {i+1}/{args.n_ops}")

    latencies.sort()
    print(f"\nSET operations:")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  avg:   {statistics.mean(latencies):.3f} ms")

    latencies = []
    for i in range(args.n_ops):
        key = f"bench:set:{i}"
        start = time.perf_counter()
        await client.get(key)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nGET operations:")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  avg:   {statistics.mean(latencies):.3f} ms")

    for i in range(args.n_ops):
        await client.delete(f"bench:set:{i}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
