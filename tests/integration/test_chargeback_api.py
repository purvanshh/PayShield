"""Chargeback API integration tests (Phase 12).

Exercises the wired routes through the ASGI app with an in-memory Redis and
the tamper-evident audit chain used by the hot path.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from api.auth import auth_manager
from api.main import app
from store.audit_log import AuditLogWriter
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
DEV_KEY = "payshield-dev-key-2026"
ADMIN_KEY = "test-admin-key-track2"


@pytest.fixture
async def client():
    app.state.resources = {"redis": FakeRedis()}
    transport = ASGITransport(app=app)
    auth_manager.register_api_key(ADMIN_KEY, role="admin", name="track2-test")
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


def _seed_score_event(txn_id="TXN_CB001", amount=4500.0, rules=None):
    writer = AuditLogWriter("store/audit_logs")
    writer.append(
        "SCORE_DECISION",
        "U000001",
        "ALLOW",
        {
            "txn_id": txn_id,
            "merchant_id": "M00001",
            "amount": amount,
            "device_fingerprint": "DEV-88412",
            "fraud_probability": 0.12,
            "triggered_rules": rules or [],
        },
    )


class TestChargebackAuth:
    async def test_respond_requires_auth(self, client):
        resp = await client.post("/v1/chargeback/respond", json={})
        assert resp.status_code == 403

    async def test_get_requires_auth(self, client):
        resp = await client.get("/v1/chargeback/disp_x")
        assert resp.status_code == 403


class TestChargebackRespond:
    async def test_respond_builds_and_caches_rebuttal(self, client):
        _seed_score_event("TXN_CB001")
        body = {
            "dispute_id": "disp_cb001",
            "payment_id": "pay_cb001",
            "transaction_id": "TXN_CB001",
            "network": "VISA",
            "reason_code": "10.4",
            "reason_description": "Cardholder fraud probe",
        }
        resp = await client.post("/v1/chargeback/respond", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        payload = data["data"]
        assert payload["dispute_id"] == "disp_cb001"
        assert payload["response_type"] == "REJECT"
        assert 0 <= payload["confidence_score"] <= 1
        assert payload["evidence_completeness"] > 0
        assert "contest" in payload["razorpay_payload"]
        assert any(e["action"] == "REBUTTAL_ASSEMBLED" for e in payload["audit_trail"])
        assert data["latency_ms"] > 0

        # cached rebuttal retrievable by dispute id
        resp2 = await client.get("/v1/chargeback/disp_cb001", headers={"X-API-Key": DEV_KEY})
        assert resp2.status_code == 200
        assert resp2.json()["data"]["dispute_id"] == "disp_cb001"

    async def test_respond_unknown_txn_404(self, client):
        body = {
            "dispute_id": "disp_missing",
            "payment_id": "pay_missing",
            "transaction_id": "TXN_NOPE",
            "reason_code": "10.4",
        }
        resp = await client.post("/v1/chargeback/respond", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 404

    async def test_auto_submit_requires_admin(self, client):
        _seed_score_event("TXN_CB002")
        body = {
            "dispute_id": "disp_cb002",
            "payment_id": "pay_cb002",
            "transaction_id": "TXN_CB002",
            "auto_submit": True,
            "reason_code": "10.4",
        }
        resp = await client.post("/v1/chargeback/respond", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 403

    async def test_auto_submit_with_admin_accepts(self, client):
        _seed_score_event("TXN_CB003")
        body = {
            "dispute_id": "disp_cb003",
            "payment_id": "pay_cb003",
            "transaction_id": "TXN_CB003",
            "auto_submit": True,
            "reason_code": "10.4",
        }
        resp = await client.post("/v1/chargeback/respond", json=body, headers={"X-API-Key": ADMIN_KEY})
        assert resp.status_code == 200


class TestChargebackSubmit:
    async def test_submit_without_draft_404(self, client):
        resp = await client.post(
            "/v1/chargeback/disp_unknown/submit",
            json={"strike": "contest"},
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 404

    async def test_submit_requires_admin(self, client):
        _seed_score_event("TXN_CB004")
        await client.post(
            "/v1/chargeback/respond",
            json={
                "dispute_id": "disp_cb004",
                "payment_id": "pay_cb004",
                "transaction_id": "TXN_CB004",
                "reason_code": "10.4",
            },
            headers={"X-API-Key": DEV_KEY},
        )
        resp = await client.post(
            "/v1/chargeback/disp_cb004/submit",
            json={"strike": "contest"},
            headers={"X-API-Key": DEV_KEY},
        )
        assert resp.status_code == 403

    async def test_submit_drafted_rebuttal(self, client):
        _seed_score_event("TXN_CB005")
        await client.post(
            "/v1/chargeback/respond",
            json={
                "dispute_id": "disp_cb005",
                "payment_id": "pay_cb005",
                "transaction_id": "TXN_CB005",
                "reason_code": "10.4",
            },
            headers={"X-API-Key": DEV_KEY},
        )
        resp = await client.post(
            "/v1/chargeback/disp_cb005/submit",
            json={"strike": "contest"},
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUBMITTED"
        assert data["data"]["razorpay_status"] == "under_review"
