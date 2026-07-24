import argparse
import asyncio
import logging
import statistics
import time
import uuid

from engine.graph_builder import EgoGraphExtractor, GraphFeatureExtractor
from store.neo4j_client import Neo4jGraphDB
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark ego-graph extraction")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--n-extractions", type=int, default=10)
    parser.add_argument("--hops", type=int, default=2)
    args = parser.parse_args()

    neo4j_db = Neo4jGraphDB(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
    )
    redis_client = AsyncRedisClient(host=args.redis_host, port=args.redis_port)

    try:
        await neo4j_db.connect()
        print(f"Connected to Neo4j at {args.neo4j_uri}")

        ping_ok = await redis_client.ping()
        print(f"Redis health: {'OK' if ping_ok else 'FAIL'}")

        extractor = EgoGraphExtractor(neo4j_db, redis_client)
        feature_extractor = GraphFeatureExtractor()

        test_users = await neo4j_db.run_query(
            "MATCH (u:User) RETURN u.user_id AS user_id LIMIT 5"
        )
        if not test_users:
            print("\nNo users found in Neo4j. Seed data first with: python scripts/init_neo4j.py --seed")
            return

        print(f"\nBenchmarking {args.n_extractions} ego-graph extractions (hops={args.hops})...")
        latencies = []

        for i in range(args.n_extractions):
            user = test_users[i % len(test_users)]
            user_id = user["user_id"]
            merchant_id = f"seed_merchant_{i % 10}"

            start = time.perf_counter()
            graph = await extractor.extract(user_id, merchant_id, hops=args.hops)
            features = feature_extractor.extract_structural_features(graph, user_id)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        print(f"\nEgo-graph extraction latency ({args.n_extractions} runs):")
        print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
        print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
        print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
        print(f"  avg:   {statistics.mean(latencies):.3f} ms")

        print(f"\nCached extraction (second call)...")
        user = test_users[0]
        start = time.perf_counter()
        graph = await extractor.extract(user["user_id"], "seed_merchant_0", hops=args.hops)
        features = feature_extractor.extract_structural_features(graph, user["user_id"])
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  Cached latency: {elapsed:.3f} ms")
        print(f"  Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}")

        print(f"\nStructural features:")
        feat_dict = features.to_dict()
        for k, v in feat_dict.items():
            print(f"  {k}: {v}")

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        await neo4j_db.close()
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
