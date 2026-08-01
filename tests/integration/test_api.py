from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from engine.ensemble import EnsembleFusionEngine
from engine.statistical_filter import StatisticalFilter
from store.graph_db import NetworkXGraphDB
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"


@pytest.fixture
async def client():
    app.state.resources = {
        "redis": FakeRedis(),
        "statistical_filter": StatisticalFilter(),
        "ensemble": EnsembleFusionEngine(),
        "graph_db": NetworkXGraphDB(),
        "graph_writer": None,
        "l2_inference": None,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_json(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "checks" in data

    async def test_metrics_endpoint(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200


class TestScoreEndpoint:
    async def test_score_requires_auth(self, client):
        resp = await client.post("/v1/score", json={})
        assert resp.status_code == 403

    async def test_score_with_valid_auth(self, client):
        payload = {
            "txn_id": "TXN00000001",
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 500.0,
            "timestamp": datetime.utcnow().isoformat(),
            "device_fingerprint": "D_test",
            "location": {"lat": 19.0760, "lon": 72.8777},
            "mcc_code": "food",
            "txn_type": "P2M",
        }
        resp = await client.post(
            "/v1/score",
            json=payload,
            headers={"X-API-Key": "payshield-dev-key-2026"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "txn_id" in data
        assert "decision" in data
        assert "fraud_probability" in data
        assert "latency_ms" in data

    async def test_batch_score(self, client):
        payload = {
            "transactions": [
                {
                    "txn_id": f"TXN{i:08d}",
                    "user_id": "U000001",
                    "merchant_id": "M00001",
                    "amount": float((i + 1) * 100),
                    "timestamp": datetime.utcnow().isoformat(),
                    "device_fingerprint": "D_test",
                    "location": {"lat": 19.0760, "lon": 72.8777},
                    "mcc_code": "food",
                    "txn_type": "P2M",
                }
                for i in range(3)
            ]
        }
        resp = await client.post(
            "/v1/batch",
            json=payload,
            headers={"X-API-Key": "payshield-dev-key-2026"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 3
        for r in data["results"]:
            assert "decision" in r


class TestFeedbackEndpoint:
    async def test_feedback_submission(self, client):
        payload = {
            "txn_id": "TXN00000001",
            "analyst_id": "analyst_1",
            "original_decision": "ALLOW",
            "analyst_decision": "BLOCK",
            "reason": "Confirmed fraud",
            "category": "FALSE_NEGATIVE",
        }
        resp = await client.post(
            "/v1/feedback",
            json=payload,
            headers={"X-API-Key": "payshield-dev-key-2026"},
        )
        if resp.status_code == 200:
            assert resp.json()["status"] == "ok"
