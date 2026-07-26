import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class TransactionAnalysisAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="transaction_agent", agent_type="TRANSACTION"))
        self._txn_log: dict[str, list[dict]] = defaultdict(list)

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "TXN_SCORE_REQUEST":
            return await self._handle_score_request(message)
        elif msg_type == "SPLIT_DETECT":
            return await self._handle_split_detect(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_score_request(self, message: AgentMessage) -> AgentMessage:
        txn = message.content.get("txn", {})
        user_id = txn.get("user_id", "")
        merchant_id = txn.get("merchant_id", "")

        velocity_score = self._velocity_analysis(user_id)
        split_score = self._split_analysis(user_id, txn)
        merchant_score = self._merchant_risk(merchant_id)
        amount_score = self._amount_analysis(txn)

        avg_risk = (velocity_score + split_score + merchant_score + amount_score) / 4.0

        response = {
            "type": "TXN_ANALYSIS_RESULT",
            "user_id": user_id,
            "risk_score": round(avg_risk, 4),
            "components": {
                "velocity": velocity_score,
                "split_detection": split_score,
                "merchant_risk": merchant_score,
                "amount_anomaly": amount_score,
            },
            "evidence": {
                "velocity": self._velocity_evidence(user_id),
                "split": self._split_evidence(user_id),
            },
        }

        if user_id:
            self._txn_log[user_id].append({
                "amount": float(txn.get("amount", 0)),
                "merchant_id": merchant_id,
                "timestamp": datetime.utcnow().isoformat(),
            })
            if len(self._txn_log[user_id]) > 200:
                self._txn_log[user_id] = self._txn_log[user_id][-200:]

        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content=response,
            correlation_id=message.message_id,
        )

    async def _handle_split_detect(self, message: AgentMessage) -> AgentMessage:
        user_id = message.content.get("user_id", "")
        window_minutes = message.content.get("window_minutes", 60)
        splits = self._detect_split_transactions(user_id, timedelta(minutes=window_minutes))
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content={
                "type": "SPLIT_DETECT_RESULT", "user_id": user_id,
                "split_groups": splits, "count": len(splits),
            },
            correlation_id=message.message_id,
        )

    def _velocity_analysis(self, user_id: str) -> float:
        recent = self._txn_log.get(user_id, [])
        if len(recent) < 3:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        recent_5min = [
            t for t in recent
            if datetime.fromisoformat(t["timestamp"]) > cutoff
        ]
        count = len(recent_5min)
        if count > 20:
            return 1.0
        return min(1.0, count / 20.0)

    def _split_analysis(self, user_id: str, txn: dict) -> float:
        amount = float(txn.get("amount", 0))
        recent = self._txn_log.get(user_id, [])
        cutoff = datetime.utcnow() - timedelta(minutes=60)
        nearby = [
            t for t in recent[-20:]
            if datetime.fromisoformat(t["timestamp"]) > cutoff
        ]
        total_nearby = sum(float(t.get("amount", 0)) for t in nearby)
        txn_count = len(nearby)
        if txn_count >= 3 and total_nearby > 10000:
            return min(1.0, (txn_count / 10.0 + total_nearby / 50000.0) / 2.0)
        return 0.0

    def _merchant_risk(self, merchant_id: str) -> float:
        high_risk = {"M5502", "M7721", "M3301"}
        if merchant_id in high_risk:
            return 0.8
        return 0.1

    def _amount_analysis(self, txn: dict) -> float:
        amount = float(txn.get("amount", 0))
        if amount > 100000:
            return 1.0
        roundness = abs(amount % 1000) < 1
        if amount > 50000 and roundness:
            return 0.6
        if roundness and amount > 10000:
            return 0.3
        return 0.0

    def _velocity_evidence(self, user_id: str) -> list[str]:
        recent = self._txn_log.get(user_id, [])
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        count = len([t for t in recent if datetime.fromisoformat(t["timestamp"]) > cutoff])
        if count > 10:
            return [f"{count} transactions in 5 minutes"]
        return []

    def _split_evidence(self, user_id: str) -> list[str]:
        groups = self._detect_split_transactions(user_id, timedelta(minutes=60))
        return [f"Split group: {len(g['txns'])} txns totaling {g['total']:.0f}" for g in groups]

    def _detect_split_transactions(self, user_id: str, window: timedelta) -> list[dict]:
        txns = self._txn_log.get(user_id, [])
        if len(txns) < 2:
            return []
        now = datetime.utcnow()
        recent = [t for t in txns if now - datetime.fromisoformat(t["timestamp"]) <= window]
        if len(recent) < 2:
            return []
        total = sum(float(t.get("amount", 0)) for t in recent)
        if total > 10000 and len(recent) >= 3:
            return [{"txns": recent, "total": total, "count": len(recent)}]
        return []
