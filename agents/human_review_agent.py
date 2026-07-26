import logging
from datetime import datetime, timedelta
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class HumanReviewAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="human_review_agent", agent_type="HUMAN_REVIEW"))
        self._feedback_log: list[dict] = []
        self._agent_accuracy: dict[str, list[bool]] = {}

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "ANALYST_FEEDBACK":
            return await self._handle_feedback(message)
        elif msg_type == "ESCALATION_REQUEST":
            return await self._handle_escalation(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_feedback(self, message: AgentMessage) -> AgentMessage:
        feedback = message.content.get("feedback", {})
        txn_id = feedback.get("txn_id", "")
        original = feedback.get("original_decision", "")
        analyst = feedback.get("analyst_decision", "")
        analyst_id = feedback.get("analyst_id", "")
        reason = feedback.get("reason", "")

        entry = {
            "feedback_id": f"fb_{datetime.utcnow().timestamp()}_{txn_id}",
            "txn_id": txn_id,
            "original_decision": original,
            "analyst_decision": analyst,
            "analyst_id": analyst_id,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat(),
            "correct": original == analyst,
        }
        self._feedback_log.append(entry)

        if entry["correct"]:
            for agent_type in self._agent_accuracy:
                self._agent_accuracy[agent_type].append(True)
        else:
            for agent_type in self._agent_accuracy:
                self._agent_accuracy[agent_type].append(False)

        await self.send_message(
            recipient="collective_agent", content={
                "type": "AGENT_FEEDBACK", "agent_type": message.content.get("agent_type", ""),
                "correct": original == analyst,
            }, message_type="EVENT",
        )

        logger.info(f"Feedback processed: {txn_id} {original} -> {analyst} by {analyst_id}")
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "feedback_processed", "feedback_id": entry["feedback_id"],
                     "correct": entry["correct"]},
            correlation_id=message.message_id,
        )

    async def _handle_escalation(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        escalation = {
            "escalation_id": f"esc_{datetime.utcnow().timestamp()}",
            "txn_id": content.get("txn_id", ""),
            "reason": content.get("reason", ""),
            "priority": content.get("priority", 3),
            "status": "PENDING",
            "created_at": datetime.utcnow().isoformat(),
        }
        logger.info(f"Escalation created: {escalation['escalation_id']} for {escalation['txn_id']}")
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "escalated", "escalation": escalation},
            correlation_id=message.message_id,
        )

    def get_accuracy(self, agent_type: str) -> float:
        results = self._agent_accuracy.get(agent_type, [])
        if not results:
            return 0.5
        return sum(results) / len(results)

    def get_recent_feedback(self, hours: int = 24) -> list[dict]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [f for f in self._feedback_log
                if datetime.fromisoformat(f["created_at"]) > cutoff]
