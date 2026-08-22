"""Razorpay chargeback webhook handler (Track 02 - Phase 11).

Receives ``chargeback.created`` / ``chargeback.updated`` /
``chargeback.closed`` events, verifies the HMAC signature over the raw body,
then records the event in the tamper-evident audit chain and triggers
rebuttal generation for filed disputes (when the internal transaction id can
be resolved).

Auth model: the HMAC signature is the credential - no API key here. The
route rejects unsigned payloads with 400 before any work happens.
"""

import json
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.dependencies import get_redis
from chargeback.signatures import verify_signature
from store.audit_log import async_audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

PENDING_TTL_SECONDS = 30 * 86400


async def process_chargeback_event(
    event: str, chargeback: dict | None, redis, audit_writer=None, audit_reader=None
) -> None:
    """Handle a verified chargeback event (runs in background).

    - created: persist the dispute marker and, when the internal txn id is
      resolvable (``chargeback:payment_txn:{payment_id}`` was recorded by
      ``POST /v1/chargeback/respond``), assemble the rebuttal and cache it
      under ``chargeback:rebuttal:{dispute_id}``.
    - updated/closed: log the outcome for the feedback loop.

    ``audit_writer`` defaults to the app-wide async audit logger; tests inject
    a directory-local :class:`AuditLogWriter`. ``audit_reader`` defaults to
    the standard JSONL chain reader.
    """
    writer = audit_writer or async_audit_logger
    if not chargeback:
        return
    dispute_id = chargeback.get("id", "")
    payment_id = chargeback.get("payment_id", "")
    status = chargeback.get("status", "")

    writer.append(
        event_type=f"CHARGEBACK_{event.split('.')[-1].upper()}",
        actor="razorpay_webhook",
        decision=status or "OPEN",
        payload={"dispute_id": dispute_id, "payment_id": payment_id},
    )

    try:
        if event == "chargeback.created":
            await redis.set(
                f"chargeback:dispute:{dispute_id}",
                json.dumps(
                    {
                        "dispute_id": dispute_id,
                        "payment_id": payment_id,
                        "status": status,
                        "received_at": datetime.now(UTC).isoformat(),
                    }
                ),
                ttl=PENDING_TTL_SECONDS,
            )
            txn_id_raw = await redis.get(f"chargeback:payment_txn:{payment_id}")
            if txn_id_raw:
                txn_id = json.loads(txn_id_raw).get("txn_id", "")
                if txn_id:
                    from chargeback.evidence_collector import ChargebackEvidenceCollector
                    from chargeback.razorpay_client import RazorpayClient
                    from chargeback.rebuttal_builder import ChargebackRebuttalBuilder
                    from store.audit_log import AuditLogReader

                    reader = audit_reader or AuditLogReader()
                    collector = ChargebackEvidenceCollector(redis=redis, audit_reader=reader)
                    builder = ChargebackRebuttalBuilder(
                        evidence_collector=collector,
                        llm_client=None,
                        razorpay_client=RazorpayClient(mock_mode=True),
                    )
                    rebuttal = await builder.build_rebuttal(
                        dispute_id=dispute_id,
                        payment_id=payment_id,
                        transaction_id=txn_id,
                        network=chargeback.get("network", "UPI"),
                        reason_code=chargeback.get("reason_code", ""),
                        reason_description=chargeback.get("reason_description", ""),
                    )
                    await redis.set(
                        f"chargeback:rebuttal:{dispute_id}",
                        rebuttal.model_dump_json(),
                        ttl=PENDING_TTL_SECONDS,
                    )
                    writer.append(
                        event_type="CHARGEBACK_REBUTTAL_GENERATED",
                        actor="razorpay_webhook",
                        decision=rebuttal.response_type,
                        payload={
                            "dispute_id": dispute_id,
                            "confidence": rebuttal.confidence_score,
                            "completeness": rebuttal.evidence.completeness_score,
                        },
                    )
        elif event == "chargeback.closed":
            writer.append(
                event_type="CHARGEBACK_OUTCOME_RECORDED",
                actor="razorpay_webhook",
                decision=status or "CLOSED",
                payload={"dispute_id": dispute_id, "outcome": status},
            )
    except Exception as e:
        logger.warning("chargeback webhook processing failed: %s", e)


@router.post("/webhooks/razorpay/chargeback")
async def razorpay_chargeback_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    redis=Depends(get_redis),
):
    """Handle Razorpay chargeback webhooks (signature-verified)."""
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "payshield-webhook-dev-secret")

    if not verify_signature(secret, payload, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = json.loads(payload)
    event = data.get("event", "")
    chargeback = data.get("payload", {}).get("chargeback", {}).get("entity", {})
    background_tasks.add_task(process_chargeback_event, event, chargeback, redis)
    return {"status": "processed"}
