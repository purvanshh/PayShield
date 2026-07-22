from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import InvestigationReport
from api.dependencies import verify_api_key, get_redis
from store.redis_client import RedisClient

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/investigation/{txn_id}", response_model=InvestigationReport)
async def get_investigation(txn_id: str, redis: RedisClient = Depends(get_redis)):
    key = f"investigation:{txn_id}"
    raw = redis.get(key)
    if raw is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    import json
    data = json.loads(raw)
    return InvestigationReport(
        txn_id=data["txn_id"],
        narrative=data["narrative"],
        fraud_type=data["fraud_type"],
        confidence=data["confidence"],
        recommended_action=data["recommended_action"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
    )
