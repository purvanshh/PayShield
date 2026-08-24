"""Razorpay webhook handler integration tests.

Exercises the signed endpoints through the ASGI app with an in-memory
Redis: signature verification, feature mapping, scoring envelope shape and
label persistence.
"""

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
SECRET = "payshield-webhook-dev-secret"
FIXTURES = Path(__file__).resolve().parents[2] / "integrations" / "fixtures"


@pytest.fixture
async def client():
    app.state.resources = {"redis": FakeRedis()}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


def _sign(payload: bytes) -> str:
    return hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestSignatureVerification:
    async def test_bad_signature_rejected(self, client):
        resp = await client.post(
            "/webhooks/razorpay/return-risk",
            content=_load("razorpay_order.json"),
            headers={"X-Razorpay-Signature": "deadbeef"},
        )
        assert resp.status_code == 400

    async def test_missing_signature_rejected(self, client):
        resp = await client.post("/webhooks/razorpay/refund", content=_load("razorpay_refund.json"))
        assert resp.status_code == 400


class TestReturnRiskWebhook:
    async def test_order_paid_is_scored(self, client):
        body = _load("razorpay_order.json")
        resp = await client.post(
            "/webhooks/razorpay/return-risk",
            content=body,
            headers={"X-Razorpay-Signature": _sign(body)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scored"
        assert data["order_id"] == "order_MYNT2026_001"
        assert data["data"]["risk_tier"] in ("LOW", "MEDIUM", "HIGH")
        assert data["features"]["amount"] == "5500"

    async def test_non_order_paid_event_ignored(self, client):
        body = json.dumps({"event": "payment.failed", "payload": {}}).encode()
        resp = await client.post(
            "/webhooks/razorpay/return-risk",
            content=body,
            headers={"X-Razorpay-Signature": _sign(body)},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


class TestRefundWebhook:
    async def test_refund_processed_records_label(self, client):
        body = _load("razorpay_refund.json")
        resp = await client.post(
            "/webhooks/razorpay/refund",
            content=body,
            headers={"X-Razorpay-Signature": _sign(body)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "label_recorded"
        assert data["label"]["user_id"] == "cust_returnsal"
        assert data["label"]["return_reason"] == "CHANGED_MIND"

        redis: FakeRedis = app.state.resources["redis"]
        labels = await redis.lrange("return_risk:labels", 0, -1)
        assert len(labels) == 1
        stored = json.loads(labels[0])
        assert stored["order_id"] == "order_MYNT2026_002"
        assert stored["returned"] is True
