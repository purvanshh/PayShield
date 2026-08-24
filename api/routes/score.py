import asyncio
import hashlib
import json
import logging
import os
import statistics
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_ensemble, get_redis, get_statistical_filter, verify_api_key
from api.exceptions import BatchSizeExceededError
from api.rbac import require_permission
from api.schemas import BatchScoreRequest, BatchScoreResponse, FraudScoreResponse, ScoreRequest

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

try:
    from engine.constants import L2Status
    from engine.ensemble import EnsembleFusionEngine, EnsembleResult, Layer2Result
    from engine.statistical_filter import GeoPoint, Layer1Result, StatisticalFilter

    _engines_available = True
except ImportError:
    _engines_available = False

try:
    from tasks.investigation_task import generate_investigation

    _celery_available = True
except ImportError:
    _celery_available = False

try:
    from observability.metrics import (
        fraud_score_histogram,
        inference_latency,
        layer1_block_rate,
        layer2_escalation_rate,
        llm_queue_depth,
        redis_hit_rate,
    )

    _metrics_available = True
except ImportError:
    _metrics_available = False


def _observe_l1_block(result: dict, l1_ms: float):
    if not _metrics_available:
        return
    try:
        layer1_block_rate.inc()
        fraud_score_histogram.observe(1.0)
        inference_latency.labels(layer="l1_rules").observe(l1_ms / 1000.0)
    except Exception as e:
        logger.debug(f"metrics_record_failed: {e}")


def _observe_ensemble(
    result: dict, l1_ms: float, l2_ms: float, ensemble_ms: float, l2_escalated: bool
):
    if not _metrics_available:
        return
    try:
        fraud_score_histogram.observe(result["fraud_probability"])
        inference_latency.labels(layer="l1_rules").observe(l1_ms / 1000.0)
        if l2_escalated:
            layer2_escalation_rate.inc()
            inference_latency.labels(layer="l2_gnn").observe(l2_ms / 1000.0)
        inference_latency.labels(layer="ensemble").observe(ensemble_ms / 1000.0)
    except Exception as e:
        logger.debug(f"metrics_record_failed: {e}")


async def _record_and_build_features(
    redis, txn: ScoreRequest
) -> tuple[dict, dict, GeoPoint | None, dict | None]:
    """Record the transaction in Redis and derive velocity/geo features from real history."""
    now = txn.timestamp.timestamp()
    user_id = txn.user_id
    device = txn.device_fingerprint or "UNKNOWN_DEVICE"
    merchant = txn.merchant_id
    amount = txn.amount

    user_key = f"velocity:user:{user_id}"
    dev_key = f"velocity:dev:{device}"
    loc_key = f"velocity:loc:{user_id}"
    # Scored once per external txn id: re-scoring the same order (idempotent
    # retries, dashboard replays, verification loops) must never double-count
    # into the velocity windows or it fabricates bursts for honest users.
    dedupe_key = f"velocity:dedup:{txn.txn_id}"

    entry = json.dumps(
        {"ts": now, "amount": amount, "merchant": merchant, "user": user_id, "device": device}
    )

    try:
        if await redis.exists(dedupe_key):
            return await _derive_features(redis, txn, user_key, dev_key, loc_key, now)
    except Exception as e:
        logger.warning(f"velocity_dedupe_check_failed: {e}")

    try:
        pipe = await redis.pipeline()
        pipe.lpush(user_key, entry)
        pipe.ltrim(user_key, 0, 999)
        pipe.expire(user_key, 7 * 86400)
        pipe.lpush(dev_key, entry)
        pipe.ltrim(dev_key, 0, 999)
        pipe.expire(dev_key, 7 * 86400)
        pipe.setex(dedupe_key, 7 * 86400, "1")
        await pipe.execute()
    except Exception as e:
        logger.warning(f"feature_record_failed: {e}")

    return await _derive_features(redis, txn, user_key, dev_key, loc_key, now)


