import pytest

from store.feature_store import FeatureStore


class MockRedis:
    def __init__(self):
        self.data = {}
        self.hashes = {}
        self.expiry = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value
        if ttl:
            self.expiry[key] = ttl
        return True

    def delete(self, key):
        return bool(self.data.pop(key, None))

    def exists(self, key):
        return key in self.data

    def hset(self, name, key, value):
        self.hashes.setdefault(name, {})[key] = value

    def hget(self, name, key):
        return self.hashes.get(name, {}).get(key)

    def hgetall(self, name):
        return self.hashes.get(name, {}).copy()

    def zadd(self, name, mapping):
        pass

    def zcount(self, name, min_s, max_s):
        return 0

    def zremrangebyscore(self, name, min_s, max_s):
        return 0

    def expire(self, name, ttl):
        self.expiry[name] = ttl
        return True

    def pipeline(self):
        return self

    def execute(self):
        pass

    def ping(self):
        return True

    def close(self):
        pass


class TestFeatureStore:
    def setup_method(self):
        self.redis = MockRedis()
        self.store = FeatureStore(self.redis)

    def test_set_and_get_user_baseline(self):
        baseline = {"daily_avg_txn_count": 15.0, "daily_std_txn_count": 5.0, "median_amount": 500.0}
        self.store.set_user_baseline("U1", baseline)
        result = self.store.get_user_baseline("U1")
        assert result["daily_avg_txn_count"] == 15.0
        assert result["median_amount"] == 500.0

    def test_get_user_baseline_missing(self):
        result = self.store.get_user_baseline("nonexistent")
        assert result is None

    def test_set_device_fingerprint(self):
        self.store.set_device_fingerprint("D1", "U1")
        assert "U1" in self.redis.hashes.get("device:D1", {})

    def test_get_device_users(self):
        self.store.set_device_fingerprint("D1", "U1")
        self.store.set_device_fingerprint("D1", "U2")
        users = self.store.get_device_users("D1")
        assert len(users) == 2
        assert "U1" in users
        assert "U2" in users

    def test_set_and_get_geospatial_cache(self):
        self.store.set_geospatial_cache("U1", 19.0, 72.0, 1000.0)
        result = self.store.get_geospatial_cache("U1")
        assert result["lat"] == 19.0
        assert result["lon"] == 72.0
        assert result["timestamp"] == 1000.0

    def test_get_geospatial_cache_missing(self):
        result = self.store.get_geospatial_cache("nonexistent")
        assert result is None

    def test_flush_user(self):
        self.store.set_user_baseline("U1", {"daily_avg": 10})
        self.store.set_geospatial_cache("U1", 19.0, 72.0, 1000.0)
        self.store.flush_user("U1")
        assert self.store.get_user_baseline("U1") is None
        assert self.store.get_geospatial_cache("U1") is None

    def test_get_velocity_stats(self):
        stats = self.store.get_velocity_stats("U1")
        assert "txn_count_5min" in stats
        assert "txn_count_1h" in stats
        assert "txn_count_24h" in stats
