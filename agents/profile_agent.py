import logging
import statistics
from datetime import datetime, timedelta
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType
from agents.state import AgentState

logger = logging.getLogger(__name__)


class ProfileAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="profile_agent", agent_type="PROFILE"))
        self._profiles: dict[str, dict] = {}
        self._history: dict[str, list[dict]] = {}

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "USER_TXN_EVENT":
            return await self._handle_txn_event(message)
        elif msg_type == "PROFILE_QUERY":
            return await self._handle_profile_query(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_txn_event(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id", "")
        txn = content.get("txn", {})

        self._update_profile(user_id, txn)
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

    def _update_profile(self, user_id: str, txn: dict):
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                "txn_count": 0, "total_amount": 0.0, "avg_amount": 0.0,
                "merchants": set(), "devices": set(), "locations": set(),
                "first_txn": datetime.utcnow(), "last_txn": datetime.utcnow(),
            }
            self._history[user_id] = []
        p = self._profiles[user_id]
        p["txn_count"] += 1
        p["total_amount"] += float(txn.get("amount", 0))
        p["avg_amount"] = p["total_amount"] / p["txn_count"]
        p["last_txn"] = datetime.utcnow()
        if "merchant_id" in txn:
            p["merchants"].add(txn["merchant_id"])
        if "device_id" in txn:
            p["devices"].add(txn["device_id"])
        if "location" in txn:
            p["locations"].add(str(txn["location"]))

        self._history[user_id].append({
            "amount": float(txn.get("amount", 0)),
            "timestamp": datetime.utcnow().isoformat(),
        })
        if len(self._history[user_id]) > 100:
            self._history[user_id] = self._history[user_id][-100:]

    def _detect_drift(self, user_id: str) -> float:
        history = self._history.get(user_id, [])
        if len(history) < 10:
            return 0.0
        recent = history[-10:]
        older = history[:-10] if len(history) > 20 else history[:-5]
        if not older:
            return 0.0
        recent_avg = statistics.mean([t["amount"] for t in recent])
        older_avg = statistics.mean([t["amount"] for t in older])
        if older_avg == 0:
            return 0.0
        ratio = abs(recent_avg - older_avg) / max(older_avg, 0.01)
        drift = min(1.0, ratio / 3.0)
        return round(drift, 4)