async def _derive_features(
    redis,
    txn: ScoreRequest,
    user_key: str,
    dev_key: str,
    loc_key: str,
    now: float,
) -> tuple[dict, dict, GeoPoint | None, dict | None]:
    """Compute velocity/geo features from recorded history (read-only)."""
    merchant = txn.merchant_id
    amount = txn.amount

    def parse_entries(raw: list[str]) -> list[dict]:
        out = []
        for r in raw:
            try:
                d = json.loads(r)
                out.append(d)
            except Exception:
                continue
        return out

    last_loc = None
    try:
        raw_loc = await redis.get(loc_key)
        if raw_loc:
            loc_data = json.loads(raw_loc)
            last_loc = GeoPoint(lat=loc_data["lat"], lon=loc_data["lon"], timestamp=loc_data["ts"])
    except Exception:
        pass

    if txn.location:
        try:
            await redis.set(
                loc_key,
                json.dumps({"lat": txn.location.lat, "lon": txn.location.lon, "ts": now}),
                ttl=7 * 86400,
            )
        except Exception:
            pass

    try:
        user_txns = parse_entries(await redis.lrange(user_key, 0, -1))
        dev_txns = parse_entries(await redis.lrange(dev_key, 0, -1))
    except Exception:
        user_txns, dev_txns = [], []

    past = [e for e in user_txns if e["ts"] < now - 1]
    window_5m = [e for e in past if e["ts"] >= now - 300]
    window_1h = [e for e in past if e["ts"] >= now - 3600]
    window_24h = [e for e in past if e["ts"] >= now - 86400]

    gap_min = 1440.0
    if past:
        gap_min = (now - max(e["ts"] for e in past)) / 60.0
    loc_dist_km = 0.0
    if txn.location and last_loc is not None:
        try:
            from engine.graph_feature_engine import haversine_km

            loc_dist_km = haversine_km(
                last_loc.lat,
                last_loc.lon,
                txn.location.lat,
                txn.location.lon,
            )
        except Exception:
            loc_dist_km = 0.0

    merchant_round_share = 0.0
    try:
        from store.feature_store import FeatureCache

        cache = FeatureCache(redis)
        await cache.record_merchant_amount(merchant, amount)
        merchant_round_share = await cache.merchant_round_share(merchant)
    except Exception:
        pass

    amounts = [e["amount"] for e in past]
    median_amount = statistics.median(amounts) if amounts else 500.0
    std_amount = statistics.pstdev(amounts) if len(amounts) > 1 else median_amount * 0.25
    z_score = (amount - median_amount) / std_amount if std_amount > 0 else 0.0

    dev_window_24h = [e for e in dev_txns if e["ts"] >= now - 86400]
    distinct_users_dev = len({e["user"] for e in dev_window_24h})

    velocity_features = {
        "txn_count_5m": len(window_5m),
        "txn_count_1h": len(window_1h),
        "amount_total_1h": round(sum(e["amount"] for e in window_1h), 2),
        "device_txn_count_24h": len(dev_window_24h),
        "distinct_users_last_24h": distinct_users_dev,
        "ip_txn_count_5m": 0,
        "distinct_merchants_1h": len({e["merchant"] for e in window_1h}),
        "inter_arrival_gap_min": round(gap_min, 2),
        "loc_dist_km": round(loc_dist_km, 2),
        "merchant_round_share": merchant_round_share,
    }
    deviation_features = {
        "baseline_txn_count_24h": len(window_24h),
        "median_amount_30d": median_amount,
        "amount_z_score": round(z_score, 4),
    }
    baseline = {
        "max_location_distance_km": 50.0,
        "centroid_lat": last_loc.lat if last_loc else None,
        "centroid_lon": last_loc.lon if last_loc else None,
    }
    if baseline["centroid_lat"] is None:
        baseline = None

    return velocity_features, deviation_features, last_loc, baseline


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
        (
            velocity_features,
            deviation_features,
            last_loc,
            baseline,
        ) = await _record_and_build_features(redis, txn)
        await _write_to_graph_db(request, txn, velocity_features)
    except Exception as e:
        logger.warning(f"feature_build_failed: {e}")
        velocity_features, deviation_features, last_loc, baseline = {}, None, None, None

    await _record_drift_samples(redis, velocity_features)

    t1 = time.time()
    try:
        if stat_filter:
            layer1_result = await stat_filter.evaluate(
                velocity_features,
                deviation_features,
                current_loc=GeoPoint(
                    lat=txn.location.lat, lon=txn.location.lon, timestamp=txn.timestamp.timestamp()
                )
                if txn.location
                else None,
                last_loc=last_loc,
                baseline=baseline,
                account_age_days=365.0,
                user_country=None,
                txn_country=None,
                merchant_id=txn.merchant_id,
                amount=txn.amount,
                is_shell_merchant=False,
            )
        else:
            layer1_result = Layer1Result()
    except Exception as e:
        logger.error(f"Layer1 evaluation failed: {e}")
        layer1_result = Layer1Result()
    l1_ms = (time.time() - t1) * 1000

    l1_decision = getattr(layer1_result, "decision", "ALLOW")
    if l1_decision == "BLOCK":
        result = {
            "txn_id": txn.txn_id,
            "decision": "BLOCK",
            "fraud_probability": 1.0,
            "layer_triggered": "L1_STATISTICAL",
            "evidence": {
                "triggered_rules": getattr(layer1_result, "triggered_rules", []),
                "latency_breakdown": {"l1_rules_ms": round(l1_ms, 2), "ensemble_ms": 0.0},
            },
            "latency_ms": 0.0,
            "model_version": "1.0.0",
        }
        elapsed = (time.time() - start) * 1000
        result["latency_ms"] = round(elapsed, 2)
        _observe_l1_block(result, l1_ms)
        _persist_explanation(txn, layer1_result, velocity_features, deviation_features, result)
        _enqueue_investigation(txn.txn_id, result)
        _append_audit_entry(txn, result)
        try:
            await _cache_result(redis, txn_hash, result)
        except Exception:
            pass
        return FraudScoreResponse(**result)

    l2_result = await _run_l2_inference(request, txn)

    t2 = time.time()
    try:
        ensemble_result = ensemble.fuse(layer1_result, l2_result) if ensemble else EnsembleResult()
    except Exception as e:
        logger.error(f"Ensemble fusion failed: {e}")
        ensemble_result = EnsembleResult()
    ensemble_ms = (time.time() - t2) * 1000

    l2_status = getattr(l2_result, "status", None)
    l2_prob = getattr(l2_result, "fraud_probability", None)

    response_data = {
        "txn_id": txn.txn_id,
        "decision": getattr(ensemble_result, "decision", "ALLOW"),
        "fraud_probability": getattr(ensemble_result, "confidence", 0.0),
        "layer_triggered": getattr(ensemble_result, "source", "ENSEMBLE"),
        "evidence": {
            "triggered_rules": getattr(layer1_result, "triggered_rules", []),
            "ensemble_confidence": getattr(ensemble_result, "confidence", 0.0),
            "l2_status": l2_status,
            "l2_probability": l2_prob,
            "l2_latency_ms": getattr(l2_result, "latency_ms", 0.0),
            "latency_breakdown": {
                "l1_rules_ms": round(l1_ms, 2),
                "ensemble_ms": round(ensemble_ms, 2),
            },
        },
        "latency_ms": 0.0,
        "model_version": "1.0.0",
        "layer1_decision": getattr(layer1_result, "decision", "ALLOW"),
        "layer1_confidence": getattr(layer1_result, "confidence", 0.0),
        "layer2_probability": l2_prob,
        "layer2_source": getattr(l2_result, "source", "L2_GNN"),
        "layer2_status": l2_status,
        "graph_features": getattr(l2_result, "graph_features", {}),
    }
    elapsed = (time.time() - start) * 1000
    response_data["latency_ms"] = round(elapsed, 2)

    _observe_ensemble(
        response_data,
        l1_ms,
        getattr(l2_result, "latency_ms", 0.0),
        ensemble_ms,
        l2_escalated=l2_status == "SUCCESS",
    )

    if response_data["decision"] in ("BLOCK", "REVIEW"):
        _persist_explanation(
            txn, layer1_result, velocity_features, deviation_features, response_data
        )
        _enqueue_investigation(txn.txn_id, response_data)
        await _broadcast_alert(request, txn.txn_id, response_data)

    try:
        await _cache_result(redis, txn_hash, response_data)
    except Exception:
        pass

    _append_audit_entry(txn, response_data, redis)

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
                try:
                    (
                        velocity_features,
                        deviation_features,
                        last_loc,
                        baseline,
                    ) = await _record_and_build_features(redis, txn)
                    await _record_drift_samples(redis, velocity_features)
                except Exception:
                    velocity_features, deviation_features, last_loc, baseline = {}, None, None, None
                if stat_filter:
                    layer1_result = await stat_filter.evaluate(
                        velocity_features,
                        deviation_features,
                        current_loc=GeoPoint(
                            lat=txn.location.lat,
                            lon=txn.location.lon,
                            timestamp=txn.timestamp.timestamp(),
                        )
                        if txn.location
                        else None,
                        last_loc=last_loc,
                        baseline=baseline,
                        merchant_id=txn.merchant_id,
                        amount=txn.amount,
                    )
                else:
                    layer1_result = Layer1Result()
                l2r = Layer2Result(graph_features={})
                er = ensemble.fuse(layer1_result, l2r) if ensemble else EnsembleResult()
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


