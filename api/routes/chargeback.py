"""Chargeback API routes (Track 02 - Phase 12).

FastAPI route handlers for the chargeback evidence responder:

- ``POST /v1/chargeback/respond``   assemble a rebuttal (merchant reviews it)
- ``GET  /v1/chargeback/{dispute_id}``  retrieve a cached rebuttal
- ``POST /v1/chargeback/{dispute_id}/submit``  human-in-the-loop submission

Follows PayShield's conventions: API-key auth, per-route RBAC, timeout-guarded
external calls, audit logging to the tamper-evident chain and Prometheus
instrumentation. Generation and submission stay separate on purpose - the AI
drafts, a human (or the admin role) pulls the trigger.
"""

import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_redis, verify_api_key
from api.rbac import ENFORCER, get_current_user, require_permission
from api.schemas.chargeback import (
    ChargebackRebuttalDocument,
    ChargebackRespondData,
    ChargebackRespondRequest,
    ChargebackRespondResponse,
    ChargebackSubmitData,
    ChargebackSubmitRequest,
    ChargebackSubmitResponse,
)
from chargeback.exceptions import ChargebackTransactionNotFoundError
from chargeback.razorpay_client import RazorpayClient
from store.audit_log import async_audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

try:
    from observability.metrics import chargeback_counter, chargeback_latency, chargeback_submitted

    _metrics_available = True
except ImportError:
    _metrics_available = False

REBUTTAL_TTL_SECONDS = 30 * 86400
CONFIDENCE_THRESHOLD = float(os.getenv("PAYSHIELD_CHARGEBACK_CONFIDENCE_THRESHOLD", "0.6"))
# LLM narrative is opt-in (Ollama must be reachable); otherwise the builder
# uses the deterministic fallback narrative, keeping endpoints operational
# without local LLM infrastructure.
LLM_ENABLED = os.getenv("PAYSHIELD_CHARGEBACK_LLM", "false") == "true"
RAZORPAY_MOCK = os.getenv("RAZORPAY_MOCK_MODE", "true") == "true"


def _get_evidence_collector(redis):
    from chargeback.evidence_collector import ChargebackEvidenceCollector
    from store.audit_log import AuditLogReader

    return ChargebackEvidenceCollector(redis=redis, audit_reader=AuditLogReader())


def _get_rebuttal_builder(redis, razorpay_client=None):
    from chargeback.rebuttal_builder import ChargebackRebuttalBuilder

    if LLM_ENABLED:
        from llm.client import OllamaClient

        llm_client = OllamaClient()
    else:
        llm_client = None
    return ChargebackRebuttalBuilder(
        evidence_collector=_get_evidence_collector(redis),
        llm_client=llm_client,
        razorpay_client=razorpay_client or RazorpayClient(mock_mode=RAZORPAY_MOCK),
        config={"confidence_threshold": CONFIDENCE_THRESHOLD},
    )


def _rebuttal_id(dispute_id: str) -> str:
    return f"reb_{dispute_id[:12]}"


