import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class VelocityFeatures:
    user_id: str
    merchant_id: str | None = None
    txn_count_1m: int = 0
    txn_count_5m: int = 0
    txn_count_15m: int = 0
    txn_count_1h: int = 0
    txn_count_24h: int = 0
    amount_total_1h: float = 0.0
    amount_avg_1h: float = 0.0
    distinct_merchants_1h: int = 0
    distinct_countries_1h: int = 0
    burst_score: float = 0.0
    window_remaining_ttl: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VelocityEngine:
    VELOCITY_PREFIX = "vel"
    MEMBER_PREFIX = "txn"
    WINDOWS_SECONDS = [60, 300, 900, 3600, 86400]
    WINDOW_LABELS = ["1m", "5m", "15m", "1h", "24h"]

    def __init__(self, redis_client):
        self.redis = redis_client

    def _key(self, user_id: str, window_sec: int) -> str:
        return f"{self.VELOCITY_PREFIX}:{user_id}:{window_sec}"

    def _ttl(self, window_sec: int) -> int:
        return window_sec * 2

    def _score_for_member(self, txn_id: str, amount: float = 0.0) -> float:
        epoch = time.time()
        return epoch + amount * 1e-6

    def _parse_score(self, score: float) -> tuple[float, float]:
        epoch = math.floor(score)
        amount = round((score - epoch) * 1e6, 2)
        return epoch, amount

    async def record_transaction(
        self,
        user_id: str,
        txn_id: str,
        amount: float = 0.0,
        merchant_id: str | None = None,
        country: str | None = None,
    ):
        now = time.time()
        member = f"{self.MEMBER_PREFIX}:{txn_id}"
        score = self._score_for_member(txn_id, amount)

        for window_sec in self.WINDOWS_SECONDS:
            key = self._key(user_id, window_sec)
            await self.redis.zadd(key, {member: score})
            trim_before = now - window_sec
            await self.redis.zremrangebyscore(key, 0, trim_before)
            await self.redis.expire(key, self._ttl(window_sec))

        if merchant_id:
            merchant_key = f"{self.VELOCITY_PREFIX}:merchant:{user_id}:{merchant_id}"
            await self.redis.zadd(merchant_key, {member: now})
            await self.redis.expire(merchant_key, 3600)

        if country:
            country_key = f"{self.VELOCITY_PREFIX}:country:{user_id}:{country}"
            await self.redis.sadd(country_key, txn_id)
            await self.redis.expire(country_key, 3600)

    async def get_velocity_features(self, user_id: str) -> VelocityFeatures:
        now = time.time()
        features = VelocityFeatures(user_id=user_id)

        for window_sec, label in zip(self.WINDOWS_SECONDS, self.WINDOW_LABELS):
            key = self._key(user_id, window_sec)
            members = await self.redis.zrangebyscore(key, now - window_sec, now)
            scores = []

            for member in members:
                txn_id = member.replace(f"{self.MEMBER_PREFIX}:", "")
                score = await self._get_score(key, member)
                if score:
                    scores.append(score)

            count = len(members)

            if label == "1m":
                features.txn_count_1m = count
            elif label == "5m":
                features.txn_count_5m = count
            elif label == "15m":
                features.txn_count_15m = count
            elif label == "1h":
                features.txn_count_1h = count
            elif label == "24h":
                features.txn_count_24h = count

        features.amount_total_1h = await self._sum_amounts(user_id, 3600)
        features.amount_avg_1h = features.amount_total_1h / max(features.txn_count_1h, 1)

        merchant_pattern = f"{self.VELOCITY_PREFIX}:merchant:{user_id}:*"
        features.distinct_merchants_1h = len(await self._scan_keys(merchant_pattern))

        country_pattern = f"{self.VELOCITY_PREFIX}:country:{user_id}:*"
        features.distinct_countries_1h = len(await self._scan_keys(country_pattern))

        features.burst_score = self._compute_burst_score(features)
        features.window_remaining_ttl = max(0, 3600 - int(now % 3600))

        return features

    async def _get_score(self, key: str, member: str) -> float | None:
        try:
            pipe = await self.redis.pipeline()
            pipe.zscore(key, member)
            results = await pipe.execute()
            return results[0]
        except Exception:
            return None

    async def _sum_amounts(self, user_id: str, window_sec: int) -> float:
        key = self._key(user_id, window_sec)
        members = await self.redis.zrangebyscore(key, time.time() - window_sec, time.time())
        total = 0.0
        for member in members:
            score = await self._get_score(key, member)
            if score:
                _, amount = self._parse_score(score)
                total += amount
        return round(total, 2)

    async def _scan_keys(self, pattern: str) -> list[str]:
        try:
            keys = await self.redis._client.keys(pattern)
            return keys
        except Exception:
            return []

    def _compute_burst_score(self, vf: VelocityFeatures) -> float:
        rates = {
            "1m": vf.txn_count_1m,
            "5m": vf.txn_count_5m / 5,
            "15m": vf.txn_count_15m / 15,
            "1h": vf.txn_count_1h / 60,
        }
        max_rate = max(rates.values())
        min_rate = min(rates.values())
        if min_rate == 0:
            return max_rate * 2 if max_rate > 0 else 0.0
        return round(max_rate / min_rate, 2)

    async def cleanup_stale(self, user_id: str):
        for window_sec in self.WINDOWS_SECONDS:
            key = self._key(user_id, window_sec)
            await self.redis.zremrangebyscore(key, 0, time.time() - window_sec)


class VelocityFeatureExtractor:
    def __init__(self, engine: VelocityEngine):
        self.engine = engine

    async def extract(self, user_id: str) -> dict:
        features = await self.engine.get_velocity_features(user_id)
        return {
            "txn_count_1m": features.txn_count_1m,
            "txn_count_5m": features.txn_count_5m,
            "txn_count_15m": features.txn_count_15m,
            "txn_count_1h": features.txn_count_1h,
            "txn_count_24h": features.txn_count_24h,
            "amount_total_1h": features.amount_total_1h,
            "amount_avg_1h": features.amount_avg_1h,
            "distinct_merchants_1h": features.distinct_merchants_1h,
            "distinct_countries_1h": features.distinct_countries_1h,
            "burst_score": features.burst_score,
        }
