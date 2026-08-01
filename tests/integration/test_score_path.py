"""Integration tests for the full scoring hot path (statistical -> ensemble -> L2).

Five named scenarios covering the gating ladder:

1. Normal transaction -> ALLOW (L1 clean, L2 unavailable).
2. Velocity burst -> BLOCK at L1 (no L2 needed).
3. Empty graph -> L2 SKIPPED_NO_GRAPH, ALLOW from L1-only fusion.
4. Graph history present -> L2 SUCCESS, calibrated score BLOCKs via L2_GNN.
5. Calibrated probabilities stay in [0,1] and respect the REVIEW/BLOCK gates.

All external services (Redis, Neo4j, Ollama, Celery, model server) are fakes
or disabled — the suite runs offline.
"""
# ruff: noqa: ARG001, ARG002 -- test doubles mirror the client interface

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

import api.routes.score as score_module
from api.main import app
from engine.ensemble import EnsembleFusionEngine
from engine.statistical_filter import StatisticalFilter
from store.graph_db import NetworkXGraphDB
from tests.fake_redis import FakeRedis

API_KEY = "payshield-dev-key-2026"
BASE_URL = "http://test"
HEADERS = {"X-API-Key": API_KEY}


class FakeL2Service:
    """Deterministic stand-in for L2InferenceService.

    Mirrors the real contract: ``predict(ego_graph, ...)`` returns a dict with
    status/fraud_probability/nodes/edges/latency_ms, and returns
    SKIPPED_NO_GRAPH for ego graphs with fewer than 2 nodes.
    """

    def __init__(self, prob=None):
        self.prob = prob
        self.calls = []

    async def predict(self, graph, **kwargs):
        self.calls.append(kwargs)
        if graph.number_of_nodes() < 2:
            return {
                "status": "SKIPPED_NO_GRAPH",
                "fraud_probability": None,
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "latency_ms": 0.0,
            }
        return {
            "status": "SUCCESS",
            "fraud_probability": self.prob,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "latency_ms": 8.5,
        }


def _txn_payload(txn_id: str, user_id: str = "U_TEST_001", merchant_id: str = "M5502",
                 amount: float = 500.0, device: str = "DEV_TEST_001",
                 ts: datetime | None = None) -> dict:
    return {
        "txn_id": txn_id,
        "user_id": user_id,
        "merchant_id": merchant_id,
        "amount": amount,
        "timestamp": (ts or datetime.utcnow()).isoformat(),
        "device_fingerprint": device,
        "location": {"lat": 19.076, "lon": 72.8777},
        "mcc_code": "food",
        "txn_type": "P2M",
    }


def _seed_graph_history(db: NetworkXGraphDB, user_id: str, merchant_id: str,
                        device: str, n: int = 6, base_ts: float | None = None):
    base = base_ts if base_ts is not None else datetime.utcnow().timestamp()
    for i in range(n):
        txn_id = f"TXN_HIST_{user_id}_{i}"
        db.create_transaction_node(txn_id, amount=250.0 + i, timestamp=base - (i + 1) * 300)
        db.link_user_to_txn(user_id, txn_id)
        db.link_merchant_to_txn(merchant_id, txn_id)
        db.link_device_to_txn(device, txn_id)


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(score_module, "_celery_available", False)
    resources = {
        "redis": FakeRedis(),
        "statistical_filter": StatisticalFilter(),
        "ensemble": EnsembleFusionEngine(),
        "graph_db": NetworkXGraphDB(),
        "graph_writer": None,
        "l2_inference": FakeL2Service(),
    }
    app.state.resources = resources
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac, resources


