import logging
import time
from datetime import datetime
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 60
MAX_ERROR_RATE = 0.05
P99_LATENCY_THRESHOLD = 5.0


class MonitoringAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="monitoring_agent", agent_type="MONITORING"))
        self._heartbeats: dict[str, float] = {}
        self._metrics: dict[str, dict] = {}
        self._alerts: list[dict] = []

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "HEARTBEAT":
            return await self._handle_heartbeat(message)
        elif msg_type == "PERFORMANCE_REPORT":
            return await self._handle_performance(message)
        elif msg_type == "HEALTH_CHECK":
            return await self._handle_health_check(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_heartbeat(self, message: AgentMessage) -> AgentMessage:
        agent_id = message.sender
        now = time.time()
        self._heartbeats[agent_id] = now

        if agent_id not in self._metrics:
            self._metrics[agent_id] = {"latencies": [], "errors": 0, "total": 0}
        self._metrics[agent_id]["total"] += 1

        self._check_anomalies(agent_id)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ack", "timestamp": datetime.utcnow().isoformat()},
            correlation_id=message.message_id,
        )

    async def _handle_performance(self, message: AgentMessage) -> AgentMessage:
        agent_id = message.sender
        perf = message.content.get("metrics", {})
        latency = perf.get("latency_ms", 0)

        if agent_id not in self._metrics:
            self._metrics[agent_id] = {"latencies": [], "errors": 0, "total": 0}
        self._metrics[agent_id]["latencies"].append(latency)
        if len(self._metrics[agent_id]["latencies"]) > 100:
            self._metrics[agent_id]["latencies"] = self._metrics[agent_id]["latencies"][-100:]

        if perf.get("error", False):
            self._metrics[agent_id]["errors"] += 1

        self._check_anomalies(agent_id)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "recorded", "agent_id": agent_id},
            correlation_id=message.message_id,
        )

    async def _handle_health_check(self, message: AgentMessage) -> AgentMessage:
        agent_health = {}
        for agent_id in self._heartbeats:
            agent_health[agent_id] = self._check_agent_health(agent_id)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ok", "agents": agent_health, "alerts": self._alerts[-10:]},
            correlation_id=message.message_id,
        )

    def _check_agent_health(self, agent_id: str) -> dict:
        now = time.time()
        last_seen = self._heartbeats.get(agent_id, 0)
        metrics = self._metrics.get(agent_id, {})

        alive = (now - last_seen) < HEARTBEAT_TIMEOUT
        error_rate = metrics.get("errors", 0) / max(metrics.get("total", 1), 1)
        latencies = metrics.get("latencies", [])
        p99 = sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 10 else 0

        return {
            "agent_id": agent_id,
            "alive": alive,
            "last_seen": last_seen,
            "error_rate": round(error_rate, 4),
            "p99_latency_ms": round(p99, 2),
            "total_requests": metrics.get("total", 0),
        }

    def _check_anomalies(self, agent_id: str):
        health = self._check_agent_health(agent_id)
        alerts = []

        if not health["alive"]:
            alerts.append(f"Agent {agent_id} not responding for > {HEARTBEAT_TIMEOUT}s")
        if health["error_rate"] > MAX_ERROR_RATE:
            alerts.append(f"Agent {agent_id} error rate {health['error_rate']:.1%} > {MAX_ERROR_RATE:.0%}")
        if health["p99_latency_ms"] > P99_LATENCY_THRESHOLD:
            alerts.append(f"Agent {agent_id} p99 latency {health['p99_latency_ms']}ms > {P99_LATENCY_THRESHOLD}ms")

        for alert in alerts:
            entry = {
                "alert_id": f"alert_{datetime.utcnow().timestamp()}_{agent_id}",
                "agent_id": agent_id,
                "message": alert,
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "ALERT",
            }
            self._alerts.append(entry)
            logger.warning(f"SYSTEM_ALERT: {alert}")
