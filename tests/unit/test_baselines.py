import json
import math

import pytest

from store.baselines import (
    BehavioralBaseline,
    BehavioralBaselineStore,
    BehavioralFeatureExtractor,
    DeviationFeatures,
    WelfordStats,
)


@pytest.fixture()
def redis():
    from tests.fake_redis import FakeRedis

    return FakeRedis()


class TestWelfordStats:
    def test_updates_and_stats(self):
        stats = WelfordStats()
        for v in [10.0, 20.0, 30.0, 40.0]:
            stats.update(v)
        assert stats.n == 4
        assert stats.mean == pytest.approx(25.0, abs=0.01)
        assert stats.min_val == 10.0
        assert stats.max_val == 40.0
        assert stats.variance > 0
        assert stats.std == pytest.approx(math.sqrt(500 / 3), abs=0.01)

    def test_z_score(self):
        stats = WelfordStats()
        assert stats.z_score(50.0) == 0.0  # n < 2
        for v in [10.0, 20.0, 30.0]:
            stats.update(v)
        assert stats.z_score(10.0) == pytest.approx(-1.0, abs=0.01)
        assert stats.z_score(30.0) == pytest.approx(1.0, abs=0.01)

    def test_zero_std_returns_zero(self):
        stats = WelfordStats()
        for _ in range(3):
            stats.update(5.0)
        assert stats.std == 0.0
        assert stats.z_score(9.0) == 0.0

    def test_roundtrip_dict(self):
        stats = WelfordStats()
        for v in [1.0, 2.0, 3.0]:
            stats.update(v)
        restored = WelfordStats.from_dict(stats.to_dict())
        assert restored.n == stats.n
        assert restored.mean == pytest.approx(stats.mean, abs=0.01)
        assert restored.std == pytest.approx(stats.std, abs=0.01)

    def test_from_dict_backcompat_std_only(self):
        stats = WelfordStats.from_dict({"n": 10, "mean": 5.0, "std": 2.0})
        assert stats.n == 10
        assert stats.m2 == pytest.approx(4.0 * 9, abs=0.01)


class TestBehavioralBaseline:
    def test_to_dict(self):
        baseline = BehavioralBaseline(
            user_id="U1",
            merchant_diversity=2.0,
            country_diversity=1.0,
            device_count=2,
            profile_version=3,
        )
        baseline.txn_amount_stats.update(100.0)
        data = baseline.to_dict()
        assert data["user_id"] == "U1"
        assert data["merchant_diversity"] == 2.0
        assert data["profile_version"] == 3
        assert data["txn_amount_stats"]["n"] == 1
        assert data["last_updated"].endswith("+00:00")


@pytest.mark.asyncio
class TestBehavioralBaselineStore:
    async def test_update_and_get_baseline(self, redis):
        store = BehavioralBaselineStore(redis)
        await store.update_baseline("U1", 100.0, "M1", "IN", device_id="D1")
        await store.update_baseline("U1", 200.0, "M2", "US", device_id="D2")
        await store.update_baseline("U1", 150.0, "M1", "IN", device_id="D1")

        baseline = await store.get_baseline("U1")
        assert baseline is not None
        assert baseline.user_id == "U1"
        assert baseline.txn_amount_stats.n == 3
        assert baseline.txn_amount_stats.mean == pytest.approx(150.0, abs=0.01)
        assert baseline.merchant_diversity == 2.0
        assert baseline.country_diversity == 2.0
        assert baseline.device_count == 2
        assert baseline.interarrival_seconds_stats.n == 2

        assert await store.get_baseline("NOPE") is None

    async def test_compute_deviation(self, redis):
        store = BehavioralBaselineStore(redis)
        deviation = await store.compute_deviation("U1", 100.0, "M1", "IN")
        assert isinstance(deviation, DeviationFeatures)
        assert deviation.amount_z_score == 0.0
        assert deviation.profile_version == 0

        await store.update_baseline("U1", 100.0, "M1", "IN")
        await store.update_baseline("U1", 100.0, "M1", "IN")
        await redis.pfadd(store._hll_merchant_key("U1"), "M2")
        await redis.pfadd(store._hll_country_key("U1"), "US")
        deviation = await store.compute_deviation("U1", 100.0, "M2", "US")
        assert deviation.amount_z_score == 0.0
        assert deviation.merchant_deviation == pytest.approx(1.0, abs=0.01)
        assert deviation.country_deviation == pytest.approx(1.0, abs=0.01)
        assert deviation.combined_anomaly_score > 0
        assert deviation.profile_version == 1

    async def test_extractor(self, redis):
        store = BehavioralBaselineStore(redis)
        extractor = BehavioralFeatureExtractor(store)
        result = await extractor.extract("U1", 500.0, "M1", "IN")
        assert set(result) == {
            "amount_z_score",
            "time_hour_z_score",
            "interarrival_z_score",
            "merchant_deviation",
            "country_deviation",
            "combined_anomaly_score",
        }
        assert isinstance(result["amount_z_score"], float)

    async def test_serialize_deserialize(self, redis):
        store = BehavioralBaselineStore(redis)
        baseline = BehavioralBaseline(user_id="U1")
        baseline.txn_amount_stats.update(42.0)
        raw = store._serialize(baseline)
        restored = store._deserialize(raw)
        assert restored.user_id == "U1"
        assert restored.txn_amount_stats.n == 1
        assert json.loads(raw)["user_id"] == "U1"
