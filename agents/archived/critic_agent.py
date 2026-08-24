import logging
from typing import Any

from agents.base import BaseAgent, AgentConfig
from agents.message import AgentMessage

logger = logging.getLogger(__name__)


class CriticResult:
    def __init__(self, decision: dict):
        self.decision = decision
        self.challenges: list[dict] = []
        self.should_challenge = False
        self.confidence = decision.get("confidence", 0.0)
        self.action = decision.get("action", "")
        self.amount = decision.get("amount", 0)
        self.user_median = decision.get("user_median_amount", 0)
        self.user_vip = decision.get("user_vip", False)
        self.historical_fp_rate = decision.get("historical_fp_rate", 0.0)

    def add_challenge(self, reason: str, severity: str = "medium") -> dict:
        challenge = {"reason": reason, "severity": severity}
        self.challenges.append(challenge)
        self.should_challenge = True
        return challenge

    def to_dict(self) -> dict:
        return {
            "should_challenge": self.should_challenge,
            "challenges": self.challenges,
            "original_action": self.action,
            "recommended_action": "REVIEW" if self.should_challenge else self.action,
        }


class CriticAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        if config is None:
            config = AgentConfig(agent_id="critic_agent", agent_type="CRITIC", timeout_seconds=15)
        super().__init__(config)
        self._total_evaluations = 0
        self._correct_challenges = 0
        self._incorrect_challenges = 0
        self._aggression_threshold = 0.5

    async def process(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        decision = content.get("decision", {})

        if message.message_type not in ("COLLECTIVE_DECISION", "DECISION_OPINION"):
            return self._error_response(message, f"Unexpected message type: {message.message_type}")

        result = self.evaluate_decision(decision)
        challenge = None

        if result.should_challenge:
            challenge = self.challenge_decision(decision, result)
            logger.info(f"CriticAgent: challenging decision {decision.get('transaction_id', 'unknown')} "
                        f"({len(result.challenges)} reasons)")

        return AgentMessage(
            sender=self.config.agent_id,
            recipient=message.sender,
            message_type="DECISION_CHALLENGE" if challenge else "DECISION_CONFIRM",
            content=challenge or {"action": "confirm", "transaction_id": decision.get("transaction_id")},
            correlation_id=message.correlation_id,
            priority=1,
        )

    def evaluate_decision(self, decision: dict) -> CriticResult:
        self._total_evaluations += 1
        result = CriticResult(decision)

        if result.confidence < 0.80 and result.action == "BLOCK":
            result.add_challenge(
                f"Low confidence BLOCK: confidence={result.confidence:.2f} < 0.80",
                severity="high",
            )

        single_agent = decision.get("single_agent_dissent", False)
        if single_agent:
            result.add_challenge(
                "Single agent dissent in collective vote",
                severity="medium",
            )

        if result.historical_fp_rate > 0.10:
            result.add_challenge(
                f"Historical FP rate {result.historical_fp_rate:.1%} > 10% for this pattern",
                severity="high",
            )

        if result.amount > result.user_median * 20 and result.user_vip:
            result.add_challenge(
                f"Amount ${result.amount:.2f} > 20x user median ${result.user_median:.2f} "
                f"but user has VIP status",
                severity="medium",
            )

        if not result.should_challenge:
            self._correct_challenges += 1

        return result

    def challenge_decision(self, decision: dict, result: CriticResult) -> dict:
        return {
            "action": "challenge",
            "transaction_id": decision.get("transaction_id"),
            "confidence": result.confidence,
            "challenges": result.challenges,
            "recommended_action": "REVIEW",
            "requires_additional_evidence": True,
        }

    def record_challenge_outcome(self, was_correct: bool):
        if was_correct:
            self._correct_challenges += 1
            self._aggression_threshold = max(0.1, self._aggression_threshold - 0.05)
        else:
            self._incorrect_challenges += 1
            self._aggression_threshold = min(0.95, self._aggression_threshold + 0.05)
        logger.info(f"CriticAgent: accuracy={self.accuracy:.2f} aggression={self._aggression_threshold:.2f}")

    @property
    def accuracy(self) -> float:
        total = self._correct_challenges + self._incorrect_challenges
        return self._correct_challenges / max(total, 1)

    def _error_response(self, message: AgentMessage, error: str) -> AgentMessage:
        return AgentMessage(
            sender=self.config.agent_id,
            recipient=message.sender,
            message_type="ERROR",
            content={"error": error},
            correlation_id=message.correlation_id,
        )
