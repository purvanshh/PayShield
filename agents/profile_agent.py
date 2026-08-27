import logging
import statistics
from datetime import datetime, timedelta
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class ProfileAgent(BaseAgent):
    """Maintains per-user return-risk profiles from scored orders.

    Consumes ``RETURN_RISK_SCORED`` events (order + score + tier) and
    accumulates a rolling profile: order count, average amount, COD share,
    category mix and the running mean return-risk score. When a user's recent
    behaviour drifts from their own history, it broadcasts a ``PROFILE_ANOMALY``
    so downstream agents can react.
    """

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="profile_agent", agent_type="PROFILE"))
        self._profiles: dict[str, dict] = {}
        self._history: dict[str, list[dict]] = {}

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "RETURN_RISK_SCORED":
            return await self._handle_score_event(message)
        elif msg_type == "PROFILE_QUERY":
            return await self._handle_profile_query(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_score_event(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id", "")
        order = content.get("order", {})

        self._update_profile(user_id, order)
        drift_score = self._detect_drift(user_id)

        response = {
            "user_id": user_id,
            "profile_updated": True,
            "drift_score": drift_score,
            "anomaly": drift_score > 0.5,
        }
        if drift_score > 0.5:
            await self.send_message(
                recipient="broadcast", content={
                    "type": "PROFILE_ANOMALY", "user_id": user_id,
                    "drift_score": drift_score, "severity": "HIGH" if drift_score > 0.7 else "MEDIUM",
                }, message_type="EVENT",
            )
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content=response,
            correlation_id=message.message_id,
        )

    async def _handle_profile_query(self, message: AgentMessage) -> AgentMessage:
        user_id = message.content.get("user_id", "")
        profile = self._profiles.get(user_id, {})
        drift = self._detect_drift(user_id)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content={
                "user_id": user_id, "profile": profile,
                "drift_score": drift, "anomaly": drift > 0.5,
            },
            correlation_id=message.message_id,
        )

    def _update_profile(self, user_id: str, order: dict):
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                "order_count": 0, "total_amount": 0.0, "avg_amount": 0.0,
                "categories": set(), "cod_count": 0,
                "score_sum": 0.0, "avg_score": 0.0,
                "first_order": datetime.utcnow(), "last_order": datetime.utcnow(),
            }
            self._history[user_id] = []
        p = self._profiles[user_id]
        amount = float(order.get("amount", 0) or 0)
        p["order_count"] += 1
        p["total_amount"] += amount
        p["avg_amount"] = p["total_amount"] / p["order_count"]
        p["last_order"] = datetime.utcnow()
        category = order.get("category", "")
        if category:
            p["categories"].add(category)
        if order.get("cod_flag"):
            p["cod_count"] += 1
        score = float(order.get("score", 0) or 0)
        p["score_sum"] += score
        p["avg_score"] = p["score_sum"] / p["order_count"]

        self._history[user_id].append({
            "amount": amount,
            "score": score,
            "cod_flag": bool(order.get("cod_flag", False)),
            "category": category,
            "timestamp": datetime.utcnow().isoformat(),
        })
        if len(self._history[user_id]) > 100:
            self._history[user_id] = self._history[user_id][-100:]

    def _detect_drift(self, user_id: str) -> float:
        """Drift of the last 10 orders' return-risk score vs the user's own
        older baseline."""
        history = self._history.get(user_id, [])
        if len(history) < 10:
            return 0.0
        recent = history[-10:]
        older = history[:-10] if len(history) > 20 else history[:-5]
        if not older:
            return 0.0
        recent_avg = statistics.mean([t["score"] for t in recent])
        older_avg = statistics.mean([t["score"] for t in older])
        if older_avg == 0:
            return 0.0
        ratio = abs(recent_avg - older_avg) / max(older_avg, 0.01)
        return round(min(1.0, ratio / 3.0), 4)

    def get_profile(self, user_id: str) -> dict:
        profile = self._profiles.get(user_id, {})
        return {
            **profile,
            "categories": sorted(profile.get("categories", set())),
        }