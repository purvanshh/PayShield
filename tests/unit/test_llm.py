# ruff: noqa: ARG002 -- test doubles mirror the client interface


from llm.cache import LLMCache


class MockRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value


class TestLLMCache:
    def setup_method(self):
        self.redis = MockRedis()
        self.cache = LLMCache(self.redis, ttl=3600)

    def test_make_key_deterministic(self):
        e1 = {"a": 1, "b": 2}
        e2 = {"b": 2, "a": 1}
        assert self.cache._make_key(e1) == self.cache._make_key(e2)

    def test_make_key_different_inputs(self):
        e1 = {"a": 1}
        e2 = {"a": 2}
        assert self.cache._make_key(e1) != self.cache._make_key(e2)

    def test_cache_miss(self):
        assert self.cache.get({"test": "data"}) is None

    def test_cache_hit(self):
        evidence = {"key": "value"}
        self.cache.set(evidence, "test narrative")
        result = self.cache.get(evidence)
        assert result == "test narrative"
