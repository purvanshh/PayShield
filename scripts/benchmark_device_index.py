import argparse
import asyncio
import logging
import statistics
import time
import uuid

from store.device_index import DeviceFingerprint, DeviceFingerprintIndex, DeviceFeatureExtractor
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark device fingerprint index")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--n-devices", type=int, default=100)
    parser.add_argument("--n-registrations", type=int, default=500)
    args = parser.parse_args()

    client = AsyncRedisClient(host=args.host, port=args.port)
    index = DeviceFingerprintIndex(client)
    extractor = DeviceFeatureExtractor(index)

    ping_ok = await client.ping()
    print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")
    if not ping_ok:
        return

    fake_user_id = f"bench_user_{uuid.uuid4().hex[:8]}"
    latencies = []
    for i in range(args.n_registrations):
        device_id = f"bench_device_{uuid.uuid4().hex[:12]}"
        fp = DeviceFingerprint(
            device_id=device_id,
            ip_address=f"192.168.{i % 256}.{(i * 7) % 256}",
            user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
            screen_resolution="1080x1920" if i % 2 == 0 else "1440x2560",
            timezone="America/New_York",
            language="en-US",
            canvas_hash=uuid.uuid4().hex,
            webgl_hash=uuid.uuid4().hex,
        )
        start = time.perf_counter()
        await index.register(device_id, fake_user_id, fp)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    print(f"\nRegister latency ({args.n_registrations} registrations):")
    print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
    print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  avg:   {statistics.mean(latencies):.3f} ms")

    device_id = f"bench_device_{uuid.uuid4().hex[:12]}"
    fp = DeviceFingerprint(
        device_id=device_id,
        ip_address="10.0.0.1",
        user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
        screen_resolution="1080x1920",
        timezone="America/New_York",
        language="en-US",
    )
    await index.register(device_id, fake_user_id, fp)

    print(f"\nExtracting device features...")
    start = time.perf_counter()
    features = await extractor.extract(device_id, fake_user_id)
    elapsed = (time.perf_counter() - start) * 1000
    print(f"Extract latency: {elapsed:.3f} ms")
    print(f"\nFeatures:")
    for k, v in features.items():
        print(f"  {k}: {v}")

    multi = await index.detect_multi_device(fake_user_id)
    print(f"\nMulti-device count for user: {multi}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
