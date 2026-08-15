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
        return {
            k: float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
            for k, v in raw.items()
        }

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


class FeatureCache:
    """Redis-backed caches for GNN features that are expensive to recompute.

    - **Merchant round-amount share**: rolling HINCRBY counters (total txn
      count, round-amount count) refreshed on every scored transaction.
    - **User location centroid**: last known location, stored under the same
      ``velocity:loc:{user}`` key the scoring hot path maintains — the GNN's
      location-distance feature is measured against it.

    Every method is best-effort: cache failures return neutral defaults
    (0.0 / None) and must never block or fail a payment.
    """

    MERCHANT_STATS_KEY = "merchant:round_stats:{merchant_id}"
    CENTROID_KEY = "velocity:loc:{user_id}"
    TTL_SECONDS = 7 * 86400

    def __init__(self, redis_client):
        self.redis = redis_client

    async def record_merchant_amount(self, merchant_id: str, amount: float):
        try:
            key = self.MERCHANT_STATS_KEY.format(merchant_id=merchant_id)
            pipe = await self.redis.pipeline()
            pipe.hincrby(key, "total", 1)
            pipe.hincrby(key, "round", 1 if float(amount) % 100 == 0 else 0)
            pipe.expire(key, self.TTL_SECONDS)
            await pipe.execute()
        except Exception:
            pass

    async def merchant_round_share(self, merchant_id: str) -> float:
        try:
            key = self.MERCHANT_STATS_KEY.format(merchant_id=merchant_id)
            raw = await self.redis.hgetall(key)
            total = int(raw.get("total", 0))
            if total <= 0:
                return 0.0
            return round(int(raw.get("round", 0)) / total, 4)
        except Exception:
            return 0.0

    async def get_user_centroid(self, user_id: str) -> tuple[float, float] | None:
        try:
            raw = await self.redis.get(self.CENTROID_KEY.format(user_id=user_id))
            if not raw:
                return None
            data = json.loads(raw)
            return float(data["lat"]), float(data["lon"])
        except Exception:
            return None

    async def set_user_centroid(
        self, user_id: str, lat: float, lon: float, timestamp: float | None = None
    ):
        try:
            import time as _time

            key = self.CENTROID_KEY.format(user_id=user_id)
            await self.redis.set(
                key,
                json.dumps(
                    {
                        "lat": float(lat),
                        "lon": float(lon),
                        "ts": timestamp if timestamp is not None else _time.time(),
                    }
                ),
                ttl=self.TTL_SECONDS,
            )
        except Exception:
            pass