class TestScorePath:
    async def test_allow_normal_transaction(self, client):
        ac, resources = client
        resp = await ac.post("/v1/score", json=_txn_payload("TXN_ALLOW_01"), headers=HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["txn_id"] == "TXN_ALLOW_01"
        assert result["decision"] == "ALLOW"
        assert result["layer_triggered"] == "ENSEMBLE"
        assert result["evidence"]["l2_status"] == "SKIPPED_NO_GRAPH"
        assert 0.0 <= result["fraud_probability"] <= 1.0
        assert result["latency_ms"] > 0.0

    async def test_block_velocity_burst(self, client):
        ac, resources = client
        redis = resources["redis"]
        now = datetime.utcnow().timestamp()
        bursts = [now - 60 + i * 2 for i in range(25)]
        # Same device used by multiple users -> device flood (V-RULE-04 BLOCK).
        redis.seed_velocity(
            "U_BURST_001", "DEV_BURST_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        redis.seed_velocity(
            "U_BURST_002", "DEV_BURST_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_BURST_01", user_id="U_BURST_001", device="DEV_BURST_001",
                              amount=15000.0),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["decision"] == "BLOCK"
        assert result["layer_triggered"] == "L1_STATISTICAL"
        assert "V-RULE-04" in result["evidence"]["triggered_rules"]
        assert result["fraud_probability"] == 1.0

    async def test_l2_skips_empty_graph(self, client):
        ac, resources = client
        l2 = resources["l2_inference"]
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_SKIP_01", user_id="U_GHOST_001", device="DEV_GHOST_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["evidence"]["l2_status"] == "SKIPPED_NO_GRAPH"
        assert result["decision"] == "ALLOW"
        assert result["evidence"]["l2_probability"] is None
        assert l2.calls and l2.calls[-1]["user_id"] == "U_GHOST_001"

    async def test_l2_runs_with_history(self, client):
        ac, resources = client
        db = resources["graph_db"]
        _seed_graph_history(db, "U_HIST_001", "M5502", "DEV_HIST_001")
        l2 = resources["l2_inference"]
        l2.prob = 0.85
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_HIST_01", user_id="U_HIST_001", device="DEV_HIST_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["evidence"]["l2_status"] == "SUCCESS"
        assert result["layer_triggered"] == "L2_GNN"
        assert result["decision"] == "BLOCK"
        assert result["evidence"]["l2_latency_ms"] > 0.0
        assert result["evidence"]["l2_probability"] == 0.85

    async def test_calibrated_probability_range_and_gates(self, client):
        ac, resources = client
        l2 = resources["l2_inference"]
        scenarios = [
            (0.2, "ALLOW"),
            (0.5, "ALLOW"),
            (0.65, "REVIEW"),
            (0.9, "BLOCK"),
        ]
        for i, (prob, expected) in enumerate(scenarios):
            l2.prob = prob
            db = resources["graph_db"]
            user = f"U_RANGE_{i}"
            _seed_graph_history(db, user, "M5502", f"DEV_RANGE_{i}")
            resp = await ac.post(
                "/v1/score",
                json=_txn_payload(f"TXN_RANGE_{i}", user_id=user, device=f"DEV_RANGE_{i}"),
                headers=HEADERS,
            )
            assert resp.status_code == 200
            result = resp.json()
            assert 0.0 <= result["fraud_probability"] <= 1.0, f"prob out of range for {prob}"
            assert result["decision"] == expected, f"expected {expected} got {result['decision']}"
            if expected == "REVIEW":
                assert result["layer_triggered"] == "ENSEMBLE"
            if expected == "BLOCK":
                assert result["layer_triggered"] == "L2_GNN"


class FailingWriter:
    def __init__(self):
        self.calls = []

    async def write_transaction(self, txn_dict, velocity_features):
        self.calls.append(txn_dict)
        raise RuntimeError("neo4j down")


class RecordingWriter(FailingWriter):
    async def write_transaction(self, txn_dict, velocity_features):
        self.calls.append(txn_dict)


class FailingL2Service:
    async def predict(self, graph, **kwargs):
        raise RuntimeError("model server down")


class _BroadcastStub:
    def __init__(self, raise_error=False):
        self.messages = []
        self.raise_error = raise_error

    async def broadcast(self, message, filter_fn=None):
        if self.raise_error:
            raise RuntimeError("ws down")
        self.messages.append(message)


class TestScorePathRobustness:
    async def test_malformed_velocity_entries_skipped(self, client):
        ac, resources = client
        redis = resources["redis"]
        await redis.lpush("velocity:user:U_MALFORMED_01", "not-json")
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_MALFORMED_01", user_id="U_MALFORMED_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_redis_read_failures_tolerated(self, client, monkeypatch):
        ac, resources = client
        redis = resources["redis"]
        async def boom(*_a, **_k):
            raise RuntimeError("redis down")
        monkeypatch.setattr(redis, "get", boom)
        monkeypatch.setattr(redis, "set", boom)
        monkeypatch.setattr(redis, "lrange", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_REDIS_FAIL_01", user_id="U_REDIS_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_idempotent_replay_returns_cached(self, client):
        ac, resources = client
        redis = resources["redis"]
        payload = _txn_payload("TXN_REPLAY_01", user_id="U_REPLAY_01")
        first = (await ac.post("/v1/score", json=payload, headers=HEADERS)).json()
        second = (await ac.post("/v1/score", json=payload, headers=HEADERS)).json()
        assert first == second
        assert second["txn_id"] == "TXN_REPLAY_01"
        import hashlib
        cached = await redis.get(f"idempotent:{hashlib.sha256(b'TXN_REPLAY_01').hexdigest()}")
        assert cached is not None

    async def test_feature_build_failure_falls_back(self, client, monkeypatch):
        ac, resources = client
        async def boom(*_a, **_k):
            raise RuntimeError("velocity down")
        monkeypatch.setattr(score_module, "_record_and_build_features", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_FEATURE_FAIL_01", user_id="U_FEATURE_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_layer1_eval_failure_falls_back(self, client, monkeypatch):
        ac, resources = client
        async def boom(_self, *_a, **_k):
            raise RuntimeError("rules down")
        monkeypatch.setattr(StatisticalFilter, "evaluate", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_L1_FAIL_01", user_id="U_L1_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_ensemble_fusion_failure_falls_back(self, client, monkeypatch):
        ac, resources = client
        def boom(_self, *_a, **_k):
            raise RuntimeError("fusion down")
        monkeypatch.setattr(EnsembleFusionEngine, "fuse", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_FUSE_FAIL_01", user_id="U_FUSE_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_l2_inference_error_falls_back(self, client):
        ac, resources = client
        resources["l2_inference"] = FailingL2Service()
        db = resources["graph_db"]
        _seed_graph_history(db, "U_L2_FAIL_01", "M5502", "DEV_L2_FAIL_01")
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_L2_FAIL_01", user_id="U_L2_FAIL_01", device="DEV_L2_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["decision"] == "ALLOW"
        assert result["evidence"]["l2_status"] == "ERROR"

    async def test_block_broadcasts_fraud_alert(self, client, monkeypatch):
        import api.websocket as ws_module
        ac, resources = client
        stub = _BroadcastStub()
        monkeypatch.setattr(ws_module, "manager", stub)
        db = resources["graph_db"]
        _seed_graph_history(db, "U_ALERT_001", "M5502", "DEV_ALERT_001")
        resources["l2_inference"].prob = 0.9
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_ALERT_01", user_id="U_ALERT_001", device="DEV_ALERT_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "BLOCK"
        assert stub.messages and stub.messages[0]["type"] == "fraud_alert"
        assert stub.messages[0]["txn_id"] == "TXN_ALERT_01"

    async def test_broadcast_failure_ignored(self, client, monkeypatch):
        import api.websocket as ws_module
        ac, resources = client
        monkeypatch.setattr(ws_module, "manager", _BroadcastStub(raise_error=True))
        db = resources["graph_db"]
        _seed_graph_history(db, "U_ALERT2_001", "M5502", "DEV_ALERT2_001")
        resources["l2_inference"].prob = 0.9
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_ALERT2_01", user_id="U_ALERT2_001", device="DEV_ALERT2_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "BLOCK"

    async def test_investigation_enqueue_failure_ignored(self, client, monkeypatch):
        ac, resources = client
        monkeypatch.setattr(score_module, "_celery_available", True)
        monkeypatch.setattr(score_module, "generate_investigation", _FakeCeleryTask())
        now = datetime.utcnow().timestamp()
        bursts = [now - 60 + i * 2 for i in range(25)]
        redis = resources["redis"]
        redis.seed_velocity(
            "U_ENQ_001", "DEV_ENQ_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        redis.seed_velocity(
            "U_ENQ_002", "DEV_ENQ_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_ENQ_01", user_id="U_ENQ_001", device="DEV_ENQ_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "BLOCK"

    async def test_cache_write_failure_ignored(self, client, monkeypatch):
        ac, resources = client
        redis = resources["redis"]
        async def boom(*_a, **_k):
            raise RuntimeError("cache down")
        monkeypatch.setattr(redis, "set", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_CACHE_FAIL_01", user_id="U_CACHE_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_drift_sample_failure_ignored(self, client, monkeypatch):
        ac, resources = client
        redis = resources["redis"]
        async def boom(*_a, **_k):
            raise RuntimeError("drift down")
        monkeypatch.setattr(redis, "pipeline", boom)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_DRIFT_FAIL_01", user_id="U_DRIFT_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_explanation_persist_failure_ignored(self, client, monkeypatch):
        ac, resources = client
        def boom(*_a, **_k):
            raise OSError("disk full")
        monkeypatch.setattr(score_module.os, "makedirs", boom)
        now = datetime.utcnow().timestamp()
        bursts = [now - 60 + i * 2 for i in range(25)]
        redis = resources["redis"]
        redis.seed_velocity(
            "U_PERSIST_001", "DEV_PERSIST_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        redis.seed_velocity(
            "U_PERSIST_002", "DEV_PERSIST_001", bursts,
            amounts=[10000.0] * 25, merchants=["M5502"] * 25,
        )
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_PERSIST_01", user_id="U_PERSIST_001", device="DEV_PERSIST_001"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "BLOCK"

    async def test_audit_append_failure_ignored(self, client, monkeypatch):
        import store.audit_log as audit_module
        ac, resources = client
        class _BrokenWriter:
            def append(self, **kwargs):
                raise RuntimeError("audit down")
        monkeypatch.setattr(audit_module, "AuditLogWriter", _BrokenWriter)
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_AUDIT_FAIL_01", user_id="U_AUDIT_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_graph_writer_mirrors_txn(self, client):
        ac, resources = client
        writer = RecordingWriter()
        resources["graph_writer"] = writer
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_WRITER_01", user_id="U_WRITER_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert len(writer.calls) == 1
        assert writer.calls[0]["txn_id"] == "TXN_WRITER_01"

    async def test_graph_writer_failure_ignored(self, client):
        ac, resources = client
        resources["graph_writer"] = FailingWriter()
        resp = await ac.post(
            "/v1/score",
            json=_txn_payload("TXN_WRITER_FAIL_01", user_id="U_WRITER_FAIL_01"),
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"


class _FakeCeleryTask:
    def delay(self, *a, **k):
        raise RuntimeError("broker down")


class TestBatchScoring:
    def _batch_payload(self, n, prefix="TXN_B"):
        return {
            "transactions": [
                _txn_payload(f"{prefix}_{i}", user_id=f"U_BATCH_{i}", device=f"DEV_BATCH_{i}")
                for i in range(n)
            ]
        }

    async def test_batch_exceeds_limit_rejected(self, client):
        ac, resources = client
        resp = await ac.post("/v1/batch", json=self._batch_payload(101), headers=HEADERS)
        assert resp.status_code == 400

    async def test_batch_scores_all_transactions(self, client):
        ac, resources = client
        resp = await ac.post("/v1/batch", json=self._batch_payload(3), headers=HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert len(result["results"]) == 3
        assert all(r["decision"] == "ALLOW" for r in result["results"])
        assert result["batch_latency_ms"] >= 0.0

    async def test_batch_without_stat_filter(self, client):
        ac, resources = client
        resources["statistical_filter"] = None
        resp = await ac.post("/v1/batch", json=self._batch_payload(2), headers=HEADERS)
        assert resp.status_code == 200
        assert all(r["decision"] == "ALLOW" for r in resp.json()["results"])

    async def test_batch_survives_txn_error(self, client, monkeypatch):
        ac, resources = client
        async def boom(_self, *_a, **_k):
            raise RuntimeError("rules down")
        monkeypatch.setattr(StatisticalFilter, "evaluate", boom)
        resp = await ac.post("/v1/batch", json=self._batch_payload(2), headers=HEADERS)
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert all(r["decision"] == "ALLOW" for r in results)
        assert all("error" in r["evidence"] for r in results)
