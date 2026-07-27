from store.redis_client import AsyncRedisClient
from store.sync_redis import SyncRedisClient


def create_async_redis(**kwargs) -> AsyncRedisClient:
    return AsyncRedisClient(**kwargs)


def create_sync_redis(**kwargs) -> SyncRedisClient:
    return SyncRedisClient(**kwargs)
