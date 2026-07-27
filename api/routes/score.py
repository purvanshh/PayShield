import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_ensemble, get_redis, get_statistical_filter, verify_api_key
from api.exceptions import BatchSizeExceededError
from api.rbac import require_permission
from api.schemas import (BatchScoreRequest, BatchScoreResponse,
                          FraudScoreResponse, ScoreRequest)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

try:
    from engine.statistical_filter import StatisticalFilter, StatisticalFilter as SF
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
    stat_filter=Depends(get_statistical_filter),
    ensemble=Depends(get_ensemble),
    redis=Depends(get_redis),
):
    start = time.time()

    txn_hash = hashlib.sha256(txn.txn_id.encode()).hexdigest()
    idempotent = await redis.get(f"idempotent:{txn_hash}")
    if idempotent:
        cached = json.loads(idempotent)
        return FraudScoreResponse(**cached)

    txn_dict = txn.model_dump()
    txn_dict["timestamp"] = txn.timestamp.timestamp()

    layer1_result = await stat_filter.evaluate(txn_dict, redis) if stat_filter else type("L1", (), {"decision": "ALLOW", "triggered_rules": [], "confidence": 0.0})()

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
        await _cache_result(redis, txn_hash, result)
        return FraudScoreResponse(**result)

    l2_result = type("L2", (), {
        "fraud_probability": 0.0, "source": "L2_GNN",
        "graph_features": {"velocity": {}, "geo": {}, "benford": {}},
        "latency_ms": 0.0,
    })()
    ensemble_result = ensemble.fuse(layer1_result, l2_result) if ensemble else EnsembleResult()

    response_data = {
        "txn_id": txn.txn_id,
        "decision": ensemble_result.decision if hasattr(ensemble_result, "decision") else "ALLOW",
        "fraud_probability": ensemble_result.confidence if hasattr(ensemble_result, "confidence") else 0.0,
        "layer_triggered": ensemble_result.source if hasattr(ensemble_result, "source") else "ENSEMBLE",
        "evidence": {"triggered_rules": getattr(layer1_result, "triggered_rules", []),
                     "ensemble_confidence": ensemble_result.confidence if hasattr(ensemble_result, "confidence") else 0.0},
        "latency_ms": 0.0,
        "model_version": "1.0.0",
    }
    elapsed = (time.time() - start) * 1000
    response_data["latency_ms"] = round(elapsed, 2)

    if response_data["decision"] in ("BLOCK", "REVIEW"):
        _enqueue_investigation(txn.txn_id, response_data)

    await _cache_result(redis, txn_hash, response_data)
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
            txn_dict = txn.model_dump()
            txn_dict["timestamp"] = txn.timestamp.timestamp()
            layer1_result = await stat_filter.evaluate(txn_dict, redis) if stat_filter else type("L1", (), {"decision": "ALLOW", "triggered_rules": [], "confidence": 0.0})()
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

    results = await asyncio.gather(*[score_single(t) for t in batch.transactions])
    batch_ms = (time.time() - start) * 1000
    return BatchScoreResponse(results=list(results), batch_latency_ms=round(batch_ms, 2))


def _enqueue_investigation(txn_id: str, result: dict):
    if _celery_available:
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
