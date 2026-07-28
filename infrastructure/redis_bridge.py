import os
from typing import Optional

from store.redis_client import AsyncRedisClient
from store.sync_redis import SyncRedisClient


def create_async_redis(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs,
) -> AsyncRedisClient:
    return AsyncRedisClient(
        host=host or os.getenv("REDIS_HOST", "localhost"),
        port=port or int(os.getenv("REDIS_PORT", "6379")),
        db=db or int(os.getenv("REDIS_DB", "0")),
        password=password or os.getenv("REDIS_PASSWORD") or None,
        **kwargs,
    )


def create_sync_redis(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs,
) -> SyncRedisClient:
    return SyncRedisClient(
        host=host or os.getenv("REDIS_HOST", "localhost"),
        port=port or int(os.getenv("REDIS_PORT", "6379")),
        db=db or int(os.getenv("REDIS_DB", "0")),
        password=password or os.getenv("REDIS_PASSWORD") or None,
        **kwargs,
    )
