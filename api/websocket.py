import asyncio
import json
import logging
import time
from typing import Any, Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_CONNECTIONS = 1000
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 60


class WebSocketManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._filters: dict[str, dict] = {}
        self._last_heartbeat: dict[str, float] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        if len(self._connections) >= MAX_CONNECTIONS:
            await websocket.close(code=1008, reason="max_connections_exceeded")
            return
        await websocket.accept()
        self._connections[client_id] = websocket
        self._last_heartbeat[client_id] = time.time()
        logger.info(f"WebSocket connected: {client_id} ({len(self._connections)} active)")

    async def disconnect(self, client_id: str):
        self._connections.pop(client_id, None)
        self._filters.pop(client_id, None)
        self._last_heartbeat.pop(client_id, None)
        logger.info(f"WebSocket disconnected: {client_id} ({len(self._connections)} active)")

    async def broadcast(self, message: dict, filter_fn: Callable | None = None):
        dead: list[str] = []
        for cid, ws in self._connections.items():
            if filter_fn and not filter_fn(cid):
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            await self.disconnect(cid)

    async def send_personal(self, client_id: str, message: dict):
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(client_id)

    def set_filter(self, client_id: str, alert_filter: dict):
        self._filters[client_id] = alert_filter

    def matches_filter(self, client_id: str, message: dict) -> bool:
        af = self._filters.get(client_id)
        if not af:
            return True
        fraud_type = message.get("fraud_type", "")
        probability = message.get("fraud_probability", 0)
        if af.get("fraud_types") and fraud_type not in af["fraud_types"]:
            return False
        if af.get("min_probability", 0) > probability:
            return False
        return True

    async def heartbeat_check(self):
        now = time.time()
        dead = []
        for cid, last in self._last_heartbeat.items():
            if now - last > HEARTBEAT_TIMEOUT:
                dead.append(cid)
        for cid in dead:
            ws = self._connections.get(cid)
            if ws:
                try:
                    await ws.close(code=1001, reason="heartbeat_timeout")
                except Exception:
                    pass
            await self.disconnect(cid)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = WebSocketManager()


class AlertBroadcaster:
    def __init__(self, redis=None):
        self.redis = redis

    async def listen_and_broadcast(self):
        if not self.redis:
            logger.warning("Redis not available; AlertBroadcaster disabled")
            return
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe("fraud_alerts")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(
                        data,
                        filter_fn=lambda cid: manager.matches_filter(cid, data),
                    )
                except Exception as e:
                    logger.error(f"AlertBroadcaster error: {e}")
        except Exception as e:
            logger.error(f"AlertBroadcaster failed: {e}")
