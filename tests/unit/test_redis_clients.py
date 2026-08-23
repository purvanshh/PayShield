# ruff: noqa: ARG001, ARG002, ARG005 -- test doubles mirror the client interface


import pytest

from store.connection_pool import CircuitBreaker, CircuitBreakerState
from store.exceptions import RedisUnavailableError
from store.redis_client import AsyncRedisClient, create_redis
from store.sync_redis import SyncRedisClient


class FakeAsyncClient:
    def __init__(self):
        self.store = {"s": {}, "h": {}, "z": {}, "m": set()}
        self.fail = False

    async def ping(self):
        if self.fail:
            raise ConnectionError("down")
        return True

    async def get(self, key):
        if self.fail:
            raise ConnectionError("down")
        return self.store["s"].get(key)

    async def set(self, key, value):
        if self.fail:
            raise ConnectionError("down")
        self.store["s"][key] = value
        return True

    async def setex(self, key, ttl, value):
        if self.fail:
            raise ConnectionError("down")
        self.store["s"][key] = value
        return True

    async def delete(self, key):
        return self.store["s"].pop(key, None) is not None

    async def exists(self, key):
        return key in self.store["s"]

    async def hgetall(self, key):
        return dict(self.store["h"].get(key, {}))

    async def hset(self, name, *args, mapping=None):
        self.store["h"].setdefault(name, {})
        if mapping is not None:
            self.store["h"][name].update(mapping)
        elif len(args) == 2 and isinstance(args[1], str):
            self.store["h"][name][args[0]] = args[1]
        else:
            self.store["h"][name].update(args[0])
        return 1

    async def hincrby(self, name, key, amount=1):
        current = int(self.store["h"].setdefault(name, {}).get(key, 0)) + amount
        self.store["h"][name][key] = current
        return current

    async def expire(self, key, ttl):
        return True

    async def zadd(self, key, mapping):
        self.store["z"].setdefault(key, {}).update(mapping)
        return len(self.store["z"][key])

    async def zcount(self, key, lo, hi):
        return sum(1 for s in self.store["z"].get(key, {}).values() if lo <= s <= hi)

    async def zrangebyscore(self, key, lo, hi, withscores=False):
        items = [(m, s) for m, s in self.store["z"].get(key, {}).items() if lo <= s <= hi]
        if withscores:
            return items
        return [m for m, _ in items]

    async def zremrangebyscore(self, key, lo, hi):
        z = self.store["z"].get(key, {})
        removed = {m for m, s in z.items() if lo <= s <= hi}
        for m in removed:
            del z[m]
        return len(removed)

    async def sadd(self, key, *members):
        self.store["m"].update(members)
        return len(members)

    async def smembers(self, key):
        return set(self.store["m"])

    async def sinter(self, *keys):
        return set(self.store["m"])

    async def sunion(self, *keys):
        return set(self.store["m"])

    async def pfadd(self, key, *elements):
        self.store.setdefault("pf", {}).setdefault(key, set()).update(elements)
        return True

    async def pfcount(self, key):
        return len(self.store.get("pf", {}).get(key, set()))

    async def keys(self, pattern):
        return list(self.store["s"])

    async def lpush(self, key, *values):
        return len(values)

    async def ltrim(self, key, start, end):
        return True

    async def lrange(self, key, start, end):
        return []

    async def pipeline(self):
        return None


class FakePool:
    def __init__(self, client, circuit_breaker):
        self.client = client
        self.circuit_breaker = circuit_breaker

    async def close(self):
        pass


@pytest.fixture()
def pool():
    client = FakeAsyncClient()
    return FakePool(client, CircuitBreaker(failure_threshold=2, recovery_timeout=0.05))


@pytest.fixture()
def client(pool):
    return AsyncRedisClient(pool=pool)


