import json
from datetime import datetime

from fastapi import APIRouter, Depends

from api.schemas import FeedbackRequest, FeedbackResponse
from api.dependencies import verify_api_key, get_redis
from store.redis_client import RedisClient

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest, redis: RedisClient = Depends(get_redis)):
    key = f"feedback:{feedback.txn_id}:{feedback.analyst_id}"
    payload = {
        "txn_id": feedback.txn_id,
        "analyst_id": feedback.analyst_id,
        "correct_decision": feedback.correct_decision,
        "comment": feedback.comment,
        "submitted_at": datetime.utcnow().isoformat(),
    }
    redis.set(key, json.dumps(payload), ttl=2592000)
    return FeedbackResponse(status="ok", message="Feedback recorded")
