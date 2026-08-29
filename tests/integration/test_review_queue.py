"""Human-review queue meta-endpoint tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from store.audit_log import AuditLogWriter
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
DEV_KEY = "payshield-dev-key-2026"


@pytest.fixture
async def client(tmp_path):
    from store.audit_log import AuditLogReader

    writer = AuditLogWriter(str(tmp_path))
    for payload, decision in [
        ({"order_id": "ORD_LOW", "merchant_id": "M1", "score": 0.1, "tier": "LOW"}, "LOW"),
        ({"order_id": "ORD_MED_1", "merchant_id": "M1", "score": 0.45, "tier": "MEDIUM"}, "MEDIUM"),
        ({"order_id": "ORD_HIGH", "merchant_id": "M2", "score": 0.9, "tier": "HIGH"}, "HIGH"),
        ({"order_id": "ORD_MED_2", "merchant_id": "M2", "score": 0.55, "tier": "MEDIUM"}, "MEDIUM"),
        ({"order_id": "ORD_MED_1", "merchant_id": "M1", "score": 0.6, "tier": "MEDIUM"}, "MEDIUM"),
    ]:
        writer.append("RETURN_RISK_SCORED", "U_USER", decision, payload)

    app.state.resources = {
        "redis": FakeRedis(),
        "audit_reader": AuditLogReader(str(tmp_path)),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


class TestReviewQueue:
    async def test_requires_auth(self, client):
        resp = await client.get("/v1/meta/review-queue")
        assert resp.status_code == 403

    async def test_lists_latest_medium_decisions_deduped(self, client):
        resp = await client.get("/v1/meta/review-queue", headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2  # ORD_MED_1 (latest) and ORD_MED_2
        order_ids = [i["order_id"] for i in data["items"]]
        assert order_ids[0] == "ORD_MED_1"  # newest first (re-scored latest)
        assert "ORD_MED_2" in order_ids
        assert "ORD_LOW" not in order_ids and "ORD_HIGH" not in order_ids
        assert all(i["tier"] == "MEDIUM" for i in data["items"])
        assert all(i["reviewed"] is False for i in data["items"])

    async def test_mark_reviewed_then_reflects_in_queue(self, client):
        resp = await client.post(
            "/v1/meta/review-queue/ORD_MED_1/mark", headers={"X-API-Key": DEV_KEY}
        )
        assert resp.status_code == 200
        assert resp.json()["reviewed"] is True
        data = await client.get(
            "/v1/meta/review-queue", headers={"X-API-Key": DEV_KEY}
        )
        items = {i["order_id"]: i for i in data.json()["items"]}
        assert items["ORD_MED_1"]["reviewed"] is True
        assert items["ORD_MED_2"]["reviewed"] is False