@pytest.mark.asyncio
class TestAsyncRedisClient:
    async def test_basic_ops(self, client):
        assert await client.ping() is True
        assert await client.set("k", "v") is True
        assert await client.set("k2", "v2", ttl=30) is True
        assert await client.get("k") == "v"
        assert await client.exists("k") is True
        assert await client.delete("k") is True
        assert await client.get("k") is None
        await client.hset("h", "f", "1")
        await client.hmset("h2", {"a": "1", "b": "2"})
        assert await client.hgetall("h") == {"f": "1"}
        assert await client.hincrby("h", "f", 5) == 6
        await client.zadd("z", {"m1": 1.0, "m2": 2.0})
        assert await client.zcount("z", 0, 3) == 2
        assert await client.zrangebyscore("z", 0, 3) == ["m1", "m2"]
        assert await client.zrangebyscore_withscores("z", 0, 3) == [("m1", 1.0), ("m2", 2.0)]
        assert await client.zremrangebyscore("z", 0, 1) == 1
        await client.sadd("s", "a", "b")
        assert await client.smembers("s") == {"a", "b"}
        assert await client.sinter("s") == {"a", "b"}
        assert await client.sunion("s") == {"a", "b"}
        assert await client.expire("k2", 10) is True
        await client.pfadd("hll", "x", "y")
        assert await client.pfcount("hll") == 2
        await client.lpush("l", "v1")
        assert await client.ltrim("l", 0, 1) is True
        assert await client.lrange("l", 0, 1) == []
        await client.close()

    async def test_circuit_breaker_degrades(self, client, pool):
        pool.client.fail = True
        for _ in range(2):
            await client.get("k")
        assert pool.circuit_breaker.state == CircuitBreakerState.OPEN
        assert await client.get("k") is None
        assert await client.set("k", "v") is False
        assert await client.ping() is False
        assert await client.exists("k") is False
        assert await client.hgetall("k") == {}
        await client.hset("k", "f", "v")
        await client.hmset("k", {"a": "1"}, ttl=10)
        await client.zadd("z", {"m": 1})
        assert await client.zcount("z", 0, 1) == 0
        assert await client.zrangebyscore("z", 0, 1) == []
        assert await client.zrangebyscore_withscores("z", 0, 1) == []
        assert await client.zremrangebyscore("z", 0, 1) == 0
        await client.sadd("s", "a")
        assert await client.smembers("s") == set()
        assert await client.sinter("s") == set()
        assert await client.sunion("s") == set()
        assert await client.expire("k", 10) is False
        assert await client.hincrby("h", "f") == 0
        assert await client.pfadd("hll", "x") is False
        assert await client.pfcount("hll") == 0
        assert await client.keys("*") == []
        assert await client.lpush("l", "v") == 0
        assert await client.ltrim("l", 0, 1) is False
        assert await client.lrange("l", 0, 1) == []

    async def test_half_open_recovers(self, client, pool):
        pool.client.fail = True
        for _ in range(2):
            await client.get("k")
        pool.client.fail = False
        import time as time_module

        pool.circuit_breaker.last_failure_time = time_module.time() - 1
        assert await client.ping() is True
        assert pool.circuit_breaker.state == CircuitBreakerState.CLOSED

    async def test_fallback_cache_used(self, client, pool):
        assert await client.set("k", "stale-value") is True
        pool.client.fail = True
        for _ in range(2):
            await client.get("k")
        assert pool.circuit_breaker.state == CircuitBreakerState.OPEN
        key = pool.circuit_breaker._make_key(client.get, ("k",), {})
        pool.circuit_breaker.update_fallback_cache(key, "served-from-cache")
        assert await client.get("k") == "served-from-cache"


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_state_transitions(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.05)

        async def ok():
            return "ok"

        async def boom():
            raise ConnectionError("boom")

        assert await cb.call(ok) == "ok"
        for _ in range(3):
            with pytest.raises(RedisUnavailableError):
                await cb.call(boom)
        assert cb.state == CircuitBreakerState.OPEN

        import time as time_module

        cb.last_failure_time = time_module.time() - 1
        assert await cb.call(ok) == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_fallback_cache_eviction(self):
        cb = CircuitBreaker()
        for i in range(1005):
            key = f"key{i}"

            async def getter(k=key):
                raise ConnectionError("x")

            cb.update_fallback_cache(key, "v")
            cb._get_from_fallback(key)
        assert len(cb._fallback_cache) <= 1000
        cb._fallback_cache["expired"] = (0.0, "old")
        assert cb._get_from_fallback("expired") is None
        assert "expired" not in cb._fallback_cache

    def test_make_key(self):
        cb = CircuitBreaker()

        async def func(a, b=None):
            pass

        key1 = cb._make_key(func, (1,), {"b": 2})
        key2 = cb._make_key(func, (1,), {"b": 3})
        assert key1 != key2


