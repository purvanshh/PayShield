import logging
import re
from typing import Any

from agents.base import BaseAgent, AgentConfig
from agents.message import AgentMessage

logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self):
        self.is_valid = True
        self.violations: list[str] = []
        self.contradictions: list[dict] = []
        self.agent_id: str = ""

    def add_violation(self, message: str):
        self.violations.append(message)
        self.is_valid = False

    def add_contradiction(self, evidence_a: dict, evidence_b: dict, reason: str):
        self.contradictions.append({
            "evidence_a": evidence_a,
            "evidence_b": evidence_b,
            "reason": reason,
        })
        self.is_valid = False

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "violations": self.violations,
            "contradictions": self.contradictions,
        }


PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{16}\b"),
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    re.compile(r"\b\d{10}\b"),
]


class ValidationAgent(BaseAgent):
    VALID_DECISIONS = {"ALLOW", "BLOCK", "REVIEW"}

    def __init__(self, config: AgentConfig | None = None):
        if config is None:
            config = AgentConfig(agent_id="validation_agent", agent_type="VALIDATION", timeout_seconds=5)
        super().__init__(config)
        self._agent_failure_counts: dict[str, int] = {}
        self._total_validations = 0

    async def process(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        decision = content.get("decision", {})

        if message.message_type not in ("DECISION_ACTION", "COLLECTIVE_DECISION"):
            return AgentMessage(
                sender=self.config.agent_id,
                recipient=message.sender,
                message_type="ERROR",
                content={"error": f"Unexpected message type: {message.message_type}"},
                correlation_id=message.correlation_id,
            )

        result = self.validate(decision)

        if result.is_valid:
            return AgentMessage(
                sender=self.config.agent_id,
                recipient=message.sender,
                message_type="DECISION_VALIDATED",
                content={"decision": decision, "validation": result.to_dict()},
                correlation_id=message.correlation_id,
                priority=1,
            )
        else:
            sender_agent = decision.get("agent_id", message.sender)
            self._agent_failure_counts[sender_agent] = self._agent_failure_counts.get(sender_agent, 0) + 1

            logger.warning(f"ValidationAgent: BLOCKED decision from {sender_agent}: {result.violations}")

            escalation_msg = AgentMessage(
                sender=self.config.agent_id,
                recipient="human_review_agent",
                message_type="VALIDATION_FAILURE",
                content={
                    "decision": decision,
                    "validation_result": result.to_dict(),
                    "source_agent": sender_agent,
                },
                correlation_id=message.correlation_id,
                priority=1,
            )
            await self.send_message(
                recipient="human_review_agent",
                content=escalation_msg.content,
                message_type="VALIDATION_FAILURE",
                correlation_id=message.correlation_id or "",
                priority=1,
            )

            return AgentMessage(
                sender=self.config.agent_id,
                recipient=message.sender,
                message_type="VALIDATION_FAILURE",
                content={"error": "Decision blocked by validation", "validation": result.to_dict()},
                correlation_id=message.correlation_id,
                priority=1,
            )

    def validate(self, decision: dict) -> ValidationResult:
        self._total_validations += 1
        result = ValidationResult()
        result.agent_id = decision.get("agent_id", "unknown")

        action = decision.get("action", "")
        if action not in self.VALID_DECISIONS:
            result.add_violation(f"Invalid action '{action}'. Must be one of {self.VALID_DECISIONS}")

        confidence = decision.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                result.add_violation(f"Confidence must be numeric, got {type(confidence).__name__}")
            elif confidence < 0 or confidence > 1:
                result.add_violation(f"Confidence {confidence} outside [0, 1] range")

        if action == "BLOCK":
            evidence = decision.get("evidence", [])
            if len(evidence) < 2:
                result.add_violation(f"BLOCK decision requires minimum 2 evidence items, got {len(evidence)}")

        contradictions = self.check_contradictions(decision)
        for c in contradictions:
            result.add_contradiction(**c)

        decision_str = str(decision)
        for pattern in PII_PATTERNS:
            if pattern.search(decision_str):
                result.add_violation(f"PII detected in decision payload matching pattern: {pattern.pattern}")
                break

        return result

    def check_contradictions(self, decision: dict) -> list[dict]:
        contradictions = []
        evidence = decision.get("evidence", [])

        geo_info = None
        device_info = None
        for e in evidence:
            if e.get("type") == "geo_velocity":
                geo_info = e
            if e.get("type") == "device_fingerprint":
                device_info = e

        if geo_info and device_info:
            if geo_info.get("impossible_travel", False) and device_info.get("known_device", True):
                contradictions.append({
                    "evidence_a": geo_info,
                    "evidence_b": device_info,
                    "reason": "Geo-velocity suggests impossible travel but device fingerprint matches home device",
                })

        return contradictions

    def get_agent_failure_rate(self, agent_id: str) -> float:
        failures = self._agent_failure_counts.get(agent_id, 0)
        return failures / max(self._total_validations, 1)

    def get_flag_for_review_agents(self) -> list[str]:
        return [
            agent_id for agent_id, count in self._agent_failure_counts.items()
            if count > 0 and (count / max(self._total_validations, 1)) > 0.01
        ]
