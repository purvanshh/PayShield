"""Compatibility shim for the pre-scope-cut import path.

Several seeders and scripts import ``create_sync_redis`` from
``infrastructure.redis_bridge``. That package was removed in the repo scoping
commit; the live factory now lives in ``store.redis_client``. This shim keeps
the old import path working without editing every script — it delegates to
``store.redis_client.create_redis(mode="sync")``.
"""

from store.redis_client import create_redis


def create_sync_redis(**kwargs):
    """Return a synchronous Redis client (delegates to store.redis_client)."""
    return create_redis(mode="sync", **kwargs)


__all__ = ["create_sync_redis"]
