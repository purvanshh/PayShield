"""Chargeback webhook event processing tests (Phase 11).

Exercises process_chargeback_event directly (no HTTP stack) against the
FakeRedis store with a directory-local audit writer, plus the HTTP route
with signature verification via an in-process AsyncClient.
"""

import json
import os

from chargeback.signatures import compute_signature
from store.audit_log import AuditLogReader, AuditLogWriter
from tests.fake_redis import FakeRedis


def _audit(tmp_path) -> AuditLogWriter:
    return AuditLogWriter(str(tmp_path))


class TestWebhookEventProcessing:
    async def test_created_sets_dispute_marker_and_audits(self, tmp_path):
        redis = FakeRedis()
        writer = _audit(tmp_path)
        payload = {"id": "disp_100", "payment_id": "pay_100", "status": "open"}

        from api.routes.chargeback_webhook import process_chargeback_event

        await process_chargeback_event("chargeback.created", payload, redis, writer)

        stored = await redis.get("chargeback:dispute:disp_100")
        assert stored is not None
        assert json.loads(stored)["payment_id"] == "pay_100"
        assert writer.entry_count >= 1

    async def test_created_with_txn_mapping_assembles_rebuttal(self, tmp_path):
        writer = _audit(tmp_path)
        writer.append(
            "SCORE_DECISION",
            "U001",
            "ALLOW",
            {
                "txn_id": "TXN_9",
                "merchant_id": "M001",
                "amount": 1200.0,
                "device_fingerprint": "DEV-1",
                "triggered_rules": [],
            },
        )
        reader = AuditLogReader(str(tmp_path))
        redis = FakeRedis()
        await redis.set(
            "chargeback:payment_txn:pay_900",
            json.dumps({"txn_id": "TXN_9"}),
        )

        from api.routes.chargeback_webhook import process_chargeback_event

        payload = {
            "id": "disp_200",
            "payment_id": "pay_900",
            "status": "open",
            "reason_code": "10.4",
            "network": "UPI",
        }
        await process_chargeback_event(
            "chargeback.created", payload, redis, writer, audit_reader=reader
        )

        rebuttal_raw = await redis.get("chargeback:rebuttal:disp_200")
        assert rebuttal_raw is not None
        doc = json.loads(rebuttal_raw)
        assert doc["dispute_id"] == "disp_200"
        assert doc["transaction_id"] == "TXN_9"
        assert reader.get_transaction("TXN_9") is not None

    async def test_closed_records_outcome(self, tmp_path):
        redis = FakeRedis()
        writer = _audit(tmp_path)

        from api.routes.chargeback_webhook import process_chargeback_event

        await process_chargeback_event(
            "chargeback.closed", {"id": "disp_300", "status": "won"}, redis, writer
        )
        assert writer.entry_count >= 1
        assert await redis.get("chargeback:dispute:disp_300") is None

    async def test_missing_chargeback_is_noop(self, tmp_path):
        redis = FakeRedis()
        writer = _audit(tmp_path)

        from api.routes.chargeback_webhook import process_chargeback_event

        await process_chargeback_event("chargeback.created", None, redis, writer)
        assert writer.entry_count == 0


class TestWebhookRoute:
    async def test_requires_valid_signature(self):
        from httpx import ASGITransport, AsyncClient

        from api.main import app

        app.state.resources = {"redis": FakeRedis()}
        transport = ASGITransport(app=app)
        body = json.dumps(
            {"event": "chargeback.created", "payload": {"chargeback": {"entity": {}}}}
        ).encode()
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhooks/razorpay/chargeback",
                content=body,
                headers={"X-Razorpay-Signature": "deadbeef"},
            )
            assert resp.status_code == 400

            secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "payshield-webhook-dev-secret")
            sig = compute_signature(secret, body)
            resp2 = await ac.post(
                "/webhooks/razorpay/chargeback",
                content=body,
                headers={"X-Razorpay-Signature": sig},
            )
            assert resp2.status_code == 200
            assert resp2.json()["status"] == "processed"
