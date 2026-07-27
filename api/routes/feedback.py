import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends

from api.dependencies import get_redis, verify_api_key
from api.exceptions import PayShieldException
from api.rbac import require_permission
from api.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackRequest,
    redis=Depends(get_redis),
    _=Depends(require_permission("feedback", "write")),
):
    txn_key = f"investigation:{feedback.txn_id}"
    existing = redis.get(txn_key)
    if not existing:
        raise PayShieldException(status_code=404, detail=f"Transaction {feedback.txn_id} not found")

    feedback_id = f"fb_{datetime.utcnow().timestamp()}_{feedback.txn_id}"
    payload = {
        "feedback_id": feedback_id,
        "txn_id": feedback.txn_id,
        "original_decision": feedback.original_decision,
        "analyst_decision": feedback.analyst_decision,
        "analyst_id": feedback.analyst_id,
        "category": feedback.category,
        "reason": feedback.reason,
        "created_at": datetime.utcnow().isoformat(),
    }

    fb_key = f"feedback:{feedback.txn_id}:{feedback.analyst_id}"
    redis.set(fb_key, json.dumps(payload), ttl=2592000)

    redis.lpush("feedback:recent", json.dumps(payload))
    redis.ltrim("feedback:recent", 0, 999)

    try:
        from agents.human_review_agent import HumanReviewAgent
        from agents.base import AgentConfig
        from agents.message import AgentMessage
        agent = HumanReviewAgent(AgentConfig(agent_id="api_feedback", agent_type="HUMAN_REVIEW"))
        msg = AgentMessage(
            sender="api",
            recipient="human_review_agent",
            message_type="EVENT",
            content={
                "type": "ANALYST_FEEDBACK",
                "feedback": payload,
                "agent_type": "LAYER1",
            },
        )
        await agent.process(msg)
    except Exception as e:
        logger.warning(f"Failed to notify HumanReviewAgent: {e}")

    if feedback.category in ("FALSE_POSITIVE", "FALSE_NEGATIVE"):
        logger.warning(f"Model degradation signal: {feedback.category} for {feedback.txn_id}")

    return FeedbackResponse(
        status="ok",
        feedback_id=feedback_id,
        message="Feedback recorded and agent weights updated",
    )


@router.get("/feedback/stats")
async def feedback_stats(
    redis=Depends(get_redis),
    _=Depends(require_permission("feedback", "write")),
):
    recent_raw = redis.lrange("feedback:recent", 0, 999) or []
    entries = []
    for r in recent_raw:
        try:
            entries.append(json.loads(r) if isinstance(r, str) else r)
        except Exception:
            continue
    total = len(entries)
    by_category: dict[str, int] = {}
    for e in entries:
        cat = e.get("category", "UNKNOWN")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total_feedback": total,
        "by_category": by_category,
        "recent": entries[-20:],
    }
