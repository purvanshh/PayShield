import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class WelfordStats:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_val: float = float("inf")
    max_val: float = float("-inf")
    last_updated: float = 0.0

    @property
    def variance(self) -> float:
        return self.m2 / max(self.n - 1, 1)

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def update(self, value: float):
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self.m2 += delta * delta2
        if value < self.min_val:
            self.min_val = value
        if value > self.max_val:
            self.max_val = value
        self.last_updated = time.time()

    def z_score(self, value: float) -> float:
        if self.n < 2 or self.std == 0:
            return 0.0
        return round((value - self.mean) / self.std, 4)

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "min": round(self.min_val, 4),
            "max": round(self.max_val, 4),
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WelfordStats":
        ws = cls()
        ws.n = data.get("n", 0)
        ws.mean = data.get("mean", 0.0)
        ws.m2 = data.get("m2", 0.0) if "m2" in data else (data.get("std", 0) ** 2 * max(ws.n - 1, 1))
        ws.min_val = data.get("min", float("inf"))
        ws.max_val = data.get("max", float("-inf"))
        ws.last_updated = data.get("last_updated", 0.0)
        return ws


@dataclass
class BehavioralBaseline:
    user_id: str
    txn_amount_stats: WelfordStats = field(default_factory=WelfordStats)
    txn_time_hour_stats: WelfordStats = field(default_factory=WelfordStats)
    interarrival_seconds_stats: WelfordStats = field(default_factory=WelfordStats)
    merchant_diversity: float = 0.0
    country_diversity: float = 0.0
    device_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    profile_version: int = 1

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "txn_amount_stats": self.txn_amount_stats.to_dict(),
            "txn_time_hour_stats": self.txn_time_hour_stats.to_dict(),
            "interarrival_seconds_stats": self.interarrival_seconds_stats.to_dict(),
            "merchant_diversity": self.merchant_diversity,
            "country_diversity": self.country_diversity,
            "device_count": self.device_count,
            "last_updated": self.last_updated.isoformat(),
            "profile_version": self.profile_version,
        }


