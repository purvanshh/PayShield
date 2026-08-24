"""ReturnRiskFeatureEngine tests (Phase 13)."""

import json
import math
from datetime import datetime
from decimal import Decimal

from return_risk.feature_engine import CATEGORY_BASELINES, DEFAULT_PRIOR, ReturnRiskFeatureEngine
from tests.fake_redis import FakeRedis

NOW = datetime(2026, 8, 21, 12, 0, 0)


class TestFeatureEngine:
    def setup_method(self):
        self.redis = FakeRedis()
        self.engine = ReturnRiskFeatureEngine(self.redis)

    async def test_new_user_gets_prior_defaults(self):
        features = await self.engine.extract_features(
            user_id="U_NEW", merchant_id="M_A", category="fashion",
            amount=Decimal("10000"), cod_flag=True, timestamp=NOW,
        )
        assert features["user_is_new"]["value"] is True
        assert features["user_total_orders"]["value"] == 0
        assert features["user_return_rate_30d"]["source"] == "default_new_user"
        # new users default to the population prior, not zero
        assert features["user_return_rate_30d"]["value"] == DEFAULT_PRIOR
        assert features["user_return_rate_lifetime"]["value"] == DEFAULT_PRIOR
        assert features["txn_category_return_baseline"]["value"] == CATEGORY_BASELINES["fashion"]
        # log-normalised amount risk: ₹10k is 0.85, not saturated
        expected = round(math.log1p(10000) / math.log1p(50000), 4)
        assert features["txn_amount_risk"]["value"] == expected
        assert features["txn_cod_flag"]["value"] is True
        assert features["txn_time_of_day_risk"]["value"] == 0.0

    async def test_high_aov_no_longer_saturates_linearly(self):
        low = await self.engine.extract_features(
            user_id="U_A", merchant_id="M_A", category="electronics",
            amount=Decimal("5000"), cod_flag=False, timestamp=NOW,
        )
        high = await self.engine.extract_features(
            user_id="U_A", merchant_id="M_A", category="electronics",
            amount=Decimal("45000"), cod_flag=False, timestamp=NOW,
        )
        # both orders stay strictly inside (0,1) and are separated
        low_risk, high_risk = low["txn_amount_risk"]["value"], high["txn_amount_risk"]["value"]
        assert 0.0 < low_risk < high_risk < 1.0

    async def test_user_features_from_redis_hash(self):
        await self.redis.hmset(
            "return_risk:user:U001",
            {
                "total_orders": "10",
                "total_returns": "6",
                "return_rate_30d": "0.62",
                "return_rate_90d": "0.55",
                "avg_return_value": "3800.5",
                "cod_refusals": "4",
                "cod_orders": "8",
                "return_reason_distribution": json.dumps({"SIZE_ISSUE": 4, "CHANGED_MIND": 2}),
            },
        )
        features = await self.engine.extract_features(
            user_id="U001", merchant_id="M001", category="fashion",
            amount=Decimal("2000"), cod_flag=False, timestamp=NOW,
        )
        assert features["user_return_rate_30d"]["value"] == 0.62
        assert features["user_total_orders"]["value"] == 10
        assert features["user_return_rate_lifetime"]["value"] == 0.6  # 6/10 computed
        assert features["user_serial_returner_flag"]["value"] is True
        assert features["user_cod_refusal_rate"]["value"] == 0.5
        assert features["user_return_reason_distribution"]["value"]["SIZE_ISSUE"] == 4
        assert features["user_is_new"]["value"] is False

    async def test_return_velocity_from_zset(self):
        import time

        await self.redis.hmset("return_risk:user:U001", {"total_orders": "8", "total_returns": "3"})
        past = time.time() - 2 * 86400
        await self.redis.zadd(
            "return_risk:user:U001:returns",
            {"ORD_1": past, "ORD_2": past + 100, "ORD_3": time.time() - 20 * 86400},
        )
        features = await self.engine.extract_features(
            user_id="U001", merchant_id="M001", category="electronics",
            amount=Decimal("500"), cod_flag=False, timestamp=NOW,
        )
        assert features["user_return_velocity_7d"]["value"] == 2
        assert features["user_return_velocity_7d"]["source"] == "redis_zset"

    async def test_merchant_defaults_and_seeded_overrides(self):
        await self.redis.hmset(
            "return_risk:merchant:M001",
            {"return_rate_30d": "0.28", "avg_resolution_hours": "26.5", "return_fraud_rate": "0.03"},
        )
        await self.redis.zadd("return_risk:merchant:M001:category", {"fashion": 0.41, "electronics": 0.10})
        features = await self.engine.extract_features(
            user_id="U001", merchant_id="M001", category="fashion",
            amount=Decimal("500"), cod_flag=False, timestamp=NOW,
        )
        assert features["merchant_return_rate_30d"]["value"] == 0.28
        assert features["merchant_avg_resolution_time"]["value"] == 26.5
        # merchant zset overrides the category baseline
        assert features["txn_category_return_baseline"]["value"] == 0.41
        assert features["txn_category_return_baseline"]["source"] == "redis_zset"

    async def test_merchant_missing_is_default(self):
        features = await self.engine.extract_features(
            user_id="U001", merchant_id="M_X", category="groceries",
            amount=Decimal("200"), cod_flag=False, timestamp=NOW,
        )
        assert features["merchant_return_rate_30d"]["value"] == 0.15
        assert features["merchant_return_rate_30d"]["source"] == "default"
        assert features["txn_category_return_baseline"]["value"] == CATEGORY_BASELINES["groceries"]

    async def test_time_of_day_and_salary_day(self):
        for hour, expected_risk in ((2, 0.3), (12, 0.0), (23, 0.3), (6, 0.0)):
            ts = datetime(2026, 8, 1, hour, 30)
            features = await self.engine.extract_features(
                user_id="U1", merchant_id="M1", category="beauty",
                amount=Decimal("300"), cod_flag=True, timestamp=ts,
            )
            assert features["txn_time_of_day_risk"]["value"] == expected_risk
            assert features["txn_is_salary_day"]["value"] is True  # 1st

    async def test_every_feature_has_provenance(self):
        await self.redis.hmset(
            "return_risk:user:U002",
            {"total_orders": "4", "total_returns": "1", "return_rate_30d": "0.25"},
        )
        features = await self.engine.extract_features(
            user_id="U002", merchant_id="M001", category="sports",
            amount=Decimal("2500"), cod_flag=True, timestamp=NOW,
        )
        assert ReturnRiskFeatureEngine.validate_provenance(features) == []

    async def test_update_user_profile_order_placed(self):
        await self.engine.update_user_profile(
            "U003", "ORD_1", Decimal("1500"), category="fashion", cod_flag=True
        )
        profile = await self.redis.hgetall("return_risk:user:U003")
        assert int(profile["total_orders"]) == 1
        assert int(profile["cod_orders"]) == 1
        assert "last_activity" in profile

    async def test_update_user_profile_return(self):
        await self.engine.update_user_profile(
            "U004", "ORD_A", Decimal("2000"), category="fashion", cod_flag=True
        )
        await self.engine.update_user_profile(
            "U004", "ORD_B", Decimal("1000"), category="fashion", cod_flag=False,
            returned=True, return_reason="SIZE_ISSUE",
        )
        profile = await self.redis.hgetall("return_risk:user:U004")
        assert int(profile["total_orders"]) == 2
        assert int(profile["total_returns"]) == 1
        assert float(profile["avg_return_value"]) == 1000.0
        reasons = await self.redis.hgetall("return_risk:user:U004:reasons")
        assert int(reasons["SIZE_ISSUE"]) == 1
        out = await self.redis.zrangebyscore("return_risk:user:U004:returns", 0, float("inf"))
        assert out == ["ORD_B"]

    async def test_feature_registry_still_round_trips(self):
        from return_risk.feature_engine import FeatureRegistry

        registry = FeatureRegistry()
        assert registry.composite_weights["user_return_rate_30d"] == 0.25
        assert len(registry.by_kind("merchant")) >= 3
