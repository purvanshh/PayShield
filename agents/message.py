import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    EVENT = "EVENT"
    ALERT = "ALERT"
    COMPLEX_INVESTIGATION_REQUEST = "COMPLEX_INVESTIGATION_REQUEST"
    INVESTIGATION_PLAN = "INVESTIGATION_PLAN"
    DECISION_CHALLENGE = "DECISION_CHALLENGE"
    DECISION_CONFIRM = "DECISION_CONFIRM"
    DECISION_ACTION = "DECISION_ACTION"
    DECISION_OPINION = "DECISION_OPINION"
    DECISION_VALIDATED = "DECISION_VALIDATED"
    REFLECTION_REPORT = "REFLECTION_REPORT"
    TRIGGER_REFLECTION = "TRIGGER_REFLECTION"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"

    COLLECTIVE_DECISION = "COLLECTIVE_DECISION"


class MessagePriority:
    HIGHEST = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class AgentMessage:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    recipient: str = ""
    message_type: str = "EVENT"
    content: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: str | None = None
    priority: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            message_type=data.get("message_type", "EVENT"),
            content=data.get("content", {}),
            timestamp=data.get("timestamp", datetime.utcnow()),
            correlation_id=data.get("correlation_id"),
            priority=data.get("priority", 3),
        )


class MessageRouter:
    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._broadcast_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()

    def register_agent(self, agent_id: str, agent: Any):
        self._agents[agent_id] = agent
        logger.info(f"Agent {agent_id} registered with router")

    def unregister_agent(self, agent_id: str):
        self._agents.pop(agent_id, None)
        logger.info(f"Agent {agent_id} unregistered from router")

    async def route(self, message: AgentMessage):
        recipient = message.recipient
        if recipient == "broadcast":
            await self._broadcast(message)
        elif recipient in self._agents:
            agent = self._agents[recipient]
            await agent.message_queue.put(message)
            logger.debug(f"Message {message.message_id} routed to {recipient}")
        else:
            logger.warning(f"No agent found for recipient {recipient}")

    async def _broadcast(self, message: AgentMessage):
        for agent_id, agent in self._agents.items():
            if agent_id != message.sender:
                await agent.message_queue.put(message)
        logger.debug(f"Message {message.message_id} broadcast to {len(self._agents)} agents")
