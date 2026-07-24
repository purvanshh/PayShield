import argparse
import asyncio
import logging
import uuid

from store.neo4j_client import Neo4jGraphDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Initialize Neo4j graph schema")
    parser.add_argument("--uri", default="bolt://localhost:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="password")
    parser.add_argument("--seed", action="store_true", help="Seed with sample data")
    parser.add_argument("--n-users", type=int, default=10, help="Users to seed")
    parser.add_argument("--n-txns", type=int, default=50, help="Transactions to seed")
    args = parser.parse_args()

    db = Neo4jGraphDB(uri=args.uri, user=args.user, password=args.password)

    try:
        await db.connect()
        print(f"Connected to Neo4j at {args.uri}")

        print("\nInitializing schema...")
        await db.initialize_schema()
        print("  Constraints and indexes created")

        if args.seed:
            print(f"\nSeeding {args.n_users} users and {args.n_txns} transactions...")
            for i in range(args.n_users):
                user_id = f"seed_user_{i}"
                await db.create_user(user_id, {"risk_score": round(i * 0.1, 2)})

                device_id = f"seed_device_{i}"
                await db.create_device(device_id, uuid.uuid4().hex[:16])
                await db.link_user_device(user_id, device_id)

            categories = ["retail", "food", "travel", "entertainment", "health"]
            for i in range(args.n_txns):
                merchant_id = f"seed_merchant_{i % 10}"
                await db.create_merchant(
                    merchant_id,
                    {"category": categories[i % len(categories)], "country": "US"},
                )
                await db.create_transaction(
                    txn_id=f"seed_txn_{i}",
                    user_id=f"seed_user_{i % args.n_users}",
                    merchant_id=merchant_id,
                    amount=round(10 + (i % 1000) * 0.99, 2),
                    device_id=f"seed_device_{i % args.n_users}",
                )
            print(f"  {args.n_users} users, {args.n_txns} transactions seeded")

        print("\nVerifying schema...")
        constraints = await db.run_query("SHOW CONSTRAINTS")
        print(f"  Constraints: {len(constraints)}")
        for c in constraints:
            print(f"    - {c}")

        indexes = await db.run_query("SHOW INDEXES")
        print(f"  Indexes: {len(indexes)}")
        for idx in indexes:
            print(f"    - {idx}")

        print("\nSchema initialization complete!")

    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nMake sure Neo4j is running:")
        print("  docker run --name payshield-neo4j \\")
        print("    -p 7474:7474 -p 7687:7687 \\")
        print("    -e NEO4J_AUTH=neo4j/password \\")
        print("    neo4j:5-enterprise")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
