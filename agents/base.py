import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agents.message import AgentMessage, MessageRouter
from agents.state import AgentState

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    agent_id: str = ""
    agent_type: str = ""
    max_retries: int = 3
    timeout_seconds: int = 30
    heartbeat_interval: int = 15
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = AgentState.IDLE
        self.message_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._router: MessageRouter | None = None
        self._running = False

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentMessage:
        pass

    async def send_message(self, recipient: str, content: dict,
                           message_type: str = "EVENT", correlation_id: str = "",
                           priority: int = 3) -> None:
        if self._router is None:
            logger.warning("Agent not registered with router; message not sent")
            return
        msg = AgentMessage(
            sender=self.config.agent_id,
            recipient=recipient,
            message_type=message_type,
            content=content,
            correlation_id=correlation_id or None,
            priority=priority,
        )
        await self._router.route(msg)

    async def receive_message(self) -> AgentMessage:
        msg = await self.message_queue.get()
        self.message_queue.task_done()
        return msg

    async def start(self, router: MessageRouter):
        self._router = router
        self._running = True
        self.state = AgentState.IDLE
        logger.info(f"Agent {self.config.agent_id} ({self.config.agent_type}) started")

    async def stop(self):
        self._running = False
        self.state = AgentState.TERMINATED
        logger.info(f"Agent {self.config.agent_id} stopped")

    async def run(self):
        if not self._running:
            return
        self.state = AgentState.PROCESSING
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.receive_message(),
                    timeout=self.config.timeout_seconds,
                )
                self.state = AgentState.PROCESSING
                response = await self.process(msg)
                if response and self._router:
                    await self._router.route(response)
                self.state = AgentState.IDLE
            except asyncio.TimeoutError:
                self.state = AgentState.IDLE
            except Exception as exc:
                logger.error(f"Agent {self.config.agent_id} error: {exc}", exc_info=True)
                self.state = AgentState.ERROR

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    @property
    def agent_type(self) -> str:
        return self.config.agent_type
