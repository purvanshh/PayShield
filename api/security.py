import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import redis as sync_redis
except ImportError:
    sync_redis = None


class RateLimiter:
    def __init__(self, redis_url: str | None = "redis://localhost:6379/0"):
        self._redis = None
        self._local_store: dict[str, list[float]] = {}
        if sync_redis and redis_url is not None:
            try:
                self._redis = sync_redis.from_url(redis_url, decode_responses=True)
            except Exception:
                pass

    def is_allowed(self, key: str, limit: int = 100, window_seconds: int = 60) -> bool:
        now = time.time()
        window_start = now - window_seconds

        if self._redis:
            try:
                pipeline = self._redis.pipeline()
                pipeline.zremrangebyscore(key, 0, window_start)
                pipeline.zadd(key, {str(now): now})
                pipeline.expire(key, window_seconds)
                pipeline.zcard(key)
                _, _, _, count = pipeline.execute()
                return count <= limit
            except Exception:
                pass

        timestamps = self._local_store.get(key, [])
        timestamps = [t for t in timestamps if t > window_start]
        timestamps.append(now)
        self._local_store[key] = timestamps
        return len(timestamps) <= limit

    def is_allowed_fixed_window(self, key: str, limit: int = 1000, window_seconds: int = 3600) -> bool:
        """Fixed-window counter (INCR + TTL on first hit).

        One Redis round trip per request; the counter window is set only on the
        first increment, so the key never needs a sliding-window cleanup.
        """
        if self._redis:
            try:
                count = self._redis.incr(key)
                if count == 1:
                    self._redis.expire(key, window_seconds)
                return count <= limit
            except Exception:
                pass

        now = time.time()
        window_start = now - window_seconds
        timestamps = [t for t in self._local_store.get(key, []) if t > window_start]
        timestamps.append(now)
        self._local_store[key] = timestamps
        return len(timestamps) <= limit

    def get_remaining(self, key: str, limit: int = 100, window_seconds: int = 60) -> int:
        now = time.time()
        window_start = now - window_seconds
        if self._redis:
            try:
                self._redis.zremrangebyscore(key, 0, window_start)
                count = self._redis.zcard(key) or 0
                return max(0, limit - count)
            except Exception:
                pass
        timestamps = [t for t in self._local_store.get(key, []) if t > window_start]
        return max(0, limit - len(timestamps))

    def reset(self, key: str):
        if self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._local_store.pop(key, None)


rate_limiter = RateLimiter()
