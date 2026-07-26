import logging
from datetime import datetime
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "TRANSACTION": 0.35,
    "PROFILE": 0.25,
    "LAYER1": 0.20,
    "LAYER2": 0.20,
}

HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.50


class AgentAccuracyTracker:
    def __init__(self):
        self._accuracy: dict[str, list[bool]] = {}

    def record_outcome(self, agent_type: str, correct: bool):
        if agent_type not in self._accuracy:
            self._accuracy[agent_type] = []
        self._accuracy[agent_type].append(correct)
        if len(self._accuracy[agent_type]) > 100:
            self._accuracy[agent_type] = self._accuracy[agent_type][-100:]

    def get_precision(self, agent_type: str) -> float:
        results = self._accuracy.get(agent_type, [])
        if not results:
            return 0.5
        return sum(results) / len(results)

    def get_weight_adjustment(self, agent_type: str, base_weight: float) -> float:
        precision = self.get_precision(agent_type)
        adjustment = (precision - 0.5) * 0.2
        return round(max(0.05, min(0.5, base_weight + adjustment)), 4)


class CollectiveIntelligenceAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="collective_agent", agent_type="COLLECTIVE"))
        self._weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._tracker = AgentAccuracyTracker()

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "COLLECTIVE_ASSESSMENT_REQUEST":
            return await self._handle_assessment(message)
        elif msg_type == "AGENT_FEEDBACK":
            return await self._handle_feedback(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_assessment(self, message: AgentMessage) -> AgentMessage:
        signals = message.content.get("signals", {})
        weighted_prob = self._fuse_signals(signals)
        decision = "BLOCK" if weighted_prob >= HIGH_CONFIDENCE else "REVIEW" if weighted_prob >= MEDIUM_CONFIDENCE else "ALLOW"

        response = {
            "type": "COLLECTIVE_DECISION",
            "fraud_probability": round(weighted_prob, 4),
            "decision": decision,
            "weights": dict(self._weights),
            "signal_breakdown": signals,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_message(
            recipient="broadcast", content=response, message_type="EVENT",
            correlation_id=message.message_id,
        )
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content=response,
            correlation_id=message.message_id,
        )

    async def _handle_feedback(self, message: AgentMessage) -> AgentMessage:
        agent_type = message.content.get("agent_type", "")
        correct = message.content.get("correct", False)
        if agent_type:
            self._tracker.record_outcome(agent_type, correct)
            self._update_weights()
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "feedback_processed", "agent_type": agent_type, "weights": dict(self._weights)},
            correlation_id=message.message_id,
        )

    def _fuse_signals(self, signals: dict[str, Any]) -> float:
        weighted_sum = 0.0
        total_weight = 0.0
        for agent_type, base_weight in self._weights.items():
            signal = signals.get(agent_type, 0.0)
            if isinstance(signal, dict):
                signal = signal.get("risk_score", 0.0)
            adj_weight = self._tracker.get_weight_adjustment(agent_type, base_weight)
            weighted_sum += float(signal) * adj_weight
            total_weight += adj_weight
        if total_weight == 0:
            return 0.0
        return weighted_sum / total_weight

    def _update_weights(self):
        for agent_type in self._weights:
            self._weights[agent_type] = self._tracker.get_weight_adjustment(agent_type, DEFAULT_WEIGHTS[agent_type])
