"""Razorpay webhook handler for the return-risk flow (Track 02 - Phase 4).

Two signed endpoints that make PayShield a *pre-shipping risk layer* for
Razorpay merchants:

- ``POST /webhooks/razorpay/return-risk`` — on ``order.paid``, adapt the
  order (+ payment) into PayShield features and score return risk before
  dispatch.
- ``POST /webhooks/razorpay/refund`` — on ``refund.processed``, record a
  ground-truth label for the nightly reflection/retraining loop.

Auth is the HMAC webhook signature itself (no API key), matching the
existing ``/webhooks/razorpay/chargeback`` convention. Unverified payloads
are rejected with ``400`` before any work happens.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_redis
from chargeback.signatures import verify_signature
from integrations.razorpay_adapter import RazorpayAdapter
from return_risk.feature_engine import ReturnRiskFeatureEngine
from return_risk.rules_engine import RulesEngine
from return_risk.scorer import ReturnRiskScorer
from store.audit_log import async_audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

LABELS_KEY = "return_risk:labels"


def _webhook_secret() -> str:
    import os

    return os.getenv("RAZORPAY_WEBHOOK_SECRET", "payshield-webhook-dev-secret")


def _verify(payload: bytes, signature: str) -> bool:
    return verify_signature(_webhook_secret(), payload, signature)


@router.post("/webhooks/razorpay/return-risk")
async def razorpay_return_risk_webhook(
    request: Request,
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """Score return risk from a Razorpay ``order.paid`` event.

    Returns the same envelope as ``POST /v1/return/score`` so the merchant's
    WMS can act on it inline (ship / review / prepaid-only).
    """
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify(payload, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = json.loads(payload)
    event = data.get("event", "")
    if event != "order.paid":
        return {"status": "ignored", "event": event}

    order_entity = data.get("payload", {}).get("order", {}).get("entity", {})
    payment_entity = data.get("payload", {}).get("payment", {}).get("entity")

    scoring_input = RazorpayAdapter.order_to_scoring_input(
        order=order_entity, payment=payment_entity
    )

    try:
        scorer = ReturnRiskScorer(
            feature_engine=ReturnRiskFeatureEngine(redis),
            rules_engine=RulesEngine(),
        )
        result = await scorer.score(
            user_id=scoring_input.user_id,
            merchant_id=scoring_input.merchant_id,
            order_id=scoring_input.order_id,
            amount=scoring_input.amount,
            category=scoring_input.category,
            cod_flag=scoring_input.cod_flag,
            payment_method=scoring_input.payment_method,
            timestamp=scoring_input.timestamp,
        )
    except Exception as e:  # nosec B110 - score failure degrades, never crashes the webhook
        logger.warning("return-risk scoring failed in webhook: %s", e)
        result = {
            "order_id": scoring_input.order_id,
            "return_risk_score": None,
            "risk_tier": "UNKNOWN",
            "error": str(e),
        }
        async_audit_logger.append(
            event_type="RETURN_RISK_WEBHOOK_SCORE_FAILED",
            actor=scoring_input.user_id,
            decision="ERROR",
            payload={"order_id": scoring_input.order_id},
        )
        return {"status": "scored_with_error", "data": result}

    async_audit_logger.append(
        event_type="RETURN_RISK_WEBHOOK_SCORED",
        actor=scoring_input.user_id,
        decision=result.get("risk_tier", ""),
        payload={
            "order_id": scoring_input.order_id,
            "merchant_id": scoring_input.merchant_id,
            "score": result.get("return_risk_score"),
            "tier": result.get("risk_tier"),
            "source_event": "order.paid",
        },
    )

    return {
        "status": "scored",
        "order_id": scoring_input.order_id,
        "data": result,
        "features": RazorpayAdapter.scoring_input_to_payload(scoring_input),
    }


@router.post("/webhooks/razorpay/refund")
async def razorpay_refund_webhook(
    request: Request,
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """Record a return-risk label from a Razorpay ``refund.processed`` event.

    Every processed refund is a positive training example. Labels are pushed
    to ``return_risk:labels`` and consumed by the nightly reflection /
    retraining task (see ``tasks/reflection_task.py``).
    """
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify(payload, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = json.loads(payload)
    event = data.get("event", "")
    if event != "refund.processed":
        return {"status": "ignored", "event": event}

    def _entity(section: str) -> dict[str, Any]:
        return data.get("payload", {}).get(section, {}).get("entity", {})

    order_entity = _entity("order")
    payment_entity = _entity("payment")
    refund_entity = _entity("refund")

    label = RazorpayAdapter.refund_to_label(payment_entity, refund_entity, order_entity or None)

    try:
        await redis.lpush(LABELS_KEY, json.dumps(label, default=str))
    except Exception as e:  # nosec B110 - label persistence failure degrades to audit-only
        logger.warning("label persistence failed: %s", e)

    async_audit_logger.append(
        event_type="RETURN_RISK_LABEL_RECORDED",
        actor=label["user_id"],
        decision="RETURNED",
        payload={
            "order_id": label["order_id"],
            "refund_id": label["refund_id"],
            "amount": str(label["refund_amount"]),
            "reason": label["return_reason"],
        },
    )

    return {"status": "label_recorded", "label": label}