class TestSyncRedisClient:
    @pytest.fixture(autouse=True)
    def _fake(self, monkeypatch):
        calls = []
        store = {"s": {}, "h": {}, "z": {}, "m": set(), "l": []}

        class FakeSync:
            def __init__(self, *a, **k):
                calls.append(k)

            def ping(self):
                return True

            def get(self, key):
                return store["s"].get(key)

            def set(self, key, value, **k):
                store["s"][key] = value
                return True

            def setex(self, key, ttl, value):
                store["s"][key] = value
                return True

            def delete(self, key):
                return store["s"].pop(key, None) is not None

            def exists(self, key):
                return key in store["s"]

            def hgetall(self, key):
                return dict(store["h"].get(key, {}))

            def hset(self, name, key, value):
                store["h"].setdefault(name, {})[key] = value
                return 1

            def hincrby(self, name, key, amount=1):
                current = int(store["h"].setdefault(name, {}).get(key, 0)) + amount
                store["h"][name][key] = current
                return current

            def expire(self, key, ttl):
                return True

            def zadd(self, key, mapping):
                store["z"].setdefault(key, {}).update(mapping)
                return len(store["z"][key])

            def zcount(self, key, lo, hi):
                return sum(1 for s in store["z"].get(key, {}).values() if lo <= s <= hi)

            def zrangebyscore(self, key, lo, hi, withscores=False):
                items = [(m, s) for m, s in store["z"].get(key, {}).items() if lo <= s <= hi]
                return items if withscores else [m for m, _ in items]

            def zremrangebyscore(self, key, lo, hi):
                z = store["z"].get(key, {})
                removed = {m for m, s in z.items() if lo <= s <= hi}
                for m in removed:
                    del z[m]
                return len(removed)

            def sadd(self, key, *members):
                store["m"].update(members)
                return 1

            def smembers(self, key):
                return set(store["m"])

            def keys(self, pattern):
                return list(store["s"])

            def lpush(self, key, *values):
                store["l"] = list(values) + store["l"]
                return len(values)

            def ltrim(self, key, start, end):
                return True

            def lrange(self, key, start, end):
                return store["l"]

            def pipeline(self):
                return object()

            def close(self):
                pass

        import store.sync_redis as sync_module

        monkeypatch.setattr(sync_module.sync_redis, "Redis", FakeSync)
        self.calls = calls

    def test_all_operations(self):
        client = SyncRedisClient(host="h", port=1, db=2)
        assert self.calls[0]["host"] == "h"
        assert client.ping() is True
        assert client.set("k", "v") is True
        assert client.set("k2", "v2", ttl=5) is True
        assert client.get("k") == "v"
        assert client.exists("k") is True
        assert client.delete("k") is True
        client.hset("h", "f", "1")
        assert client.hgetall("h") == {"f": "1"}
        assert client.hincrby("h", "f", 2) == 3
        assert client.expire("k2", 5) is True
        client.zadd("z", {"m": 1.0})
        assert client.zcount("z", 0, 2) == 1
        assert client.zrangebyscore("z", 0, 2) == ["m"]
        assert client.zrangebyscore_withscores("z", 0, 2) == [("m", 1.0)]
        assert client.zremrangebyscore("z", 0, 1) == 1
        client.sadd("s", "a")
        assert client.smembers("s") == {"a"}
        assert client.keys("*") == ["k2"]
        assert client.lpush("l", "v") == 1
        assert client.ltrim("l", 0, 1) is True
        assert client.lrange("l", 0, 1) == ["v"]
        client.close()

    def test_error_paths_return_defaults(self, monkeypatch):
        import store.sync_redis as sync_module

        class BrokenSync:
            def __init__(self, *a, **k):
                pass

            def ping(self):
                raise ConnectionError

            def get(self, key):
                raise ConnectionError

            def set(self, key, value, **k):
                raise ConnectionError

            def delete(self, key):
                raise ConnectionError

            def exists(self, key):
                raise ConnectionError

            def hgetall(self, key):
                raise ConnectionError

            def hset(self, *a):
                raise ConnectionError

            def hincrby(self, *a):
                raise ConnectionError

            def expire(self, *a):
                raise ConnectionError

            def zadd(self, *a):
                raise ConnectionError

            def zcount(self, *a):
                raise ConnectionError

            def zrangebyscore(self, *a):
                raise ConnectionError

            def zremrangebyscore(self, *a):
                raise ConnectionError

            def sadd(self, *a):
                raise ConnectionError

            def smembers(self, key):
                raise ConnectionError

            def keys(self, pattern):
                raise ConnectionError

            def lpush(self, *a):
                raise ConnectionError

            def ltrim(self, *a):
                raise ConnectionError

            def lrange(self, *a):
                raise ConnectionError

            def close(self):
                raise ConnectionError

        monkeypatch.setattr(sync_module.sync_redis, "Redis", BrokenSync)
        client = SyncRedisClient()
        assert client.ping() is False
        assert client.get("k") is None
        assert client.set("k", "v") is False
        assert client.delete("k") is False
        assert client.exists("k") is False
        assert client.hgetall("k") == {}
        client.hset("k", "f", "v")
        assert client.hincrby("h", "f") == 0
        assert client.expire("k", 1) is False
        client.zadd("z", {"m": 1})
        assert client.zcount("z", 0, 1) == 0
        assert client.zrangebyscore("z", 0, 1) == []
        assert client.zrangebyscore_withscores("z", 0, 1) == []
        assert client.zremrangebyscore("z", 0, 1) == 0
        client.sadd("s", "a")
        assert client.smembers("s") == set()
        assert client.keys("*") == []
        assert client.lpush("l", "v") == 0
        assert client.ltrim("l", 0, 1) is False
        assert client.lrange("l", 0, 1) == []
        client.close()


class TestCreateRedisFactory:
    def test_sync_mode(self, monkeypatch):
        from configs.config_loader import settings

        monkeypatch.setattr(settings.redis, "host", "testhost")
        client = create_redis("sync")
        assert isinstance(client, SyncRedisClient)
        assert client._client is not None

    def test_async_mode_default(self, monkeypatch):
        from configs.config_loader import settings

        monkeypatch.setattr(settings.redis, "host", "testhost")
        client = create_redis()
        assert isinstance(client, AsyncRedisClient)
        assert client.pool is not None