async def _run_l2_inference(request: Request, txn: ScoreRequest) -> Layer2Result:
    """Conditional L2 GNN inference.

    - model not loaded        -> status=MODEL_UNAVAILABLE
    - ego graph too small     -> status=SKIPPED_NO_GRAPH
    - inference > 20ms        -> status=TIMEOUT
    - otherwise               -> status=SUCCESS with fraud_probability

    Never raises; the ensemble falls back to L1-only fusion on any failure.
    """
    try:
        resources = getattr(request.app.state, "resources", {})
        service = resources.get("l2_inference")
        graph_db = resources.get("graph_db")
        if service is None or graph_db is None:
            return Layer2Result(status=L2Status.MODEL_UNAVAILABLE, graph_features={})

        from engine.graph_feature_engine import extract_ego_graph_live

        ego = extract_ego_graph_live(
            graph_db.graph,
            user_id=txn.user_id,
            merchant_id=txn.merchant_id,
            device_id=txn.device_fingerprint or None,
        )
        out = await service.predict(
            ego,
            user_id=txn.user_id,
            merchant_id=txn.merchant_id,
            device_id=txn.device_fingerprint or None,
        )
        return Layer2Result(
            fraud_probability=out["fraud_probability"] if out["status"] == "SUCCESS" else None,
            source="L2_GNN",
            graph_features={"nodes": out.get("nodes", 0), "edges": out.get("edges", 0)},
            latency_ms=out.get("latency_ms", 0.0),
            status=L2Status(out["status"]),
        )
    except Exception as e:
        logger.warning(f"l2_inference_failed: {e}")
        return Layer2Result(status=L2Status.ERROR, graph_features={})


