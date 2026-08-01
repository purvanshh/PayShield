"""Backwards-compatible bridge to the consolidated Redis factory.

New code should call :func:`store.redis_client.create_redis` directly with
``mode="async"`` or ``mode="sync"``.
"""

from typing import Optional

from store.redis_client import AsyncRedisClient, SyncRedisClient, create_redis


def create_async_redis(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs,
) -> AsyncRedisClient:
    return create_redis(mode="async", host=host, port=port, db=db, password=password, **kwargs)


def create_sync_redis(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs,
) -> SyncRedisClient:
    return create_redis(mode="sync", host=host, port=port, db=db, password=password, **kwargs)
