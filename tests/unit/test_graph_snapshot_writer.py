# ruff: noqa: ARG001, ARG002, ARG005, ASYNC230, ASYNC240 -- test doubles + async file helpers

import json
import os
from datetime import UTC, datetime

import pytest

from store.graph_snapshot import GraphSnapshotManager, TransactionLog
from store.graph_writer import GraphDBWriter, device_users_key


class FakeNeo4j:
    def __init__(self, nodes=None, edges=None):
        self.nodes = nodes or [
            {
                "n": {"user_id": "U1", "amount": 100},
                "labels": ["User"],
            },
            {
                "n": {"merchant_id": "M1", "spend": 50.5},
                "labels": ["Merchant"],
            },
            {
                "n": {"x": 1},
                "labels": [],
            },
        ]
        self.edges = edges or [
            {
                "r": {"amount": 20},
                "rel_type": "TRANSACTION",
                "src_user": "U1",
                "dst_merchant": "M1",
            }
        ]

    async def run_query(self, query, **params):
        if query.startswith("MATCH (n) RETURN n"):
            return self.nodes
        return self.edges


class TestGraphSnapshotManager:
    @pytest.mark.asyncio
    async def test_create_and_load_snapshot(self, tmp_path):
        manager = GraphSnapshotManager(FakeNeo4j(), base_dir=str(tmp_path))
        snapshot_id = await manager.create_snapshot(label="test")
        assert snapshot_id.startswith("test_")

        meta_path = os.path.join(tmp_path, snapshot_id, "meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["node_count"] == 3
        assert meta["edge_count"] == 1
        assert meta["label"] == "test"

        graph = await manager.load_snapshot(snapshot_id)
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 1
        assert graph.nodes["U1"]["node_type"] == "User"
        assert graph.edges["U1", "M1"]["edge_type"] == "TRANSACTION"

    @pytest.mark.asyncio
    async def test_load_missing_snapshot_raises(self, tmp_path):
        manager = GraphSnapshotManager(FakeNeo4j(), base_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            await manager.load_snapshot("nope_123")

    @pytest.mark.asyncio
    async def test_get_snapshot_at_time_and_list(self, tmp_path):
        manager = GraphSnapshotManager(FakeNeo4j(), base_dir=str(tmp_path))
        ts = datetime(2026, 1, 15, tzinfo=UTC)
        old_id = await manager.create_snapshot(timestamp=datetime(2026, 1, 1, tzinfo=UTC), label="old")
        await manager.create_snapshot(timestamp=datetime(2026, 2, 1, tzinfo=UTC), label="new")

        graph = await manager.get_snapshot_at_time(ts)
        assert graph.number_of_nodes() == 3
        with open(os.path.join(tmp_path, old_id, "meta.json")) as f:
            assert json.load(f)["label"] == "old"

        empty = await manager.get_snapshot_at_time(datetime(2020, 1, 1, tzinfo=UTC))
        assert empty.number_of_nodes() == 0

        listed = await manager.list_snapshots()
        assert [s["label"] for s in listed] == ["old", "new"]


class TestTransactionLog:
    @pytest.fixture(autouse=True)
    def _log(self, tmp_path):
        self.path = str(tmp_path / "txn_log.jsonl")
        self.log = TransactionLog(self.path)

    @pytest.mark.asyncio
    async def test_append_and_replay(self):
        await self.log.append("CREATE_NODE", "user", "U1", {"name": "a"})
        await self.log.append("CREATE_EDGE", "edge", "E1")
        entries = await self.log.replay()
        assert len(entries) == 2
        assert entries[0]["operation"] == "CREATE_NODE"
        assert entries[0]["entity_id"] == "U1"
        assert json.loads(entries[0]["properties_json"]) == {"name": "a"}
        assert entries[1]["properties_json"] == "{}"

    @pytest.mark.asyncio
    async def test_invalid_operation_raises(self):
        with pytest.raises(ValueError):
            await self.log.append("EXPLODE", "user", "U1")

    @pytest.mark.asyncio
    async def test_replay_missing_file_and_time_filters(self, tmp_path):
        other = TransactionLog(str(tmp_path / "nested" / "missing.jsonl"))
        assert await other.replay() == []
        await self.log.append("CREATE_NODE", "user", "U1")
        await self.log.append("CREATE_NODE", "user", "U2")
        entries = await self.log.replay(end_time=time_now() + 10)
        assert len(entries) == 2
        filtered = await self.log.get_mutations_since(time_now() + 1)
        assert filtered == []

    @pytest.mark.asyncio
    async def test_statistics(self):
        await self.log.append("CREATE_NODE", "user", "U1")
        await self.log.append("CREATE_NODE", "merchant", "M1")
        await self.log.append("CREATE_EDGE", "edge", "E1")
        stats = await self.log.get_statistics()
        assert stats["total_entries"] == 3
        assert stats["operations"]["CREATE_NODE"] == 2
        assert stats["entity_types"]["merchant"] == 1
        assert stats["time_range"]["start"] is not None


def time_now():
    import time

    return time.time()


class FakeNeo4jWriter:
    _driver = object()

    def __init__(self):
        self.calls = []

    async def create_transaction_node(self, *a):
        self.calls.append(("node", a))

    async def link_user_to_txn(self, *a):
        self.calls.append(("user", a))

    async def link_merchant_to_txn(self, *a):
        self.calls.append(("merchant", a))

    async def link_device_to_txn(self, *a):
        self.calls.append(("device", a))

    async def link_p2p_transfer(self, *a):
        self.calls.append(("p2p", a))


class FakeNxDB:
    def __init__(self):
        self.calls = []

    def create_transaction_node(self, *a):
        self.calls.append(("node", a))

    def link_user_to_txn(self, *a):
        self.calls.append(("user", a))

    def link_merchant_to_txn(self, *a):
        self.calls.append(("merchant", a))

    def link_device_to_txn(self, *a):
        self.calls.append(("device", a))

    def link_p2p_transfer(self, *a):
        self.calls.append(("p2p", a))


@pytest.mark.asyncio
class TestGraphDBWriter:
    async def test_backends_detection(self):
        writer = GraphDBWriter()
        assert writer.backends == []
        writer = GraphDBWriter(neo4j=FakeNeo4jWriter())
        assert writer.backends == ["neo4j"]
        writer = GraphDBWriter(networkx_db=FakeNxDB())
        assert writer.backends == ["networkx"]
        writer = GraphDBWriter(redis=object())
        assert writer.backends == ["redis_index"]

    async def test_write_transaction_all_backends(self):
        from tests.fake_redis import FakeRedis

        redis = FakeRedis()
        neo = FakeNeo4jWriter()
        nx_db = FakeNxDB()
        writer = GraphDBWriter(neo4j=neo, networkx_db=nx_db, redis=redis)
        result = await writer.write_transaction(
            {
                "txn_id": "T1",
                "user_id": "U1",
                "merchant_id": "M1",
                "device_fingerprint": "D1",
                "amount": 250.0,
                "txn_type": "P2M",
            }
        )
        assert result["backends"] == ["neo4j", "networkx", "redis_index"]
        assert ("node", ("T1", 250.0, None)) in neo.calls
        assert ("user", ("U1", "T1")) in neo.calls
        assert ("p2p",) not in [c[0] for c in neo.calls]

    async def test_p2p_writes_link(self):
        neo = FakeNeo4jWriter()
        writer = GraphDBWriter(neo4j=neo)
        await writer.write_transaction(
            {
                "txn_id": "T2",
                "user_id": "U1",
                "merchant_id": "M1",
                "counterparty_user_id": "U2",
                "txn_type": "P2P",
            }
        )
        assert ("p2p", ("U1", "U2", "T2")) in neo.calls

    async def test_failures_do_not_raise(self):
        from tests.fake_redis import FakeRedis

        class BrokenNx:
            def create_transaction_node(self, *a):
                raise RuntimeError("boom")

        redis = FakeRedis()
        writer = GraphDBWriter(networkx_db=BrokenNx(), redis=redis)
        result = await writer.write_transaction({"txn_id": "T3", "user_id": "U1"})
        assert result["backends"] == ["redis_index"]

    async def test_redis_index_key(self):
        from tests.fake_redis import FakeRedis

        redis = FakeRedis()
        writer = GraphDBWriter(redis=redis)
        await writer.write_transaction(
            {"txn_id": "T4", "user_id": "U1", "device_fingerprint": "D9"}
        )
        members = await redis.smembers(device_users_key("D9"))
        assert members == {"U1"}