async def _write_to_graph_db(request: Request, txn: ScoreRequest, velocity_features: dict):
    """Mirror the live transaction into Neo4j (when available) and the
    in-memory NetworkX graph, plus the Redis device->users index.

    Transaction and merchant nodes carry the velocity/geo/round-share
    attributes the GNN feature engine reads back at scoring time.
    """
    try:
        resources = getattr(request.app.state, "resources", {})
        writer = resources.get("graph_writer")
        if writer is None:
            return
        txn_dict = txn.model_dump()
        txn_dict["timestamp"] = txn.timestamp.timestamp()
        if txn.location:
            txn_dict["lat"], txn_dict["lon"] = txn.location.lat, txn.location.lon
        for key in ("inter_arrival_gap_min", "txn_count_5m", "txn_count_1h", "loc_dist_km"):
            if key in velocity_features:
                txn_dict[key] = velocity_features[key]
        if "merchant_round_share" in velocity_features:
            txn_dict["round_amount_share"] = velocity_features["merchant_round_share"]
        await writer.write_transaction(txn_dict, velocity_features)
    except Exception as e:
        logger.debug(f"graph_write_failed: {e}")


async def _broadcast_alert(request: Request, txn_id: str, result: dict):
    try:
        from api.websocket import manager

        await manager.broadcast(
            {
                "type": "fraud_alert",
                "txn_id": txn_id,
                "decision": result["decision"],
                "fraud_probability": result["fraud_probability"],
                "layer_triggered": result.get("layer_triggered", ""),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
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


async def _record_drift_samples(redis, velocity_features: dict):
    """Log per-feature values into time-scored zsets for PSI drift analysis.

    Convention: member = "{ts}:{value}" (unique per sample), score = timestamp.
    """
    try:
        import time as _time

        now = _time.time()
        pipe = await redis.pipeline()
        for name, value in velocity_features.items():
            if isinstance(value, (int, float)):
                pipe.zadd(f"drift:feat:{name}", {f"{now}:{float(value)}": now})
        pipe.zremrangebyscore("drift:feat:txn_count_5m", 0, now - 48 * 3600)
        await pipe.execute()
    except Exception as e:
        logger.debug(f"drift_sample_record_failed: {e}")


def _persist_explanation(
    txn, layer1_result, velocity_features: dict, deviation_features: dict, result: dict
):
    """Persist explanation artifacts for BLOCK/REVIEW decisions (RBI AI-1 / PCI 10.x)."""
    try:
        explanation_dir = "models/production/explanations"
        os.makedirs(explanation_dir, exist_ok=True)
        artifact = {
            "txn_id": txn.txn_id,
            "decision": result["decision"],
            "triggered_rules": getattr(layer1_result, "triggered_rules", []),
            "rule_details": getattr(layer1_result, "rule_details", []),
            "velocity_features": velocity_features,
            "deviation_features": deviation_features,
            "explanation_source": "L1_STATISTICAL",
            "generated_at": datetime.utcnow().isoformat(),
        }
        path = os.path.join(explanation_dir, f"{txn.txn_id}.json")
        with open(path, "w") as f:
            json.dump(artifact, f, indent=2)
    except Exception as e:
        logger.debug(f"explanation_persist_failed: {e}")


def _append_audit_entry(txn, result: dict, redis=None):
    """Append tamper-evident, PII-masked audit entry for every decision.

    Uses the async queue-backed logger when available (non-blocking, <1ms);
    falls back to the synchronous writer otherwise.
    """
    payload = {
        "txn_id": txn.txn_id,
        "merchant_id": txn.merchant_id,
        "amount": txn.amount,
        "device_fingerprint": txn.device_fingerprint,
        "fraud_probability": result["fraud_probability"],
        "layer_triggered": result["layer_triggered"],
        "triggered_rules": result["evidence"].get("triggered_rules", []),
    }
    try:
        from store.audit_log import AuditLogWriter, async_audit_logger

        async_audit_logger.append(
            event_type="SCORE_DECISION",
            actor=txn.user_id,
            decision=result["decision"],
            payload=payload,
        )
    except Exception:
        try:
            writer = AuditLogWriter()
            writer.append(
                event_type="SCORE_DECISION",
                actor=txn.user_id,
                decision=result["decision"],
                payload=payload,
            )
        except Exception as e:
            logger.debug(f"audit_append_failed: {e}")
