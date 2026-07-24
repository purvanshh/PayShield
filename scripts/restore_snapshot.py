import argparse
import asyncio
import logging

from store.graph_snapshot import GraphSnapshotManager
from store.neo4j_client import Neo4jGraphDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Restore a graph snapshot")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--snapshot-id", required=True, help="Snapshot ID to restore")
    parser.add_argument("--dry-run", action="store_true", help="Load into memory without writing to Neo4j")
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

        print(f"\nLoading snapshot: {args.snapshot_id}")
        graph = await manager.load_snapshot(args.snapshot_id)

        print(f"  Nodes: {graph.number_of_nodes()}")
        print(f"  Edges: {graph.number_of_edges()}")

        node_types: dict[str, int] = {}
        for _, d in graph.nodes(data=True):
            ntype = d.get("node_type", "Unknown")
            node_types[ntype] = node_types.get(ntype, 0) + 1

        print(f"\nNode types:")
        for ntype, count in sorted(node_types.items(), key=lambda x: -x[1]):
            print(f"  {ntype}: {count}")

        if args.dry_run:
            print(f"\nDry-run: snapshot loaded in memory only. No data written to Neo4j.")
        else:
            print(f"\nRestoring snapshot to Neo4j...")
            for nid, d in graph.nodes(data=True):
                ntype = d.get("node_type", "Unknown").lower()
                if ntype == "user":
                    await neo4j_db.create_user(nid, d)
                elif ntype == "merchant":
                    await neo4j_db.create_merchant(nid, d)
                elif ntype == "device":
                    fp_hash = d.get("fingerprint_hash", nid)
                    await neo4j_db.create_device(nid, fp_hash, d)

            edge_count = 0
            for u, v, d in graph.edges(data=True):
                edge_type = d.get("edge_type", "")
                if edge_type == "performed":
                    txn_id = f"restored_{u}_{v}_{edge_count}"
                    await neo4j_db.create_transaction(txn_id, u, v, float(d.get("amount", 0)))
                    edge_count += 1

            print(f"  Restored {graph.number_of_nodes()} nodes and {edge_count} edges")

        print(f"\nRestore complete!")

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        await neo4j_db.close()


if __name__ == "__main__":
    asyncio.run(main())
