"""In-memory Redis fakes so the test suite runs with zero external services.

Implements the subset of the redis protocol used by the app hot path:
strings (get/set/setex/delete), lists (lpush/ltrim/lrange), sorted sets
(zadd/zremrangebyscore) and a transactional pipeline.

Used by integration and e2e tests via ``app.state.resources["redis"]``.
"""
# ruff: noqa: ARG002 -- stub methods mirror the redis-py interface

import json


def _pattern_match(pattern: str, key: str) -> bool:
    if pattern.endswith("*"):
        return key.startswith(pattern[:-1])
    return key == pattern


class FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def lpush(self, key, *values):
        self._ops.append(("lpush", key, values))
        return self

    def ltrim(self, key, start, stop):
        self._ops.append(("ltrim", key, start, stop))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    def zadd(self, key, mapping):
        self._ops.append(("zadd", key, mapping))
        return self

    def zremrangebyscore(self, key, min_, max_):
        self._ops.append(("zremrangebyscore", key, min_, max_))
        return self

    def zscore(self, key, member):
        self._ops.append(("zscore", key, member))
        return self

    def set(self, key, value):
        self._ops.append(("set", key, value))
        return self

    def setex(self, key, ttl, value):
        self._ops.append(("setex", key, ttl, value))
        return self

    def get(self, key):
        self._ops.append(("get", key))
        return self

    async def execute(self):
        store = self._store
        results = []
        for op in self._ops:
            cmd = op[0]
            key = op[1]
            if cmd == "lpush":
                values = op[2]
                store.lists[key] = list(values) + store.lists.get(key, [])
            elif cmd == "ltrim":
                start, stop = op[2], op[3]
                items = store.lists.get(key, [])
                store.lists[key] = items[start:None if stop == -1 else stop + 1]
            elif cmd == "expire":
                pass
            elif cmd == "zadd":
                mapping = op[2]
                zset = store.zsets.setdefault(key, {})
                for member, score in mapping.items():
                    zset[member] = score
            elif cmd == "zremrangebyscore":
                min_, max_ = op[2], op[3]
                zset = store.zsets.get(key, {})
                store.zsets[key] = {
                    m: s for m, s in zset.items() if not (min_ <= s <= max_)
                }
            elif cmd == "zscore":
                zset = store.zsets.get(key, {})
                results.append(zset.get(op[2]))
                continue
            elif cmd == "set":
                store.strings[key] = op[2]
            elif cmd == "setex":
                store.strings[key] = op[3]
            elif cmd == "get":
                results.append(store.strings.get(key))
                continue
            results.append(1)
        return results


class FakeRedisStore:
    def __init__(self):
        self.strings = {}
        self.lists = {}
        self.zsets = {}
        self.sets = {}
        self.hashes = {}


class FakeRedis:
    """Async redis client compatible with the app's hot-path usage."""

    def __init__(self):
        self._store = FakeRedisStore()

    async def get(self, key):
        return self._store.strings.get(key)

    async def set(self, key, value, ttl=None):
        self._store.strings[key] = value
        return True

    async def setex(self, key, ttl, value):
        self._store.strings[key] = value
        return True

    async def delete(self, key):
        self._store.strings.pop(key, None)
        return True

    async def lpush(self, key, *values):
        self._store.lists[key] = list(values) + self._store.lists.get(key, [])
        return len(self._store.lists[key])

    async def ltrim(self, key, start, stop):
        items = self._store.lists.get(key, [])
        self._store.lists[key] = items[start:None if stop == -1 else stop + 1]
        return True

    async def lrange(self, key, start, stop):
        items = self._store.lists.get(key, [])
        return items[start:None if stop == -1 else stop + 1]

    async def expire(self, key, ttl):
        return True

    async def zadd(self, key, mapping):
        zset = self._store.zsets.setdefault(key, {})
        zset.update(mapping)
        return len(zset)

    async def zremrangebyscore(self, key, min_, max_):
        zset = self._store.zsets.get(key, {})
        removed = {m for m, s in zset.items() if min_ <= s <= max_}
        for m in removed:
            del zset[m]
        return len(removed)

    async def zrangebyscore(self, key, min_, max_):
        zset = self._store.zsets.get(key, {})
        return sorted((m for m, s in zset.items() if min_ <= s <= max_), key=lambda m: zset[m])

    async def zrangebyscore_withscores(self, key, min_, max_):
        zset = self._store.zsets.get(key, {})
        return sorted(zset.items(), key=lambda kv: kv[1])

    async def zscore(self, key, member):
        zset = self._store.zsets.get(key, {})
        return zset.get(member)

    async def sadd(self, key, *members):
        self._store.sets.setdefault(key, set()).update(members)
        return len(self._store.sets[key])

    async def smembers(self, key):
        return set(self._store.sets.get(key, set()))

    async def hmset(self, key, mapping):
        self._store.hashes.setdefault(key, {}).update(mapping)
        return True

    async def hgetall(self, key):
        return dict(self._store.hashes.get(key, {}))

    async def exists(self, key):
        return (
            key in self._store.strings
            or key in self._store.lists
            or key in self._store.zsets
            or key in self._store.sets
            or key in self._store.hashes
        )

    async def zcount(self, key, min_, max_):
        zset = self._store.zsets.get(key, {})
        return sum(1 for s in zset.values() if min_ <= s <= max_)

    async def pfadd(self, key, *members):
        self._store.sets.setdefault(key, set()).update(members)
        return True

    async def pfcount(self, key):
        return len(self._store.sets.get(key, set()))

    async def keys(self, pattern):
        return [
            k
            for k in list(self._store.strings) + list(self._store.zsets) + list(self._store.sets)
            if _pattern_match(pattern, k)
        ]

    async def incr(self, key):
        self._store.strings[key] = str(int(self._store.strings.get(key, "0")) + 1)
        return int(self._store.strings[key])

    async def config_get(self, parameter):
        return {"maxmemory-policy": "allkeys-lru"}

    @property
    def _client(self):
        return self

    async def ping(self):
        return True

    async def pipeline(self):
        return FakePipeline(self._store)

    def seed_velocity(self, user_id, device, timestamps, amounts, merchants):
        """Pre-populate velocity keys for a user/device (used to trigger L1 rules)."""
        for i, ts in enumerate(timestamps):
            entry = json.dumps({
                "ts": ts,
                "amount": amounts[i],
                "merchant": merchants[i],
                "user": user_id,
                "device": device,
            })
            self._store.lists.setdefault(f"velocity:user:{user_id}", []).append(entry)
            self._store.lists.setdefault(f"velocity:dev:{device}", []).append(entry)


class FakeSyncRedis:
    """Sync redis client matching the subset used by Celery tasks."""

    def __init__(self):
        self._store = FakeRedisStore()

    def get(self, key):
        return self._store.strings.get(key)

    def set(self, key, value, ttl=None):
        self._store.strings[key] = value
        return True

    def setex(self, key, ttl, value):
        self._store.strings[key] = value
        return True