async def _cache_rebuttal(redis, rebuttal: ChargebackRebuttalDocument) -> None:
    try:
        await redis.set(
            f"chargeback:rebuttal:{rebuttal.dispute_id}",
            rebuttal.model_dump_json(),
            ttl=REBUTTAL_TTL_SECONDS,
        )
        await redis.set(
            f"chargeback:payment_txn:{rebuttal.payment_id}",
            json.dumps({"txn_id": rebuttal.transaction_id}),
            ttl=REBUTTAL_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning("rebuttal cache write failed: %s", e)


async def _load_rebuttal(redis, dispute_id: str) -> ChargebackRebuttalDocument | None:
    try:
        raw = await redis.get(f"chargeback:rebuttal:{dispute_id}")
        if not raw:
            return None
        return ChargebackRebuttalDocument.model_validate_json(raw)
    except Exception as e:
        logger.warning("rebuttal cache read failed: %s", e)
        return None


def _warnings_for(rebuttal: ChargebackRebuttalDocument) -> list[str]:
    warnings = []
    if rebuttal.evidence.graph_evidence is None:
        warnings.append("Graph evidence incomplete: user has <2 graph nodes")
    if rebuttal.evidence.investigation_report is None:
        warnings.append("LLM investigation report not available")
    if rebuttal.confidence_score < CONFIDENCE_THRESHOLD:
        warnings.append("Evidence below threshold; manual review recommended")
    return warnings


@router.post("/chargeback/respond", response_model=ChargebackRespondResponse)
async def respond_to_chargeback(
    request: ChargebackRespondRequest,
    redis=Depends(get_redis),
    principal=Depends(get_current_user),
):
    """Assemble a chargeback rebuttal from PayShield's stored evidence.

    Retrieves the original transaction, collects L1/L2/L3 evidence, generates
    the narrative and produces the Razorpay payload - all without submitting
    anything. ``auto_submit`` (admin role only) is the escape hatch.
    """
    start = time.perf_counter()
    if _metrics_available:
        chargeback_counter.inc()

    builder = _get_rebuttal_builder(redis)
    try:
        rebuttal = await builder.build_rebuttal(
            dispute_id=request.dispute_id,
            payment_id=request.payment_id,
            transaction_id=request.transaction_id,
            network=request.network or "UPI",
            reason_code=request.reason_code or "",
            reason_description=request.reason_description,
            response_deadline=request.response_deadline,
        )
    except ChargebackTransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if request.auto_submit:
        if not ENFORCER.has_permission(principal, "chargeback", "admin"):
            raise HTTPException(
                status_code=403, detail="Auto-submit requires chargeback:admin permission"
            )
        if rebuttal.evidence.completeness_score < CONFIDENCE_THRESHOLD:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Insufficient evidence to auto-submit "
                    f"(completeness {rebuttal.evidence.completeness_score:.2f} < "
                    f"{CONFIDENCE_THRESHOLD}); review the draft first"
                ),
            )
        if builder.razorpay_client is not None:
            await builder.razorpay_client.contest_chargeback(
                dispute_id=request.dispute_id, rebuttal=rebuttal
            )
            if _metrics_available:
                chargeback_submitted.inc()

    await _cache_rebuttal(redis, rebuttal)
    async_audit_logger.append(
        event_type="CHARGEBACK_REBUTTAL_BUILT",
        actor="api",
        decision=rebuttal.response_type,
        payload={
            "dispute_id": rebuttal.dispute_id,
            "payment_id": rebuttal.payment_id,
            "confidence": rebuttal.confidence_score,
            "completeness": rebuttal.evidence.completeness_score,
        },
    )

    elapsed = (time.perf_counter() - start) * 1000
    if _metrics_available:
        chargeback_latency.observe(elapsed / 1000.0)

    return ChargebackRespondResponse(
        status="SUCCESS",
        data=ChargebackRespondData(
            rebuttal_id=_rebuttal_id(rebuttal.dispute_id),
            dispute_id=rebuttal.dispute_id,
            response_type=rebuttal.response_type,
            confidence_score=rebuttal.confidence_score,
            evidence_completeness=rebuttal.evidence.completeness_score,
            narrative=rebuttal.narrative.model_dump(),
            razorpay_payload=rebuttal.razorpay_payload,
            audit_trail=rebuttal.audit_trail,
            warnings=_warnings_for(rebuttal),
        ),
        latency_ms=round(elapsed, 2),
    )


@router.get("/chargeback/{dispute_id}", response_model=ChargebackRespondResponse)
async def get_chargeback_rebuttal(
    dispute_id: str,
    redis=Depends(get_redis),
):
    """Retrieve a previously generated rebuttal by dispute id."""
    rebuttal = await _load_rebuttal(redis, dispute_id)
    if rebuttal is None:
        raise HTTPException(
            status_code=404,
            detail=f"Rebuttal for dispute {dispute_id} not found",
        )
    return ChargebackRespondResponse(
        status="SUCCESS",
        data=ChargebackRespondData(
            rebuttal_id=_rebuttal_id(dispute_id),
            dispute_id=rebuttal.dispute_id,
            response_type=rebuttal.response_type,
            confidence_score=rebuttal.confidence_score,
            evidence_completeness=rebuttal.evidence.completeness_score,
            narrative=rebuttal.narrative.model_dump(),
            razorpay_payload=rebuttal.razorpay_payload,
            audit_trail=rebuttal.audit_trail,
            warnings=_warnings_for(rebuttal),
        ),
        latency_ms=0.0,
    )


@router.post("/chargeback/{dispute_id}/submit", response_model=ChargebackSubmitResponse)
async def submit_chargeback_rebuttal(
    dispute_id: str,
    request: ChargebackSubmitRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("chargeback", "admin")),
):
    """Submit a drafted rebuttal to Razorpay (human in the loop).

    The AI generates the draft; a human reviewer (or an admin credential)
    decides when the contest actually goes out.
    """
    rebuttal = await _load_rebuttal(redis, dispute_id)
    if rebuttal is None:
        raise HTTPException(
            status_code=404,
            detail=f"Rebuttal for dispute {dispute_id} not found",
        )

    razorpay_client = RazorpayClient(mock_mode=RAZORPAY_MOCK)
    try:
        if request.strike == "accept":
            result = await razorpay_client.submit_contest(
                dispute_id, {"contest": False, "comment": request.comment}
            )
        else:
            result = await razorpay_client.contest_chargeback(dispute_id, rebuttal)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay submission failed: {e}") from e

    status = result.get("razorpay_response", {}).get("status", "")
    async_audit_logger.append(
        event_type="CHARGEBACK_SUBMITTED",
        actor="api",
        decision=request.strike.upper(),
        payload={
            "dispute_id": dispute_id,
            "razorpay_status": status,
            "mock": bool(result.get("mock", False)),
        },
    )
    if _metrics_available:
        chargeback_submitted.inc()

    return ChargebackSubmitResponse(
        status="SUBMITTED",
        data=ChargebackSubmitData(
            submission_id=f"sub_{dispute_id[:12]}",
            dispute_id=dispute_id,
            razorpay_status=status,
            latency_ms=0.0,
        ),
        latency_ms=0.0,
    )
