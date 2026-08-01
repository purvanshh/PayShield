import logging
import time
from typing import Literal

from configs.config_loader import settings
from store.connection_pool import RedisConnectionPool
from store.exceptions import RedisUnavailableError
from store.sync_redis import SyncRedisClient

logger = logging.getLogger(__name__)


def create_redis(mode: Literal["async", "sync"] = "async", **kwargs):
    """Single factory for both Redis client flavours.

    `mode="async"` returns the circuit-breaker-wrapped :class:`AsyncRedisClient`
    for the API hot path; `mode="sync"` returns :class:`SyncRedisClient` for
    Celery workers and scripts. Connection defaults come from configs/config.yaml
    (env-overridable via PAYSHIELD_REDIS_*).
    """
    defaults = {
        "host": settings.redis.host,
        "port": settings.redis.port,
        "db": settings.redis.db,
    }
    if mode == "sync":
        return SyncRedisClient(**{**defaults, **kwargs})
    return AsyncRedisClient(**{**defaults, **kwargs})


class AsyncRedisClient:
    def __init__(self, pool: RedisConnectionPool | None = None, **kwargs):
        self.pool = pool or RedisConnectionPool(**kwargs)
        self._client = self.pool.client

    async def ping(self) -> bool:
        try:
            return await self.pool.circuit_breaker.call(self._client.ping)
        except RedisUnavailableError:
            return False

    async def get(self, key: str) -> str | None:
        try:
            return await self.pool.circuit_breaker.call(self._client.get, key)
        except RedisUnavailableError:
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        try:
            if ttl:
                result = await self.pool.circuit_breaker.call(self._client.setex, key, ttl, value)
            else:
                result = await self.pool.circuit_breaker.call(self._client.set, key, value)
            self.pool.circuit_breaker.update_fallback_cache(key, value)
            return result
        except RedisUnavailableError:
            return False

    async def delete(self, key: str) -> bool:
        try:
            return bool(await self.pool.circuit_breaker.call(self._client.delete, key))
        except RedisUnavailableError:
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.pool.circuit_breaker.call(self._client.exists, key))
        except RedisUnavailableError:
            return False

    async def hgetall(self, key: str) -> dict:
        try:
            return await self.pool.circuit_breaker.call(self._client.hgetall, key) or {}
        except RedisUnavailableError:
            return {}

    async def hset(self, name: str, key: str, value: str):
        try:
            await self.pool.circuit_breaker.call(self._client.hset, name, key, value)
        except RedisUnavailableError:
            pass

    async def hmset(self, name: str, mapping: dict, ttl: int | None = None):
        try:
            await self.pool.circuit_breaker.call(self._client.hset, name, mapping)
            if ttl:
                await self.pool.circuit_breaker.call(self._client.expire, name, ttl)
        except RedisUnavailableError:
            pass

    async def zadd(self, key: str, mapping: dict):
        try:
            await self.pool.circuit_breaker.call(self._client.zadd, key, mapping)
        except RedisUnavailableError:
            pass

    async def zcount(self, key: str, min_score: float, max_score: float) -> int:
        try:
            return await self.pool.circuit_breaker.call(self._client.zcount, key, min_score, max_score)
        except RedisUnavailableError:
            return 0

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        try:
            return await self.pool.circuit_breaker.call(self._client.zrangebyscore, key, min_score, max_score)
        except RedisUnavailableError:
            return []

    async def zrangebyscore_withscores(self, key: str, min_score: float, max_score: float) -> list[tuple[str, float]]:
        try:
            return await self.pool.circuit_breaker.call(
                self._client.zrangebyscore, key, min_score, max_score, withscores=True)
        except RedisUnavailableError:
            return []

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        try:
            return await self.pool.circuit_breaker.call(self._client.zremrangebyscore, key, min_score, max_score)
        except RedisUnavailableError:
            return 0

    async def sadd(self, key: str, *members):
        try:
            await self.pool.circuit_breaker.call(self._client.sadd, key, *members)
        except RedisUnavailableError:
            pass

    async def smembers(self, key: str) -> set:
        try:
            return await self.pool.circuit_breaker.call(self._client.smembers, key) or set()
        except RedisUnavailableError:
            return set()

    async def sinter(self, *keys: str) -> set:
        try:
            return await self.pool.circuit_breaker.call(self._client.sinter, *keys) or set()
        except RedisUnavailableError:
            return set()

    async def sunion(self, *keys: str) -> set:
        try:
            return await self.pool.circuit_breaker.call(self._client.sunion, *keys) or set()
        except RedisUnavailableError:
            return set()

    async def expire(self, key: str, ttl: int) -> bool:
        try:
            return await self.pool.circuit_breaker.call(self._client.expire, key, ttl)
        except RedisUnavailableError:
            return False

    async def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        try:
            return await self.pool.circuit_breaker.call(self._client.hincrby, name, key, amount)
        except RedisUnavailableError:
            return 0

    async def pfadd(self, key: str, *elements) -> bool:
        try:
            return bool(await self.pool.circuit_breaker.call(self._client.pfadd, key, *elements))
        except RedisUnavailableError:
            return False

    async def pfcount(self, key: str) -> int:
        try:
            return await self.pool.circuit_breaker.call(self._client.pfcount, key)
        except RedisUnavailableError:
            return 0

    async def keys(self, pattern: str) -> list[str]:
        try:
            return await self.pool.circuit_breaker.call(self._client.keys, pattern) or []
        except RedisUnavailableError:
            return []

    async def lpush(self, key: str, *values: str) -> int:
        try:
            return await self.pool.circuit_breaker.call(self._client.lpush, key, *values)
        except RedisUnavailableError:
            return 0

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        try:
            return await self.pool.circuit_breaker.call(self._client.ltrim, key, start, end)
        except RedisUnavailableError:
            return False

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        try:
            return await self.pool.circuit_breaker.call(self._client.lrange, key, start, end) or []
        except RedisUnavailableError:
            return []

    async def pipeline(self):
        return self._client.pipeline()

    async def close(self):
        await self.pool.close()
