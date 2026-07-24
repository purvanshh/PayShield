import argparse
import asyncio
import logging
from datetime import datetime, timezone

from store.graph_snapshot import GraphSnapshotManager
from store.neo4j_client import Neo4jGraphDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Create a graph snapshot")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--label", default="manual", help="Snapshot label")
    args = parser.parse_args()

    neo4j_db = Neo4jGraphDB(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
    )

    try:
        await neo4j_db.connect()
        print(f"Connected to Neo4j at {args.neo4j_uri}")

        manager = GraphSnapshotManager(neo4j_db)

        ts = datetime.now(timezone.utc)
        snapshot_id = await manager.create_snapshot(timestamp=ts, label=args.label)

        print(f"\nSnapshot created: {snapshot_id}")

        meta_path = f"data/snapshots/{snapshot_id}/meta.json"
        print(f"Metadata: {meta_path}")

        snapshots = await manager.list_snapshots()
        print(f"\nTotal snapshots: {len(snapshots)}")

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        await neo4j_db.close()


if __name__ == "__main__":
    asyncio.run(main())
