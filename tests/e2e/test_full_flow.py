# ruff: noqa: ARG002 -- test doubles mirror the client interface

"""End-to-end tests for the complete PayShield fraud detection pipeline.

Runs the full app in-process via ASGITransport with an in-memory Redis fake
and a fake L2 service, so the suite needs no external services. The same
flow previously required a live ``localhost:8000`` stack.
"""

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

import api.routes.score as score_module
from api.main import app
from engine.ensemble import EnsembleFusionEngine
from engine.statistical_filter import StatisticalFilter
from store.graph_db import NetworkXGraphDB
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
HEADERS = {"X-API-Key": "payshield-dev-key-2026", "Content-Type": "application/json"}


class StubL2Service:
    async def predict(self, graph, **kwargs):
        return {
            "status": "SUCCESS" if graph.number_of_nodes() >= 2 else "SKIPPED_NO_GRAPH",
            "fraud_probability": 0.05 if graph.number_of_nodes() >= 2 else None,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "latency_ms": 8.0,
        }


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(score_module, "_celery_available", False)
    resources = {
        "redis": FakeRedis(),
        "statistical_filter": StatisticalFilter(),
        "ensemble": EnsembleFusionEngine(),
        "graph_db": NetworkXGraphDB(),
        "graph_writer": None,
        "l2_inference": StubL2Service(),
    }
    app.state.resources = resources
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


def _txn(txn_id: str, user_id: str = "U_E2E_001", amount: float = 4990.0,
         merchant_id: str = "M5502", device: str = "DEV_E2E_001") -> dict:
    return {
        "txn_id": txn_id,
        "user_id": user_id,
        "merchant_id": merchant_id,
        "amount": amount,
        "timestamp": datetime.utcnow().isoformat(),
        "device_fingerprint": device,
        "location": {"lat": 19.076, "lon": 72.8777},
        "mcc_code": "6012",
        "txn_type": "P2M",
    }


class TestFullFlow:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "checks" in data

    async def test_complete_fraud_pipeline(self, client):
        resp = await client.post("/v1/score", json=_txn("e2e_txn_001"), headers=HEADERS)
        assert resp.status_code == 200
        result = resp.json()
        assert result["txn_id"] == "e2e_txn_001"
        assert result["decision"] in ("ALLOW", "BLOCK", "REVIEW")
        assert 0.0 <= result["fraud_probability"] <= 1.0
        assert result["latency_ms"] > 0.0

        inv_resp = await client.get(
            "/v1/investigation/e2e_txn_001", headers=HEADERS,
        )
        assert inv_resp.status_code in (200, 404)

    async def test_legitimate_transaction_allowed(self, client):
        resp = await client.post(
            "/v1/score", json=_txn("e2e_legit_001", amount=250.0), headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] in ("ALLOW", "REVIEW")

    async def test_batch_scoring_100(self, client):
        transactions = [
            _txn(f"e2e_batch_{i:03d}", user_id=f"U_BATCH_{i % 10}", amount=float(100 + i))
            for i in range(100)
        ]
        resp = await client.post("/v1/batch", json={"transactions": transactions}, headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 100
        for r in data["results"]:
            assert "decision" in r
            assert 0.0 <= r["fraud_probability"] <= 1.0

    async def test_batch_over_limit_rejected(self, client):
        transactions = [_txn(f"e2e_big_{i:03d}") for i in range(150)]
        resp = await client.post("/v1/batch", json={"transactions": transactions}, headers=HEADERS)
        assert resp.status_code == 400

    async def test_score_requires_auth(self, client):
        resp = await client.post("/v1/score", json=_txn("e2e_noauth_001"))
        assert resp.status_code == 403
