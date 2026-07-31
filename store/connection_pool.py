import logging
import os
import time
from functools import wraps

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._fallback_cache: dict[str, tuple[float, str]] = {}
        self._fallback_max_entries = 1000

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker state -> HALF_OPEN")
            else:
                key = self._make_key(func, args, kwargs)
                cached = self._get_from_fallback(key)
                if cached is not None:
                    return cached
                raise RedisUnavailableError("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker state -> CLOSED (recovered)")
            self.failure_count = 0
            return result
        except (ConnectionError, TimeoutError, OSError) as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(f"Circuit breaker state -> OPEN ({self.failure_count} failures)")
            key = self._make_key(func, args, kwargs)
            cached = self._get_from_fallback(key)
            if cached is not None:
                return cached
            raise RedisUnavailableError(f"Redis operation failed: {e}")

    def update_fallback_cache(self, key: str, value: str):
        if len(self._fallback_cache) >= self._fallback_max_entries:
            oldest = min(self._fallback_cache.items(), key=lambda x: x[1][0])
            del self._fallback_cache[oldest[0]]
        self._fallback_cache[key] = (time.time(), value)

    def _get_from_fallback(self, key: str):
        entry = self._fallback_cache.get(key)
        if entry:
            if time.time() - entry[0] < 60.0:
                return entry[1]
            del self._fallback_cache[key]
        return None

    def _make_key(self, func, args, kwargs):
        return f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"


class RedisConnectionPool:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int | None = None,
        password: str | None = None,
        max_connections: int = 50,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        health_check_interval: float = 30.0,
        retry_on_timeout: bool = True,
    ):
        host = host or os.getenv("REDIS_HOST", "localhost")
        port = port or int(os.getenv("REDIS_PORT", "6379"))
        db = db if db is not None else int(os.getenv("REDIS_DB", "0"))
        password = password or os.getenv("REDIS_PASSWORD") or None
        self.pool = aioredis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            health_check_interval=health_check_interval,
            retry_on_timeout=retry_on_timeout,
            decode_responses=True,
        )
        self.client = aioredis.Redis(connection_pool=self.pool)
        self.circuit_breaker = CircuitBreaker()

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def close(self):
        await self.client.close()
        await self.pool.disconnect()

    @property
    def active_connections(self) -> int:
        return self.pool._created_connections if hasattr(self.pool, "_created_connections") else 0
