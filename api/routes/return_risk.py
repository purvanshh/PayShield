"""Return-risk API routes (Track 02 - Phase 16).

- ``POST /v1/return/score``     checkout-time risk assessment (read-only)
- ``POST /v1/return/update``    return-management callback refreshing the profile
- ``GET  /v1/return/profile/{user_id}``  merchant-dashboard user history

Follows PayShield conventions: API-key auth, per-route RBAC, background
profile refresh (never blocks the score response), audit-chain logging and
Prometheus instrumentation.
"""

import json
import logging
import time

import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, BackgroundTasks, Depends

from api.dependencies import get_redis, verify_api_key
from api.rbac import require_permission
from api.schemas.return_risk import (
    ReturnExplainResponse,
    ReturnProfileData,
    ReturnScoreEnvelopeResponse,
    ReturnScoreRequest,
    ReturnSimulateRequest,
    ReturnSimulateResponse,
    ReturnStatusUpdateRequest,
    ReturnStatusUpdateResponse,
    WaterfallContribution,
)
from return_risk.feature_engine import (
    CATEGORY_BASELINES,
    PAYMENT_METHOD_RISK,
    ReturnRiskFeatureEngine,
)
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


async def _publish_agent_feed(redis, *, user_id, order_id, merchant_id, score, tier, amount) -> None:
    """Mirror a scored order onto the Redis agent feed.

    The audit chain (local JSONL) stays the compliance record. The background
    agent worker may run on a different host than the API (e.g. Render splits
    the two into separate services with separate disks), where it cannot read
    the API's audit file. Publishing a copy to ``agent:feed:return_risk`` lets
    the worker consume scored orders over Redis instead. Never raises.
    """
    if redis is None:
        return
    try:
        await redis.rpush(
            "agent:feed:return_risk",
            json.dumps(
                {
                    "user_id": user_id,
                    "order_id": order_id,
                    "merchant_id": merchant_id,
                    "score": float(score),
                    "tier": tier,
                    "amount": float(amount or 0.0),
                }
            ),
        )
    except Exception as e:
        logger.debug("agent_feed_publish_failed: %s", e)


def _address_key(request: ReturnScoreRequest) -> str:
    """Normalise the shipping address for the abuse-ring sentinel.

    Pincode is the strongest location signal; fall back to city + state when a
    merchant does not collect it. Empty when no address was provided (feature
    engine then emits a neutral ``txn_shared_address_count`` of 0).
    """
    addr = request.shipping_address
    if addr is None:
        return ""
    if addr.pincode:
        return f"{addr.pincode}"
    parts = [p for p in (addr.city, addr.state) if p]
    return ", ".join(parts)


# Waterfall normalisation mirrors the model's training envelope so every
# contribution is on a comparable [0, 1] scale (rates/baselines/method risk are
# already there; ratio and days-since are capped at their DGP maxima).
_WATERFALL_CAP = {
    "amount_vs_user_aov_ratio": 4.0,
    "days_since_last_order": 60.0,
}


def _normalize_for_waterfall(feature: str, value: float) -> float:
    cap = _WATERFALL_CAP.get(feature, 1.0)
    return min(max(float(value), 0.0) / cap, 1.0)


def _build_waterfall(result: dict) -> list[WaterfallContribution]:
    """Approximate per-feature attribution for the XGBoost engine.

    contribution = gain importance x normalised feature value. The model output
    is nonlinear, so this ranks the drivers of a score rather than exactly
    decomposing the probability (see the endpoint's ``note``).
    """
    xgb_features = result.get("xgb_features") or {}
    importance = result.get("feature_importance") or {}
    return sorted(
        (
            WaterfallContribution(
                feature=feature,
                value=round(float(value), 4),
                importance=round(float(importance.get(feature, 0.0)), 4),
                contribution=round(
                    float(importance.get(feature, 0.0))
                    * _normalize_for_waterfall(feature, float(value)),
                    4,
                ),
            )
            for feature, value in xgb_features.items()
        ),
        key=lambda c: c.contribution,
        reverse=True,
    )


@router.post("/return/explain", response_model=ReturnExplainResponse)
async def explain_return_risk(
    request: ReturnScoreRequest,
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
    _=Depends(require_permission("return_risk", "read")),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """Score an order and return the XGBoost feature-waterfall attribution.

    Read-only analysis surface: never mutates Redis and never triggers the
    background profile refresh. Same inputs as ``POST /v1/return/score``.
    """
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
        device_fingerprint=request.device_fingerprint,
        shipping_address=_address_key(request),
    )

    waterfall = _build_waterfall(result)
    note = (
        "Approximate attribution: model gain importance x normalized feature value. "
        "The XGBoost output is nonlinear, so these rank the drivers of the score, "
        "not an exact decomposition of the probability."
    )
    return ReturnExplainResponse(
        order_id=result["order_id"],
        return_risk_score=result["return_risk_score"],
        risk_tier=result["risk_tier"],
        engine=result.get("engine", "hand_weighted"),
        base_score=0.5,
        waterfall=waterfall,
        note=note,
    )


# --------------------------------------------------------------------------- #
# Calibration simulator                                                        #
# --------------------------------------------------------------------------- #

# The "stage" toggle swaps between the production 7-feature model and the
# premium 9-feature model (adds product_rating + delivery_speed_days), so the
# simulator shows how better data changes the score - not a hardcoded offset.
_SIMULATE_MODEL_PATHS = {
    "basic": "models/return_risk_xgb_v1.json",
    "premium": "models/return_risk_xgb_best_premium.json",
}
_simulate_model_cache: dict[str, xgb.XGBClassifier] = {}


def _simulate_model(stage: str) -> xgb.XGBClassifier:
    path = _SIMULATE_MODEL_PATHS[stage]
    if stage not in _simulate_model_cache:
        model = xgb.XGBClassifier()
        model.load_model(path)
        _simulate_model_cache[stage] = model
    return _simulate_model_cache[stage]


def _simulate_tier(score: float) -> str:
    if score <= 0.30:
        return "LOW"
    if score <= 0.70:
        return "MEDIUM"
    return "HIGH"


@router.post("/return/simulate", response_model=ReturnSimulateResponse)
async def simulate_return_risk(
    request: ReturnSimulateRequest,
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """Score an arbitrary feature vector against the basic or premium model.

    Pure computation - no Redis, no side effects. Amount/AOV ratio is capped
    to the model's training envelope ([0.15, 4.0]); premium stage adds the two
    observed features. Useful for showing how the score responds to data
    quality and feature changes (the dashboard /simulator page).
    """
    ratio = min(max(float(request.amount) / float(request.user_aov), 0.15), 4.0)
    features: dict[str, float] = {
        "user_return_rate_30d": request.user_return_rate_30d,
        "user_return_rate_90d": request.user_return_rate_90d,
        "amount_vs_user_aov_ratio": round(ratio, 4),
        "category_return_baseline": float(
            CATEGORY_BASELINES.get(request.category, CATEGORY_BASELINES["default"])
        ),
        "payment_method_risk": float(
            PAYMENT_METHOD_RISK.get(request.payment_method, PAYMENT_METHOD_RISK["UPI"])
        ),
        "device_fingerprint_match": request.device_fingerprint_match,
        "days_since_last_order": request.days_since_last_order,
    }
    if request.stage == "premium":
        features["product_rating"] = request.product_rating
        features["delivery_speed_days"] = request.delivery_speed_days

    model = _simulate_model(request.stage)
    score = float(model.predict_proba(pd.DataFrame([features]))[0, 1])

    return ReturnSimulateResponse(
        return_risk_score=round(score, 4),
        risk_tier=_simulate_tier(score),
        stage=request.stage,
        model_path=_SIMULATE_MODEL_PATHS[request.stage],
        features=features,
    )


@router.post("/return/score", response_model=ReturnScoreEnvelopeResponse)
async def score_return_risk(
    request: ReturnScoreRequest,
    background_tasks: BackgroundTasks,
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
    _=Depends(require_permission("return_risk", "read")),  # noqa: B008 - FastAPI dependency-injection idiom
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
        device_fingerprint=request.device_fingerprint,
        shipping_address=_address_key(request),
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
    await _publish_agent_feed(
        redis,
        user_id=request.user_id,
        order_id=request.order_id,
        merchant_id=request.merchant_id,
        score=result["return_risk_score"],
        tier=result["risk_tier"],
        amount=request.amount,
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
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
    _=Depends(require_permission("return_risk", "write")),  # noqa: B008 - FastAPI dependency-injection idiom
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
    redis=Depends(get_redis),  # noqa: B008 - FastAPI dependency-injection idiom
    _=Depends(require_permission("return_risk", "read")),  # noqa: B008 - FastAPI dependency-injection idiom
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
