class RedisUnavailableError(Exception):
    def __init__(self, message="Redis is unavailable or circuit breaker is open"):
        super().__init__(message)


class RedisTimeoutError(Exception):
    def __init__(self, message="Redis operation timed out"):
        super().__init__(message)


class RedisConnectionError(Exception):
    def __init__(self, message="Failed to connect to Redis"):
        super().__init__(message)
