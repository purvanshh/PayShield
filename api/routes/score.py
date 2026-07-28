import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_ensemble, get_redis, get_statistical_filter, verify_api_key
from api.exceptions import BatchSizeExceededError
from api.rbac import require_permission
from api.schemas import BatchScoreRequest, BatchScoreResponse, FraudScoreResponse, ScoreRequest

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

try:
    from engine.statistical_filter import StatisticalFilter
    from engine.ensemble import EnsembleFusionEngine, EnsembleResult
    _engines_available = True
except ImportError:
    _engines_available = False

try:
    from tasks.investigation_task import generate_investigation
    _celery_available = True
except ImportError:
    _celery_available = False


@router.post("/score", response_model=FraudScoreResponse)
async def score_transaction(
    txn: ScoreRequest,
    request: Request,
    stat_filter=Depends(get_statistical_filter),
    ensemble=Depends(get_ensemble),
    redis=Depends(get_redis),
):
    start = time.time()

    try:
        txn_hash = hashlib.sha256(txn.txn_id.encode()).hexdigest()
        idempotent = await redis.get(f"idempotent:{txn_hash}")
        if idempotent:
            cached = json.loads(idempotent)
            return FraudScoreResponse(**cached)
    except Exception as e:
        logger.warning(f"Redis idempotency check failed: {e}")

    txn_dict = txn.model_dump()
    txn_dict["timestamp"] = txn.timestamp.timestamp()

    try:
        if stat_filter:
            layer1_result = await stat_filter.evaluate(txn_dict, redis)
        else:
            layer1_result = type("L1", (), {"decision": "ALLOW", "triggered_rules": [], "confidence": 0.0})()
    except Exception as e:
        logger.error(f"Layer1 evaluation failed: {e}")
        layer1_result = type("L1", (), {"decision": "ALLOW", "triggered_rules": [], "confidence": 0.0})()

    l1_decision = getattr(layer1_result, "decision", "ALLOW")
    if l1_decision == "BLOCK":
        result = {
            "txn_id": txn.txn_id,
            "decision": "BLOCK",
            "fraud_probability": 1.0,
            "layer_triggered": "L1_STATISTICAL",
            "evidence": {"triggered_rules": getattr(layer1_result, "triggered_rules", [])},
            "latency_ms": 0.0,
            "model_version": "1.0.0",
        }
        elapsed = (time.time() - start) * 1000
        result["latency_ms"] = round(elapsed, 2)
        _enqueue_investigation(txn.txn_id, result)
        try:
            await _cache_result(redis, txn_hash, result)
        except Exception:
            pass
        return FraudScoreResponse(**result)

    l2_result = type("L2", (), {
        "fraud_probability": 0.0, "source": "L2_GNN",
        "graph_features": {"velocity": {}, "geo": {}, "benford": {}},
        "latency_ms": 0.0,
    })()

    try:
        ensemble_result = ensemble.fuse(layer1_result, l2_result) if ensemble else EnsembleResult()
    except Exception as e:
        logger.error(f"Ensemble fusion failed: {e}")
        ensemble_result = EnsembleResult()

    response_data = {
        "txn_id": txn.txn_id,
        "decision": getattr(ensemble_result, "decision", "ALLOW"),
        "fraud_probability": getattr(ensemble_result, "confidence", 0.0),
        "layer_triggered": getattr(ensemble_result, "source", "ENSEMBLE"),
        "evidence": {
            "triggered_rules": getattr(layer1_result, "triggered_rules", []),
            "ensemble_confidence": getattr(ensemble_result, "confidence", 0.0),
        },
        "latency_ms": 0.0,
        "model_version": "1.0.0",
    }
    elapsed = (time.time() - start) * 1000
    response_data["latency_ms"] = round(elapsed, 2)

    if response_data["decision"] in ("BLOCK", "REVIEW"):
        _enqueue_investigation(txn.txn_id, response_data)
        await _broadcast_alert(request, txn.txn_id, response_data)

    try:
        await _cache_result(redis, txn_hash, response_data)
    except Exception:
        pass

    return FraudScoreResponse(**response_data)


@router.post("/batch", response_model=BatchScoreResponse)
async def batch_score(
    batch: BatchScoreRequest,
    stat_filter=Depends(get_statistical_filter),
    ensemble=Depends(get_ensemble),
    redis=Depends(get_redis),
    _=Depends(require_permission("score", "read")),
):
    if len(batch.transactions) > 100:
        raise BatchSizeExceededError()

    start = time.time()
    sem = asyncio.Semaphore(20)

    async def score_single(txn: ScoreRequest):
        async with sem:
            try:
                txn_dict = txn.model_dump()
                txn_dict["timestamp"] = txn.timestamp.timestamp()
                if stat_filter:
                    layer1_result = await stat_filter.evaluate(txn_dict, redis)
                else:
                    layer1_result = type("L1", (), {"decision": "ALLOW", "triggered_rules": [], "confidence": 0.0})()
                l2r = type("L2", (), {"fraud_probability": 0.0, "source": "L2_GNN", "graph_features": {}, "latency_ms": 0.0})()
                er = ensemble.fuse(layer1_result, l2r) if ensemble else type("ER", (), {"decision": "ALLOW", "confidence": 0.0, "source": "ENSEMBLE"})()
                return FraudScoreResponse(
                    txn_id=txn.txn_id,
                    decision=getattr(er, "decision", "ALLOW"),
                    fraud_probability=getattr(er, "confidence", 0.0),
                    layer_triggered=getattr(er, "source", "ENSEMBLE"),
                    evidence={},
                    latency_ms=0.0,
                    model_version="1.0.0",
                )
            except Exception as e:
                logger.error(f"Batch score failed for {txn.txn_id}: {e}")
                return FraudScoreResponse(
                    txn_id=txn.txn_id,
                    decision="ALLOW",
                    fraud_probability=0.0,
                    layer_triggered="L1_STATISTICAL",
                    evidence={"error": str(e)},
                    latency_ms=0.0,
                    model_version="1.0.0",
                )

    results = await asyncio.gather(*[score_single(t) for t in batch.transactions])
    batch_ms = (time.time() - start) * 1000
    return BatchScoreResponse(results=list(results), batch_latency_ms=round(batch_ms, 2))


async def _broadcast_alert(request: Request, txn_id: str, result: dict):
    try:
        from api.websocket import manager
        await manager.broadcast({
            "type": "fraud_alert",
            "txn_id": txn_id,
            "decision": result["decision"],
            "fraud_probability": result["fraud_probability"],
            "layer_triggered": result.get("layer_triggered", ""),
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.debug(f"Alert broadcast skipped: {e}")


def _enqueue_investigation(txn_id: str, result: dict):
    if not _celery_available:
        return
    try:
        generate_investigation.delay(txn_id, json.dumps(result))
        logger.info(f"Investigation enqueued for {txn_id}")
    except Exception as e:
        logger.warning(f"Failed to enqueue investigation: {e}")


async def _cache_result(redis, txn_hash: str, result: dict, ttl: int = 60):
    try:
        await redis.set(f"idempotent:{txn_hash}", json.dumps(result), ttl=ttl)
    except Exception:
        pass
