"""Return-risk API routes (Track 02 - Phase 16).

- ``POST /v1/return/score``     checkout-time risk assessment (read-only)
- ``POST /v1/return/update``    return-management callback refreshing the profile
- ``GET  /v1/return/profile/{user_id}``  merchant-dashboard user history

Follows PayShield conventions: API-key auth, per-route RBAC, background
profile refresh (never blocks the score response), audit-chain logging and
Prometheus instrumentation.
"""

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends

from api.dependencies import get_redis, verify_api_key
from api.rbac import require_permission
from api.schemas.return_risk import (
    ReturnProfileData,
    ReturnScoreEnvelopeResponse,
    ReturnScoreRequest,
    ReturnStatusUpdateRequest,
    ReturnStatusUpdateResponse,
)
from return_risk.feature_engine import ReturnRiskFeatureEngine
from return_risk.rules_engine import RulesEngine
from return_risk.scorer import ReturnRiskScorer
from store.audit_log import async_audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

try:
    from observability.metrics import return_risk_counter, return_risk_latency

    _metrics_available = True
except ImportError:
    _metrics_available = False


def _get_scorer(redis) -> ReturnRiskScorer:
    return ReturnRiskScorer(
        feature_engine=ReturnRiskFeatureEngine(redis),
        rules_engine=RulesEngine(),
    )


@router.post("/return/score", response_model=ReturnScoreEnvelopeResponse)
async def score_return_risk(
    request: ReturnScoreRequest,
    background_tasks: BackgroundTasks,
    redis=Depends(get_redis),
    _=Depends(require_permission("return_risk", "read")),
):
    """Score an order for return-risk (checkout / pre-dispatch).

    Read-only against the feature store: the scoring path never mutates
    Redis. The user profile is refreshed in the background so the next
    score sees the latest order count.
    """
    start = time.perf_counter()
    if _metrics_available:
        return_risk_counter.inc()

    scorer = _get_scorer(redis)
    result = await scorer.score(
        user_id=request.user_id,
        merchant_id=request.merchant_id,
        order_id=request.order_id,
        amount=request.amount,
        category=request.category,
        cod_flag=request.cod_flag,
        payment_method=request.payment_method,
        timestamp=request.timestamp,
    )

    background_tasks.add_task(
        scorer.feature_engine.update_user_profile,
        user_id=request.user_id,
        order_id=request.order_id,
        amount=request.amount,
        category=request.category,
        cod_flag=request.cod_flag,
        returned=False,
    )

    try:
        from observability.return_risk_drift import record_return_risk_samples

        await record_return_risk_samples(redis, result["feature_breakdown"])
    except Exception as e:
        logger.debug("return-risk drift sampling skipped: %s", e)

    async_audit_logger.append(
        event_type="RETURN_RISK_SCORED",
        actor=request.user_id,
        decision=result["risk_tier"],
        payload={
            "order_id": request.order_id,
            "merchant_id": request.merchant_id,
            "score": result["return_risk_score"],
            "tier": result["risk_tier"],
        },
    )

    elapsed = (time.perf_counter() - start) * 1000
    if _metrics_available:
        return_risk_latency.observe(elapsed / 1000.0)

    return ReturnScoreEnvelopeResponse(
        status="SUCCESS",
        data=result,
        latency_ms=round(elapsed, 2),
    )


@router.post("/return/update", response_model=ReturnStatusUpdateResponse)
async def update_return_status(
    request: ReturnStatusUpdateRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("return_risk", "write")),
):
    """Record a return event (merchant return-management callback).

    Refreshes the user profile (counters, velocity, reason distribution,
    running average) so subsequent scores are based on current history.
    """
    start = time.perf_counter()
    scorer = _get_scorer(redis)
    await scorer.feature_engine.update_user_profile(
        user_id=request.user_id,
        order_id=request.order_id,
        amount=request.amount,
        category=request.category,
        cod_flag=request.cod_flag,
        returned=request.returned,
        return_reason=request.return_reason,
    )

    async_audit_logger.append(
        event_type="RETURN_RISK_UPDATED",
        actor=request.user_id,
        decision="RETURNED" if request.returned else "ORDER_RECORDED",
        payload={"order_id": request.order_id, "return_reason": request.return_reason},
    )

    return ReturnStatusUpdateResponse(
        status="SUCCESS",
        data={
            "order_id": request.order_id,
            "user_id": request.user_id,
            "status": "updated",
            "returned": request.returned,
        },
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )


@router.get(
    "/return/profile/{user_id}",
    response_model=ReturnProfileData,
)
async def get_user_return_profile(
    user_id: str,
    redis=Depends(get_redis),
    _=Depends(require_permission("return_risk", "read")),
):
    """Return the user's return-risk profile (merchant dashboard)."""
    start = time.perf_counter()
    scorer = _get_scorer(redis)
    features = await scorer.feature_engine.extract_features(
        user_id=user_id,
        merchant_id="__profile__",
        category="default",
        amount=0,
        cod_flag=False,
    )
    data = scorer._build_user_profile(features)
    return ReturnProfileData(
        user_id=user_id,
        total_orders=data["total_orders"],
        total_returns=data["total_returns"],
        return_rate_30d=data["return_rate_30d"],
        return_rate_lifetime=data["return_rate_lifetime"],
        serial_returner=data["serial_returner"],
        avg_return_value=data["avg_return_value"],
        is_new_user=data["is_new_user"],
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )
