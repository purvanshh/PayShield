import logging
from datetime import datetime
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)

DUAL_CONFIRM_THRESHOLD = 0.95


class MitigationAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="mitigation_agent", agent_type="MITIGATION"))
        self._action_log: list[dict] = []
        self._pending_confirmations: dict[str, dict] = {}

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "COLLECTIVE_DECISION":
            return await self._handle_decision(message)
        elif msg_type == "ROLLBACK_REQUEST":
            return await self._handle_rollback(message)
        elif msg_type == "CONFIRM_ACTION":
            return await self._handle_confirmation(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_decision(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        decision = content.get("decision", "ALLOW")
        probability = content.get("fraud_probability", 0.0)
        target = content.get("target", message.sender)

        action = self._determine_action(decision, probability)
        action_id = f"act_{datetime.utcnow().timestamp()}_{target}"

        if action in ("BLOCK", "FREEZE") and probability < DUAL_CONFIRM_THRESHOLD:
            self._pending_confirmations[action_id] = {
                "action": action, "target": target, "reason": content.get("reasoning", ""),
                "initiated_by": message.sender, "confirmed_by": [],
            }
            status = "PENDING_CONFIRMATION"
        else:
            await self._execute_action(action, target, content)
            status = "EXECUTED"

        log_entry = {
            "action_id": action_id, "action_type": action, "target_id": target,
            "reason": content.get("reasoning", ""), "executed_by": self.config.agent_id,
            "executed_at": datetime.utcnow().isoformat(), "status": status,
        }
        self._action_log.append(log_entry)

        response = {
            "status": status, "action_id": action_id, "action": action,
            "target": target, "log": log_entry,
        }
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content=response,
            correlation_id=message.message_id,
        )

    async def _handle_rollback(self, message: AgentMessage) -> AgentMessage:
        action_id = message.content.get("action_id", "")
        admin = message.content.get("admin_id", "")
        reason = message.content.get("reason", "")

        if not admin:
            return AgentMessage(
                sender=self.config.agent_id, recipient=message.sender,
                message_type=MessageType.RESPONSE,
                content={"status": "rejected", "reason": "rollback requires admin approval"},
                correlation_id=message.message_id,
            )

        for entry in self._action_log:
            if entry["action_id"] == action_id and entry["status"] == "EXECUTED":
                entry["status"] = "ROLLED_BACK"
                entry["rollback_approved_by"] = admin
                entry["rollback_reason"] = reason
                return AgentMessage(
                    sender=self.config.agent_id, recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    content={"status": "rolled_back", "action_id": action_id},
                    correlation_id=message.message_id,
                )

        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "not_found", "action_id": action_id},
            correlation_id=message.message_id,
        )

    async def _handle_confirmation(self, message: AgentMessage) -> AgentMessage:
        action_id = message.content.get("action_id", "")
        confirmer = message.content.get("agent_id", "")

        pending = self._pending_confirmations.get(action_id)
        if not pending:
            return AgentMessage(
                sender=self.config.agent_id, recipient=message.sender,
                message_type=MessageType.RESPONSE,
                content={"status": "not_pending", "action_id": action_id},
                correlation_id=message.message_id,
            )

        if confirmer not in pending["confirmed_by"]:
            pending["confirmed_by"].append(confirmer)

        if len(pending["confirmed_by"]) >= 2:
            await self._execute_action(pending["action"], pending["target"], pending)
            for entry in self._action_log:
                if entry["action_id"] == action_id:
                    entry["status"] = "EXECUTED"
            del self._pending_confirmations[action_id]
            status = "confirmed_and_executed"
        else:
            status = "awaiting_confirmation"

        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": status, "action_id": action_id, "confirmations": len(pending["confirmed_by"])},
            correlation_id=message.message_id,
        )

    def _determine_action(self, decision: str, probability: float) -> str:
        if decision == "BLOCK":
            return "BLOCK"
        elif decision == "REVIEW":
            return "ALERT"
        elif probability > 0.9:
            return "FREEZE"
        return "NOTIFY"

    async def _execute_action(self, action: str, target: str, context: dict):
        logger.info(f"Executing {action} on {target}: {context.get('reason', '')[:100]}")
        return {"status": "executed", "action": action, "target": target}
