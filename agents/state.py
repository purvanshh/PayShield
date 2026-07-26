import json
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    _has_redis = True
except ImportError:
    aioredis = None
    _has_redis = False


class AgentState(str, Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    WAITING = "WAITING"
    ERROR = "ERROR"
    TERMINATED = "TERMINATED"


class OrchestratorState:
    def __init__(self, redis_url: str = "redis://localhost:6379/1"):
        self.redis_url = redis_url
        self._redis = None
        self._local_store: dict[str, tuple[Any, float]] = {}

    async def _get_redis(self):
        if not _has_redis:
            return None
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def get_state(self, key: str) -> dict[str, Any]:
        r = await self._get_redis()
        if r is not None:
            try:
                val = await r.get(key)
                if val:
                    return json.loads(val)
            except Exception:
                pass
        entry = self._local_store.get(key)
        if entry:
            value, expiry = entry
            if expiry == 0 or time.time() < expiry:
                return value
            else:
                del self._local_store[key]
        return {}

    async def set_state(self, key: str, value: dict[str, Any], ttl: int = 300):
        r = await self._get_redis()
        if r is not None:
            try:
                await r.setex(key, ttl, json.dumps(value))
                return
            except Exception:
                pass
        expiry = (time.time() + ttl) if ttl > 0 else 0
        self._local_store[key] = (value, expiry)

    async def delete_state(self, key: str):
        r = await self._get_redis()
        if r is not None:
            try:
                await r.delete(key)
            except Exception:
                pass
        self._local_store.pop(key, None)

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None
