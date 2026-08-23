import json
import logging
import time
from typing import Any

import redis as sync_redis

logger = logging.getLogger(__name__)


class SyncRedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str | None = None, **kwargs):
        self._client = sync_redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_timeout=kwargs.get("socket_timeout", 2.0),
            socket_connect_timeout=kwargs.get("socket_connect_timeout", 2.0),
            **{k: v for k, v in kwargs.items() if k not in ("socket_timeout", "socket_connect_timeout")},
        )

    def ping(self) -> bool:
        try:
            return self._client.ping()
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        try:
            return self._client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        try:
            if ttl:
                return bool(self._client.setex(key, ttl, value))
            return bool(self._client.set(key, value))
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(key))
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def hgetall(self, key: str) -> dict:
        try:
            return self._client.hgetall(key) or {}
        except Exception:
            return {}

    def hset(self, name: str, key: str, value: str):
        try:
            self._client.hset(name, key, value)
        except Exception:
            pass

    def hmset(self, name: str, mapping: dict, ttl: int | None = None):
        try:
            self._client.hset(name, mapping=mapping)
            if ttl:
                self._client.expire(name, ttl)
        except Exception:
            pass

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        try:
            return self._client.hincrby(name, key, amount)
        except Exception:
            return 0

    def expire(self, key: str, ttl: int) -> bool:
        try:
            return bool(self._client.expire(key, ttl))
        except Exception:
            return False

    def zadd(self, key: str, mapping: dict):
        try:
            self._client.zadd(key, mapping)
        except Exception:
            pass

    def zcount(self, key: str, min_score: float, max_score: float) -> int:
        try:
            return self._client.zcount(key, min_score, max_score)
        except Exception:
            return 0

    def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        try:
            return self._client.zrangebyscore(key, min_score, max_score) or []
        except Exception:
            return []

    def zrangebyscore_withscores(self, key: str, min_score: float, max_score: float) -> list[tuple[str, float]]:
        try:
            return self._client.zrangebyscore(key, min_score, max_score, withscores=True) or []
        except Exception:
            return []

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        try:
            return self._client.zremrangebyscore(key, min_score, max_score)
        except Exception:
            return 0

    def sadd(self, key: str, *members):
        try:
            self._client.sadd(key, *members)
        except Exception:
            pass

    def smembers(self, key: str) -> set:
        try:
            return self._client.smembers(key) or set()
        except Exception:
            return set()

    def pipeline(self):
        return self._client.pipeline()

    def keys(self, pattern: str) -> list[str]:
        try:
            return self._client.keys(pattern) or []
        except Exception:
            return []

    def lpush(self, key: str, *values: str) -> int:
        try:
            return self._client.lpush(key, *values)
        except Exception:
            return 0

    def ltrim(self, key: str, start: int, end: int) -> bool:
        try:
            return bool(self._client.ltrim(key, start, end))
        except Exception:
            return False

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        try:
            return self._client.lrange(key, start, end) or []
        except Exception:
            return []

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
