import json
import logging
import os
import time
from datetime import datetime, timezone

import networkx as nx

logger = logging.getLogger(__name__)

SNAPSHOT_BASE_DIR = "data/snapshots"


class GraphSnapshotManager:
    def __init__(self, neo4j_client, base_dir: str = SNAPSHOT_BASE_DIR):
        self.neo4j = neo4j_client
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    async def create_snapshot(self, timestamp: datetime | None = None, label: str = "snapshot") -> str:
        ts = timestamp or datetime.now(timezone.utc)
        snapshot_id = f"{label}_{ts.strftime('%Y%m%d_%H%M%S')}"
        snapshot_dir = os.path.join(self.base_dir, snapshot_id)
        os.makedirs(snapshot_dir, exist_ok=True)

        nodes = await self.neo4j.run_query(
            "MATCH (n) RETURN n, labels(n) AS labels LIMIT 10000"
        )
        edges = await self.neo4j.run_query(
            "MATCH ()-[r]->() RETURN r, type(r) AS rel_type, "
            "startNode(r).user_id AS src_user, startNode(r).merchant_id AS src_merchant, "
            "startNode(r).device_id AS src_device, startNode(r).txn_id AS src_txn, "
            "endNode(r).user_id AS dst_user, endNode(r).merchant_id AS dst_merchant, "
            "endNode(r).device_id AS dst_device, endNode(r).txn_id AS dst_txn "
            "LIMIT 20000"
        )

        node_file = os.path.join(snapshot_dir, "nodes.json")
        edge_file = os.path.join(snapshot_dir, "edges.json")
        meta_file = os.path.join(snapshot_dir, "meta.json")

        serialized_nodes = []
        for record in nodes:
            n = record.get("n", {})
            node_id = None
            for field in ["user_id", "merchant_id", "device_id", "txn_id"]:
                if n.get(field):
                    node_id = n[field]
                    break
            if not node_id:
                node_id = str(id(n))

            labels = record.get("labels", ["Unknown"])
            serialized_nodes.append({
                "id": str(node_id),
                "labels": labels,
                "props": {k: str(v) if isinstance(v, datetime) else v for k, v in n.items() if k not in ("element_id",)},
            })

        serialized_edges = []
        for record in edges:
            r = record.get("r", {})
            rel_type = record.get("rel_type", "RELATED")
            src = None
            for field in ["user_id", "merchant_id", "device_id", "txn_id"]:
                val = record.get(f"src_{field}")
                if val:
                    src = str(val)
                    break
            dst = None
            for field in ["user_id", "merchant_id", "device_id", "txn_id"]:
                val = record.get(f"dst_{field}")
                if val:
                    dst = str(val)
                    break
            if src and dst:
                serialized_edges.append({
                    "src": src,
                    "dst": dst,
                    "type": rel_type,
                    "props": {k: str(v) if isinstance(v, datetime) else v for k, v in r.items() if k != "element_id"},
                })

        with open(node_file, "w") as f:
            json.dump(serialized_nodes, f, default=str)
        with open(edge_file, "w") as f:
            json.dump(serialized_edges, f, default=str)

        meta = {
            "snapshot_id": snapshot_id,
            "label": label,
            "created_at": ts.isoformat(),
            "node_count": len(serialized_nodes),
            "edge_count": len(serialized_edges),
            "format": "json",
        }
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Snapshot {snapshot_id}: {meta['node_count']} nodes, {meta['edge_count']} edges")
        return snapshot_id

    async def load_snapshot(self, snapshot_id: str) -> nx.Graph:
        snapshot_dir = os.path.join(self.base_dir, snapshot_id)
        if not os.path.exists(snapshot_dir):
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        node_file = os.path.join(snapshot_dir, "nodes.json")
        edge_file = os.path.join(snapshot_dir, "edges.json")

        graph = nx.Graph()

        if os.path.exists(node_file):
            with open(node_file) as f:
                nodes = json.load(f)
            for nd in nodes:
                nid = nd["id"]
                labels = nd.get("labels", ["Unknown"])
                graph.add_node(nid, node_type=labels[0] if labels else "Unknown", **nd.get("props", {}))

        if os.path.exists(edge_file):
            with open(edge_file) as f:
                edges = json.load(f)
            for ed in edges:
                graph.add_edge(ed["src"], ed["dst"], edge_type=ed.get("type", "RELATED"),
                               **ed.get("props", {}))

        logger.info(f"Loaded snapshot {snapshot_id}: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        return graph

    async def get_snapshot_at_time(self, timestamp: datetime) -> nx.Graph:
        snapshots = sorted(os.listdir(self.base_dir)) if os.path.isdir(self.base_dir) else []

        best_snapshot = None
        for snap_id in reversed(snapshots):
            meta_path = os.path.join(self.base_dir, snap_id, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                snap_time = datetime.fromisoformat(meta["created_at"])
                if snap_time <= timestamp:
                    best_snapshot = snap_id
                    break

        if best_snapshot:
            logger.info(f"Found snapshot {best_snapshot} at <= {timestamp}")
            return await self.load_snapshot(best_snapshot)

        logger.warning(f"No snapshot found at or before {timestamp}, returning empty graph")
        return nx.Graph()

    async def list_snapshots(self) -> list[dict]:
        if not os.path.isdir(self.base_dir):
            return []
        snapshots = []
        for snap_id in sorted(os.listdir(self.base_dir), reverse=True):
            meta_path = os.path.join(self.base_dir, snap_id, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    snapshots.append(json.load(f))
        return snapshots


class TransactionLog:
    LOG_FILE = "data/graph_transaction_log.jsonl"
    OPERATIONS = ("CREATE_NODE", "CREATE_EDGE", "UPDATE_PROP", "DELETE_NODE", "DELETE_EDGE")

    def __init__(self, log_file: str = LOG_FILE):
        self.log_file = log_file
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    async def append(self, operation: str, entity_type: str, entity_id: str, properties: dict | None = None):
        if operation not in self.OPERATIONS:
            raise ValueError(f"Invalid operation: {operation}. Must be one of {self.OPERATIONS}")

        entry = {
            "timestamp": time.time(),
            "datetime": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "properties_json": json.dumps(properties) if properties else "{}",
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    async def replay(self, start_time: float | None = None, end_time: float | None = None) -> list[dict]:
        if not os.path.exists(self.log_file):
            return []

        entries = []
        with open(self.log_file) as f:
            for line in f:
                entry = json.loads(line.strip())
                ts = entry["timestamp"]
                if start_time and ts < start_time:
                    continue
                if end_time and ts > end_time:
                    continue
                entries.append(entry)

        return entries

    async def get_mutations_since(self, timestamp: float) -> list[dict]:
        return await self.replay(start_time=timestamp)

    async def get_statistics(self) -> dict:
        entries = await self.replay()
        stats = {
            "total_entries": len(entries),
            "operations": {},
            "entity_types": {},
            "time_range": None,
        }
        for entry in entries:
            op = entry["operation"]
            stats["operations"][op] = stats["operations"].get(op, 0) + 1
            etype = entry["entity_type"]
            stats["entity_types"][etype] = stats["entity_types"].get(etype, 0) + 1
        if entries:
            stats["time_range"] = {
                "start": entries[0]["datetime"],
                "end": entries[-1]["datetime"],
            }
        return stats
