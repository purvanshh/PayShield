import time

import pytest

from store.velocity import VelocityEngine, VelocityFeatureExtractor, VelocityFeatures


@pytest.fixture()
def redis():
    from tests.fake_redis import FakeRedis

    return FakeRedis()


@pytest.mark.asyncio
class TestVelocityEngine:
    async def test_record_and_read_features(self, redis):
        engine = VelocityEngine(redis)
        await engine.record_transaction(
            "U1", "T1", amount=100.0, merchant_id="M1", country="IN"
        )
        await engine.record_transaction(
            "U1", "T2", amount=200.0, merchant_id="M1", country="IN"
        )
        await engine.record_transaction(
            "U1", "T3", amount=300.0, merchant_id="M2", country="US"
        )

        features = await engine.get_velocity_features("U1")
        assert isinstance(features, VelocityFeatures)
        assert features.user_id == "U1"
        assert features.txn_count_1m == 3
        assert features.txn_count_5m == 3
        assert features.txn_count_1h == 3
        assert features.txn_count_24h == 3
        assert features.amount_total_1h == pytest.approx(600.0, abs=0.6)
        assert features.amount_avg_1h == pytest.approx(200.0, abs=0.25)
        assert features.distinct_merchants_1h == 2
        assert features.distinct_countries_1h == 2
        assert features.burst_score == pytest.approx(60.0, abs=0.1)
        assert features.window_remaining_ttl >= 0

    async def test_extractor_dict(self, redis):
        engine = VelocityEngine(redis)
        await engine.record_transaction("U2", "T9", amount=50.0)
        result = await VelocityFeatureExtractor(engine).extract("U2")
        assert result["txn_count_24h"] == 1
        assert result["amount_total_1h"] == pytest.approx(50.0, abs=0.6)
        assert result["burst_score"] > 0

    async def test_stale_members_trimmed(self, redis):
        engine = VelocityEngine(redis)
        old = time.time() - 100
        key = engine._key("U1", 60)
        await redis.zadd(key, {"txn:OLD": old})
        await redis.zadd(key, {"txn:NEW": time.time()})
        await engine.record_transaction("U1", "T-NEW", amount=1.0)
        members = await redis.zrangebyscore(key, 0, time.time())
        assert "txn:OLD" not in members

    async def test_cleanup_stale(self, redis):
        engine = VelocityEngine(redis)
        await redis.zadd(engine._key("U1", 60), {"txn:OLD": time.time() - 3600})
        await engine.cleanup_stale("U1")
        members = await redis.zrangebyscore(engine._key("U1", 60), 0, time.time())
        assert members == []

    async def test_score_roundtrip(self, redis):
        engine = VelocityEngine(redis)
        score = engine._score_for_member("T1", amount=123.45)
        epoch, amount = engine._parse_score(score)
        assert abs(epoch - time.time()) < 2
        assert amount == pytest.approx(123.45, abs=0.6)


class TestVelocityHelpers:
    def test_burst_score_zero_rate(self):
        engine = VelocityEngine(None)
        assert engine._compute_burst_score(VelocityFeatures(user_id="U1")) == 0.0

    def test_burst_score_single_window(self):
        engine = VelocityEngine(None)
        vf = VelocityFeatures(user_id="U1", txn_count_1m=10)
        assert engine._compute_burst_score(vf) == pytest.approx(20.0, abs=0.01)

    def test_key_and_ttl_helpers(self):
        engine = VelocityEngine(None)
        assert engine._key("U1", 300) == "vel:U1:300"
        assert engine._ttl(300) == 600
