import json
import time

import redis


class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, max_connections: int = 20):
        self.pool = redis.ConnectionPool(
            host=host, port=port, db=db,
            max_connections=max_connections,
            decode_responses=True,
        )
        self.client = redis.Redis(connection_pool=self.pool)

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        if ttl:
            return bool(self.client.setex(key, ttl, value))
        return bool(self.client.set(key, value))

    def delete(self, key: str) -> bool:
        return bool(self.client.delete(key))

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(key))

    def hset(self, name: str, key: str, value: str):
        self.client.hset(name, key, value)

    def hget(self, name: str, key: str) -> str | None:
        return self.client.hget(name, key)

    def hgetall(self, name: str) -> dict:
        return self.client.hgetall(name) or {}

    def zadd(self, name: str, mapping: dict):
        self.client.zadd(name, mapping)

    def zcount(self, name: str, min_score: float, max_score: float) -> int:
        return self.client.zcount(name, min_score, max_score)

    def zremrangebyscore(self, name: str, min_score: float, max_score: float) -> int:
        return self.client.zremrangebyscore(name, min_score, max_score)

    def expire(self, name: str, ttl: int) -> bool:
        return bool(self.client.expire(name, ttl))

    def pipeline(self):
        return self.client.pipeline()

    def close(self):
        self.client.close()
        self.pool.disconnect()

    def health_check(self) -> bool:
        try:
            return self.client.ping()
        except redis.ConnectionError:
            return False
