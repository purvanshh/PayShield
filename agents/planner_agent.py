import logging
from typing import Any

from agents.base import BaseAgent, AgentConfig
from agents.message import AgentMessage, MessageType, MessagePriority

logger = logging.getLogger(__name__)


class InvestigationPlan:
    def __init__(self, transaction_id: str, strategies: list[dict]):
        self.transaction_id = transaction_id
        self.strategies = strategies
        self.selected_strategy: dict | None = None
        self.sub_tasks: list[dict] = []
        self.results: dict[str, Any] = {}

    def select_best_strategy(self):
        scored = sorted(
            self.strategies,
            key=lambda s: s.get("expected_information_gain", 0),
            reverse=True,
        )
        self.selected_strategy = scored[0] if scored else {}
        self.sub_tasks = self.selected_strategy.get("sub_tasks", [])

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "selected_strategy": self.selected_strategy,
            "sub_tasks": self.sub_tasks,
            "results": self.results,
        }


class PlannerAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        if config is None:
            config = AgentConfig(agent_id="planner_agent", agent_type="PLANNER", timeout_seconds=30)
        super().__init__(config)

    async def process(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        transaction = content.get("transaction", {})
        confidence = content.get("confidence", 0.0)
        txn_id = transaction.get("transaction_id", "unknown")

        if message.message_type != "COMPLEX_INVESTIGATION_REQUEST":
            return self._error_response(message, f"Unexpected message type: {message.message_type}")

        logger.info(f"PlannerAgent: decomposing investigation for {txn_id} (confidence={confidence})")

        plan = self.decompose_investigation(transaction, confidence)
        plan.select_best_strategy()

        await self._assign_sub_tasks(plan, message.correlation_id)

        return AgentMessage(
            sender=self.config.agent_id,
            recipient=message.sender,
            message_type="INVESTIGATION_PLAN",
            content=plan.to_dict(),
            correlation_id=message.correlation_id,
            priority=2,
        )

    def decompose_investigation(self, transaction: dict, confidence: float) -> InvestigationPlan:
        txn_id = transaction.get("transaction_id", "unknown")
        amount = transaction.get("amount", 0)
        user_id = transaction.get("user", {}).get("id", "")
        device_fp = transaction.get("device", {}).get("fingerprint", "")

        strategies = [
            {
                "name": "device_behavior_correlation",
                "description": "Verify device fingerprint history and correlate with user behavior",
                "expected_information_gain": 0.85,
                "sub_tasks": [
                    {"agent": "memory_agent", "action": "get_device_history", "params": {"device_fingerprint": device_fp}},
                    {"agent": "profile_agent", "action": "get_user_profile", "params": {"user_id": user_id}},
                ],
            },
            {
                "name": "merchant_temporal_analysis",
                "description": "Check merchant Benford deviation and time-based patterns",
                "expected_information_gain": 0.72,
                "sub_tasks": [
                    {"agent": "transaction_agent", "action": "analyze_merchant_patterns", "params": {"merchant_id": transaction.get("merchant", {}).get("id", "")}},
                    {"agent": "monitoring_agent", "action": "check_anomaly_scores", "params": {"transaction_id": txn_id}},
                ],
            },
            {
                "name": "network_social_graph",
                "description": "Analyze correlated transactions and network connections",
                "expected_information_gain": 0.78,
                "sub_tasks": [
                    {"agent": "collective_agent", "action": "find_correlated_txns", "params": {"transaction_id": txn_id, "window_hours": 1}},
                    {"agent": "memory_agent", "action": "find_similar_patterns", "params": {"features": transaction.get("features", {})}},
                ],
            },
        ]

        return InvestigationPlan(txn_id, strategies)

    async def _assign_sub_tasks(self, plan: InvestigationPlan, correlation_id: str | None):
        for task in plan.sub_tasks:
            agent_id = task["agent"]
            msg = AgentMessage(
                sender=self.config.agent_id,
                recipient=agent_id,
                message_type="REQUEST",
                content=task,
                correlation_id=correlation_id,
                priority=2,
            )
            await self.send_message(
                recipient=agent_id,
                content=task,
                message_type="REQUEST",
                correlation_id=correlation_id or "",
                priority=2,
            )
            logger.debug(f"PlannerAgent: assigned sub-task to {agent_id}: {task['action']}")

    def _error_response(self, message: AgentMessage, error: str) -> AgentMessage:
        return AgentMessage(
            sender=self.config.agent_id,
            recipient=message.sender,
            message_type="ERROR",
            content={"error": error},
            correlation_id=message.correlation_id,
        )
