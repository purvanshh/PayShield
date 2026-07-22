import json
import time


class FeatureStore:
    def __init__(self, redis_client):
        self.redis = redis_client

    def increment_velocity_counter(self, user_id: str, timestamp: float):
        key = f"velocity:{user_id}"
        self.redis.zadd(key, {str(timestamp): timestamp})
        self.redis.expire(key, 86400)

    def get_velocity_stats(self, user_id: str) -> dict:
        now = time.time()
        counts = {
            "txn_count_5min": self.redis.zcount(f"velocity:{user_id}", now - 300, now),
            "txn_count_1h": self.redis.zcount(f"velocity:{user_id}", now - 3600, now),
            "txn_count_24h": self.redis.zcount(f"velocity:{user_id}", now - 86400, now),
        }
        return counts

    def zcount(self, key: str, min_score: float, max_score: float) -> int:
        return self.redis.zcount(key, min_score, max_score)

    def set_user_baseline(self, user_id: str, baseline: dict):
        key = f"baseline:{user_id}"
        for k, v in baseline.items():
            self.redis.hset(key, k, str(v))
        self.redis.expire(key, 86400)

    def get_user_baseline(self, user_id: str) -> dict | None:
        key = f"baseline:{user_id}"
        raw = self.redis.hgetall(key)
        if not raw:
            return None
        return {k: float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v for k, v in raw.items()}

    def set_device_fingerprint(self, device_id: str, user_id: str):
        key = f"device:{device_id}"
        self.redis.hset(key, user_id, str(time.time()))
        self.redis.expire(key, 86400)

    def get_device_users(self, device_id: str) -> list[str]:
        key = f"device:{device_id}"
        return list(self.redis.hgetall(key).keys())

    def set_geospatial_cache(self, user_id: str, lat: float, lon: float, timestamp: float):
        key = f"geo:{user_id}"
        self.redis.hset(key, "lat", str(lat))
        self.redis.hset(key, "lon", str(lon))
        self.redis.hset(key, "timestamp", str(timestamp))
        self.redis.expire(key, 86400)

    def get_geospatial_cache(self, user_id: str) -> dict | None:
        key = f"geo:{user_id}"
        raw = self.redis.hgetall(key)
        if not raw:
            return None
        return {
            "lat": float(raw["lat"]),
            "lon": float(raw["lon"]),
            "timestamp": float(raw["timestamp"]),
        }

    def flush_user(self, user_id: str):
        self.redis.delete(f"velocity:{user_id}")
        self.redis.delete(f"baseline:{user_id}")
        self.redis.delete(f"geo:{user_id}")
