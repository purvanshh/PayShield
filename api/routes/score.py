import time

from fastapi import APIRouter, Depends

from api.schemas import TransactionEvent, FraudScoreResponse, BatchScoreRequest, BatchScoreResponse
from api.dependencies import verify_api_key, get_feature_store, get_ensemble
from store.feature_store import FeatureStore
from engine.ensemble import EnsembleScorer
from observability.metrics import inference_latency, fraud_score_histogram

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/score", response_model=FraudScoreResponse)
async def score_transaction(
    txn: TransactionEvent,
    feature_store: FeatureStore = Depends(get_feature_store),
    ensemble: EnsembleScorer = Depends(get_ensemble),
):
    start = time.time()

    txn_ts = txn.timestamp.timestamp()
    feature_store.increment_velocity_counter(txn.user_id, txn_ts)
    feature_store.set_device_fingerprint(txn.device_fingerprint, txn.user_id)
    feature_store.set_geospatial_cache(txn.user_id, txn.location.lat, txn.location.lon, txn_ts)

    result = ensemble.score(txn, feature_store)

    elapsed_ms = (time.time() - start) * 1000
    result["latency_ms"] = round(elapsed_ms, 2)

    inference_latency.labels(layer=result["layer_triggered"]).observe(elapsed_ms / 1000)
    fraud_score_histogram.observe(result["fraud_probability"])

    return FraudScoreResponse(
        txn_id=txn.txn_id,
        decision=result["decision"],
        fraud_probability=round(result["fraud_probability"], 4),
        layer_triggered=result["layer_triggered"],
        evidence=result["evidence"],
        latency_ms=result["latency_ms"],
        model_version=result["model_version"],
    )


@router.post("/batch", response_model=BatchScoreResponse)
async def batch_score(
    batch: BatchScoreRequest,
    feature_store: FeatureStore = Depends(get_feature_store),
    ensemble: EnsembleScorer = Depends(get_ensemble),
):
    results = []
    for txn in batch.transactions:
        txn_ts = txn.timestamp.timestamp()
        feature_store.increment_velocity_counter(txn.user_id, txn_ts)
        feature_store.set_device_fingerprint(txn.device_fingerprint, txn.user_id)
        feature_store.set_geospatial_cache(txn.user_id, txn.location.lat, txn.location.lon, txn_ts)

        start = time.time()
        result = ensemble.score(txn, feature_store)
        elapsed_ms = (time.time() - start) * 1000

        results.append(
            FraudScoreResponse(
                txn_id=txn.txn_id,
                decision=result["decision"],
                fraud_probability=round(result["fraud_probability"], 4),
                layer_triggered=result["layer_triggered"],
                evidence=result["evidence"],
                latency_ms=round(elapsed_ms, 2),
                model_version=result["model_version"],
            )
        )

    return BatchScoreResponse(results=results)