@dataclass
class DeviationFeatures:
    user_id: str
    amount_z_score: float = 0.0
    time_z_score: float = 0.0
    interarrival_z_score: float = 0.0
    merchant_deviation: float = 0.0
    country_deviation: float = 0.0
    combined_anomaly_score: float = 0.0
    profile_version: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BehavioralBaselineStore:
    BASELINE_PREFIX = "bl"
    HLL_PREFIX = "hll"

    def __init__(self, redis_client):
        self.redis = redis_client

    def _baseline_key(self, user_id: str) -> str:
        return f"{self.BASELINE_PREFIX}:{user_id}"

    def _hll_merchant_key(self, user_id: str) -> str:
        return f"{self.HLL_PREFIX}:merchant:{user_id}"

    def _hll_country_key(self, user_id: str) -> str:
        return f"{self.HLL_PREFIX}:country:{user_id}"

    async def update_baseline(self, user_id: str, amount: float, merchant_id: str, country: str, device_id: str | None = None):
        key = self._baseline_key(user_id)
        raw = await self.redis.get(key)
        if raw:
            baseline = self._deserialize(raw)
        else:
            baseline = BehavioralBaseline(user_id=user_id)

        baseline.txn_amount_stats.update(amount)
        hour = datetime.now(timezone.utc).hour
        baseline.txn_time_hour_stats.update(float(hour))

        if baseline.txn_amount_stats.n > 1:
            prev_time = baseline.last_updated.timestamp()
            interarrival = time.time() - prev_time
            if interarrival > 0:
                baseline.interarrival_seconds_stats.update(interarrival)

        await self.redis.pfadd(self._hll_merchant_key(user_id), merchant_id)
        await self.redis.pfadd(self._hll_country_key(user_id), country)

        merchant_count = await self.redis.pfcount(self._hll_merchant_key(user_id))
        country_count = await self.redis.pfcount(self._hll_country_key(user_id))
        baseline.merchant_diversity = float(merchant_count)
        baseline.country_diversity = float(country_count)
        baseline.last_updated = datetime.now(timezone.utc)

        await self.redis.set(key, self._serialize(baseline))

        if device_id and device_id not in await self._get_seen_devices(user_id):
            await self._record_device(user_id, device_id)

        baseline.device_count = len(await self._get_seen_devices(user_id))
        await self.redis.set(key, self._serialize(baseline))

    async def get_baseline(self, user_id: str) -> BehavioralBaseline | None:
        raw = await self.redis.get(self._baseline_key(user_id))
        if not raw:
            return None
        return self._deserialize(raw)

    async def compute_deviation(self, user_id: str, amount: float, merchant_id: str, country: str) -> DeviationFeatures:
        baseline = await self.get_baseline(user_id)
        features = DeviationFeatures(user_id=user_id)

        if baseline is None:
            return features

        features.amount_z_score = baseline.txn_amount_stats.z_score(amount)

        hour = float(datetime.now(timezone.utc).hour)
        features.time_z_score = baseline.txn_time_hour_stats.z_score(hour)

        interarrival = 0.0
        if baseline.interarrival_seconds_stats.n > 0:
            interarrival = time.time() - baseline.last_updated.timestamp()
            features.interarrival_z_score = baseline.interarrival_seconds_stats.z_score(interarrival)

        merchant_count = await self.redis.pfcount(self._hll_merchant_key(user_id))
        country_count = await self.redis.pfcount(self._hll_country_key(user_id))

        if baseline.merchant_diversity > 0:
            features.merchant_deviation = abs(merchant_count - baseline.merchant_diversity) / baseline.merchant_diversity
        if baseline.country_diversity > 0:
            features.country_deviation = abs(country_count - baseline.country_diversity) / baseline.country_diversity

        features.combined_anomaly_score = self._compute_combined_score(features)
        features.profile_version = baseline.profile_version

        return features

    def _compute_combined_score(self, dev: DeviationFeatures) -> float:
        scores = [
            abs(dev.amount_z_score) * 0.35,
            abs(dev.time_z_score) * 0.15,
            abs(dev.interarrival_z_score) * 0.20,
            dev.merchant_deviation * 0.15,
            dev.country_deviation * 0.15,
        ]
        return round(min(sum(scores) / 0.35, 1.0), 4)

    def _serialize(self, baseline: BehavioralBaseline) -> str:
        return json.dumps(baseline.to_dict())

    def _deserialize(self, raw: str) -> BehavioralBaseline:
        data = json.loads(raw)
        baseline = BehavioralBaseline(user_id=data["user_id"])
        baseline.txn_amount_stats = WelfordStats.from_dict(data["txn_amount_stats"])
        baseline.txn_time_hour_stats = WelfordStats.from_dict(data["txn_time_hour_stats"])
        baseline.interarrival_seconds_stats = WelfordStats.from_dict(data["interarrival_seconds_stats"])
        baseline.merchant_diversity = data.get("merchant_diversity", 0.0)
        baseline.country_diversity = data.get("country_diversity", 0.0)
        baseline.device_count = data.get("device_count", 0)
        baseline.profile_version = data.get("profile_version", 1)
        if data.get("last_updated"):
            baseline.last_updated = datetime.fromisoformat(data["last_updated"])
        return baseline

    async def _get_seen_devices(self, user_id: str) -> set:
        return await self.redis.smembers(f"user_devices:{user_id}")

    async def _record_device(self, user_id: str, device_id: str):
        await self.redis.sadd(f"user_devices:{user_id}", device_id)


class BehavioralFeatureExtractor:
    def __init__(self, store: BehavioralBaselineStore):
        self.store = store

    async def extract(self, user_id: str, amount: float, merchant_id: str, country: str) -> dict:
        await self.store.update_baseline(user_id, amount, merchant_id, country)
        deviation = await self.store.compute_deviation(user_id, amount, merchant_id, country)
        return {
            "amount_z_score": deviation.amount_z_score,
            "time_hour_z_score": deviation.time_z_score,
            "interarrival_z_score": deviation.interarrival_z_score,
            "merchant_deviation": deviation.merchant_deviation,
            "country_deviation": deviation.country_deviation,
            "combined_anomaly_score": deviation.combined_anomaly_score,
        }
