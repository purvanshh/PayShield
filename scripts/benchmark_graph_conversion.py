import argparse
import asyncio
import logging
import statistics
import time
import uuid

import networkx as nx

from engine.graph_builder import EgoGraphExtractor, GraphFeatureExtractor
from engine.graph_loader import HeteroGraphConverter, _has_pyg
from store.neo4j_client import Neo4jGraphDB
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark NetworkX → PyG conversion")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--n-conversions", type=int, default=5)
    args = parser.parse_args()

    if not _has_pyg:
        print("PyTorch Geometric not installed. Install with: pip install torch torch-geometric")
        return

    neo4j_db = Neo4jGraphDB(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
    )
    redis_client = AsyncRedisClient(host=args.redis_host, port=args.redis_port)

    try:
        await neo4j_db.connect()
        print(f"Connected to Neo4j at {args.neo4j_uri}")

        test_users = await neo4j_db.run_query(
            "MATCH (u:User) RETURN u.user_id AS user_id LIMIT 3"
        )
        if not test_users:
            print("No users found. Seed with: python scripts/init_neo4j.py --seed")
            return

        extractor = EgoGraphExtractor(neo4j_db, redis_client)
        converter = HeteroGraphConverter()

        print(f"\nBenchmarking {args.n_conversions} graph conversions...")
        latencies = []

        for i in range(args.n_conversions):
            user = test_users[i % len(test_users)]
            user_id = user["user_id"]
            merchant_id = f"seed_merchant_{i % 10}"

            graph = await extractor.extract(user_id, merchant_id, hops=args.hops)

            start = time.perf_counter()
            data = converter.convert(graph, target_user_id=user_id)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        print(f"\nConversion latency ({args.n_conversions} runs):")
        print(f"  p50:   {latencies[int(len(latencies)*0.50)]:.3f} ms")
        print(f"  p95:   {latencies[int(len(latencies)*0.95)]:.3f} ms")
        print(f"  p99:   {latencies[int(len(latencies)*0.99)]:.3f} ms")
        print(f"  avg:   {statistics.mean(latencies):.3f} ms")

        print(f"\nHeteroData structure (last conversion):")
        print(f"  Metadata: {data.metadata()}")

        for ntype in data.node_types:
            x = data[ntype].x
            print(f"  {ntype}: x shape {x.shape}")

        for etype in data.edge_types:
            ei = data[etype].edge_index
            print(f"  {etype}: edge_index shape {ei.shape}")

        if "User" in data.node_types and data["User"].get("target_node") is not None:
            print(f"  Target node (User): {data['User'].target_node.tolist()}")

        print(f"\nBenchmark complete!")

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        await neo4j_db.close()
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
