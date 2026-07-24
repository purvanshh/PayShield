import argparse
import asyncio
import logging

from engine.graph_builder import (
    EgoGraphExtractor,
    FraudGraphFeatureExtractor,
    GraphFeatureExtractor,
)
from store.neo4j_client import Neo4jGraphDB
from store.redis_client import AsyncRedisClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Analyze fraud-specific graph features")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--redis-host", default="localhost")
    parser.add_argument("--redis-port", type=int, default=6379)
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
        ping_ok = await redis_client.ping()
        print(f"Redis: {'OK' if ping_ok else 'FAIL'} | Neo4j: Connected\n")

        extractor = EgoGraphExtractor(neo4j_db, redis_client)
        struct_extractor = GraphFeatureExtractor()
        fraud_extractor = FraudGraphFeatureExtractor()

        test_users = await neo4j_db.run_query(
            "MATCH (u:User) RETURN u.user_id AS user_id LIMIT 5"
        )
        if not test_users:
            print("No users found. Seed with: python scripts/init_neo4j.py --seed")
            return

        print(f"{'Graph Feature Analysis':=^60}\n")

        for i, user in enumerate(test_users):
            user_id = user["user_id"]
            merchant_id = f"seed_merchant_{i}"

            graph = await extractor.extract(user_id, merchant_id, hops=args.hops)

            struct_feats = struct_extractor.extract_structural_features(graph, user_id)
            fraud_feats = fraud_extractor.extract_all(graph, user_id)

            print(f"User: {user_id}  |  Nodes: {graph.number_of_nodes()}  Edges: {graph.number_of_edges()}")
            print(f"  Structural:")
            for k, v in struct_feats.to_dict().items():
                print(f"    {k}: {v}")
            print(f"  Fraud-specific:")
            for k, v in fraud_feats.to_dict().items():
                print(f"    {k}: {v}")

            if i < len(test_users) - 1:
                user_b = test_users[i + 1]["user_id"]
                mutual = fraud_extractor.extract_mutual_transaction_partners(graph, user_id, user_b)
                print(f"  Mutual partners with {user_b}: {mutual}")

            cycles = fraud_extractor.extract_money_flow_cycles(graph, user_id)
            if cycles:
                print(f"  Money flow cycles: {len(cycles)}")
                for cycle in cycles:
                    print(f"    {' → '.join(cycle)}")
            else:
                print(f"  Money flow cycles: none")

            print()

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        await neo4j_db.close()
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
