"""Agent worker: runs the four live agents against the return-risk surface.

Owns the full agent lifecycle. On startup it:

1. builds a shared async Redis client (wired into every agent for
   heartbeats + live merchant lookups),
2. registers all four agents on a ``MessageRouter`` and starts their message
   loops,
3. runs a heartbeat loop renewing ``agent:heartbeat:{id}`` every 20s (the
   admin ``/agents/health`` endpoint reads these),
4. runs a feed loop that drains recent ``RETURN_RISK_SCORED`` audit entries
   into the transaction + profile agents,
5. periodically triggers the reflection agent over the same window.

Exit is clean on SIGTERM/SIGINT (cancels loops, stops agents, closes redis).
"""

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from agents.base import AgentConfig
from agents.human_review_agent import HumanReviewAgent
from agents.message import AgentMessage, MessageRouter, MessageType
from agents.profile_agent import ProfileAgent
from agents.reflection_agent import ReflectionAgent
from agents.transaction_agent import TransactionAnalysisAgent
from store.audit_log import AuditLogReader
from store.redis_client import create_redis

logger = logging.getLogger("agents.worker")

HEARTBEAT_INTERVAL_SECONDS = 20
FEED_INTERVAL_SECONDS = 15
REFLECTION_INTERVAL_SECONDS = 300
SCORED_EVENT = "RETURN_RISK_SCORED"

# Worker feed identity: registered on the router so agent responses route back.
WORKER_ID = "worker"


class AgentWorker:
    def __init__(self):
        self.redis = None
        self.router = MessageRouter()
        self.agents: list = []
        self._tasks: list[asyncio.Task] = []
        self._last_feed_entry: str | None = None

    async def start(self) -> None:
        self.redis = create_redis(mode="async")

        def _build(config: AgentConfig, cls: type):
            return cls(config) if config is not None else cls()

        agents = [
            _build(AgentConfig(agent_id="transaction_agent", agent_type="TRANSACTION"), TransactionAnalysisAgent),
            _build(AgentConfig(agent_id="profile_agent", agent_type="PROFILE"), ProfileAgent),
            _build(AgentConfig(agent_id="reflection_agent", agent_type="REFLECTION", timeout_seconds=120), ReflectionAgent),
            _build(AgentConfig(agent_id="human_review_agent", agent_type="HUMAN_REVIEW"), HumanReviewAgent),
        ]
        for agent in agents:
            agent._heartbeat_redis = self.redis
            self.router.register_agent(agent.agent_id, agent)
            await agent.start(self.router)
            self._tasks.append(asyncio.create_task(agent.run()))
            self.agents.append(agent)

        # Worker itself is an agent so responses from the others route back
        # to a live queue instead of being dropped.
        self.router.register_agent(WORKER_ID, self._response_collector())
        logger.info("agent_worker_started agents=%s", [a.agent_id for a in agents])

        self._tasks += [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._feed_loop()),
            asyncio.create_task(self._reflection_loop()),
        ]

    def _response_collector(self):
        class _Collector:
            message_queue: asyncio.Queue = asyncio.Queue()

            async def process(self, message: AgentMessage) -> None:
                await self.message_queue.put(message)

        return _Collector()

    async def _heartbeat_loop(self) -> None:
        while True:
            for agent in self.agents:
                await agent.touch_heartbeat()
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

    async def _feed_loop(self) -> None:
        """Drain newly scored orders from the audit chain into the agents."""
        while True:
            try:
                await self._dispatch_new_scored()
            except Exception as e:  # nosec B110 - feed must never crash the worker
                logger.warning("agent_feed_error: %s", e)
            await asyncio.sleep(FEED_INTERVAL_SECONDS)

    async def _dispatch_new_scored(self) -> None:
        entries = AuditLogReader().get_entries(event_type=SCORED_EVENT)
        if not entries:
            return
        # Feed only entries newer than the last dispatch (by entry timestamp).
        new_entries = []
        for entry in entries:
            ts = entry.get("timestamp", "")
            if self._last_feed_entry and ts and ts <= self._last_feed_entry:
                continue
            new_entries.append(entry)
        if not new_entries:
            return

        for entry in new_entries:
            payload = entry.get("payload", {})
            order = {
                "order_id": payload.get("order_id", ""),
                "merchant_id": payload.get("merchant_id", ""),
                "score": float(payload.get("score", 0.0) or 0.0),
                "tier": payload.get("tier", "LOW"),
                "amount": payload.get("amount", 0) or 0,
            }
            user_id = entry.get("actor", "")
            content = {"type": "RETURN_RISK_SCORED", "user_id": user_id, "order": order}
            await self.router.route(AgentMessage(sender=WORKER_ID, recipient="transaction_agent", content=content))
            await self.router.route(AgentMessage(sender=WORKER_ID, recipient="profile_agent", content=content))
            logger.info(
                "agent_feed_dispatched order=%s user=%s score=%.3f",
                order["order_id"], user_id, order["score"],
            )

        self._last_feed_entry = entries[-1].get("timestamp", "")

    async def _reflection_loop(self) -> None:
        while True:
            try:
                await self.router.route(
                    AgentMessage(
                        sender=WORKER_ID,
                        recipient="reflection_agent",
                        message_type=MessageType.TRIGGER_REFLECTION,
                        content={"period_hours": 24},
                    )
                )
                logger.info("agent_reflection_triggered")
            except Exception as e:  # nosec B110
                logger.warning("agent_reflection_error: %s", e)
            await asyncio.sleep(REFLECTION_INTERVAL_SECONDS)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # nosec B110 - shutdown best-effort
                pass
        for agent in self.agents:
            await agent.stop()
        if self.redis:
            await self.redis.close()
        logger.info("agent_worker_stopped")


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = AgentWorker()
    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await worker.start()
    logger.info("agent_worker_ready")
    await stop_event.wait()
    await worker.stop()


if __name__ == "__main__":
    asyncio.run(_main())