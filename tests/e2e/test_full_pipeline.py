# ruff: noqa: ARG002 -- stub mirrors the L2 service interface

"""Grand integration test: transaction -> return risk -> chargeback (Phase 46).

Runs all three systems in sequence against the in-process ASGI app with an
in-memory Redis (no services), proving the coherent story the demo tells:

1. /v1/score        - a live transaction (L1/L2/L3 path with stub L2)
2. /v1/return/score - order risk before dispatch (seeded profile)
3. /v1/return/update - the return event feeds back into the profile
4. /v1/chargeback/respond - dispute against the first transaction
5. verification: the rebuttal is cached + the profile reflects the update
"""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

import api.routes.score as score_module
from api.main import app
from engine.ensemble import EnsembleFusionEngine
from engine.statistical_filter import StatisticalFilter
from store.audit_log import AuditLogWriter
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
    redis = FakeRedis()
    # curated profile: serial returner so the return-risk scene is decisive
    await redis.hmset(
        "return_risk:user:U_E2E_001",
        {"total_orders": "15", "total_returns": "10", "return_rate_30d": "0.66",
         "cod_refusals": "3", "cod_orders": "8", "serial_returner": "true"},
    )
    await redis.hmset("return_risk:merchant:M_E2E_001", {"return_rate_30d": "0.30"})
    await redis.zadd("return_risk:merchant:M_E2E_001:category", {"fashion": 0.30})
    await redis.zadd("return_risk:user:U_E2E_001:returns",
                     {"ORD_E2E_0": datetime.utcnow().timestamp() - 86400})
    app.state.resources = {
        "redis": redis,
        "statistical_filter": StatisticalFilter(),
        "ensemble": EnsembleFusionEngine(),
        "graph_db": NetworkXGraphDB(),
        "graph_writer": None,
        "l2_inference": StubL2Service(),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


class TestGrandPipeline:
    async def test_transaction_to_chargeback_story(self, client):
        # 1. transaction scoring
        txn = await client.post(
            "/v1/score",
            json={
                "txn_id": "TXN_E2E_001",
                "user_id": "U_E2E_001",
                "merchant_id": "M_E2E_001",
                "amount": 5000.00,
                "timestamp": datetime.utcnow().isoformat(),
                "device_fingerprint": "DEV_E2E_001",
                "location": {"lat": 19.0760, "lon": 72.8777},
                "mcc_code": "fashion",
                "txn_type": "P2M",
            },
            headers=HEADERS,
        )
        assert txn.status_code == 200
        txn_data = txn.json()
        assert txn_data["decision"] in ("ALLOW", "REVIEW", "BLOCK")
        txn_id = txn_data["txn_id"]

        # 2. return-risk scoring before (any) dispatch
        scored = await client.post(
            "/v1/return/score",
            json={
                "order_id": "ORD_E2E_001",
                "user_id": "U_E2E_001",
                "merchant_id": "M_E2E_001",
                "amount": 5000.00,
                "currency": "INR",
                "category": "fashion",
                "payment_method": "UPI",
                "cod_flag": True,
            },
            headers=HEADERS,
        )
        assert scored.status_code == 200
        rr = scored.json()["data"]
        assert rr["risk_tier"] == "HIGH"
        assert any(r["rule_id"] == "R-RULE-01" and r["triggered"] for r in rr["rules_triggered"])

        # 3. return event feeds back into the profile
        updated = await client.post(
            "/v1/return/update",
            json={
                "user_id": "U_E2E_001",
                "order_id": "ORD_E2E_001",
                "amount": 5000.00,
                "category": "fashion",
                "cod_flag": True,
                "returned": True,
                "return_reason": "SIZE_ISSUE",
            },
            headers=HEADERS,
        )
        assert updated.status_code == 200
        profile = await app.state.resources["redis"].hgetall("return_risk:user:U_E2E_001")
        assert int(profile["total_returns"]) == 11

        # 4. chargeback response against the scored transaction
        writer = AuditLogWriter("store/audit_logs")
        writer.append(
            "SCORE_DECISION",
            "U_E2E_001",
            txn_data["decision"],
            {
                "txn_id": txn_id,
                "merchant_id": "M_E2E_001",
                "amount": 5000.00,
                "device_fingerprint": "DEV_E2E_001",
                "fraud_probability": txn_data["fraud_probability"],
                "triggered_rules": txn_data["evidence"].get("triggered_rules", []),
            },
        )
        cb = await client.post(
            "/v1/chargeback/respond",
            json={
                "dispute_id": "CB_E2E_001",
                "payment_id": "pay_E2E_001",
                "transaction_id": txn_id,
                "network": "VISA",
                "reason_code": "10.4",
                "reason_description": "Fraud - Card Not Present",
                "response_deadline": (datetime.utcnow() + timedelta(days=25)).isoformat(),
            },
            headers=HEADERS,
        )
        assert cb.status_code == 200
        cb_data = cb.json()["data"]
        assert cb_data["response_type"] in ("ACCEPT", "REJECT", "PARTIAL")
        assert cb_data["confidence_score"] > 0
        assert any(e["action"] == "REBUTTAL_ASSEMBLED" for e in cb_data["audit_trail"])
        assert cb_data["razorpay_payload"]["contest"] is not None

        # 5. rebuttal cached; profile reflects score-time refresh + the return event
        cached = await client.get("/v1/chargeback/CB_E2E_001", headers=HEADERS)
        assert cached.status_code == 200
        assert cached.json()["data"]["dispute_id"] == "CB_E2E_001"
        # 15 seeded + 1 background refresh at score time + 1 update call
        assert profile_value(await app.state.resources["redis"].hgetall("return_risk:user:U_E2E_001"), "total_orders") == 17


def profile_value(profile: dict, key: str) -> int:
    return int(profile.get(key, 0))
