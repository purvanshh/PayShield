import redis


class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.pool = redis.ConnectionPool(host=host, port=port, db=db)
        self.client = redis.Redis(connection_pool=self.pool)

    def get(self, key: str):
        pass

    def set(self, key: str, value, ttl: int | None = None):
        pass
