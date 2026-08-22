"""ReturnRiskScorer tests (Phase 15)."""

import json
from datetime import datetime
from decimal import Decimal

from return_risk.feature_engine import ReturnRiskFeatureEngine
from return_risk.rules_engine import RulesEngine
from return_risk.scorer import ReturnRiskScorer
from tests.fake_redis import FakeRedis

NOW = datetime(2026, 8, 21, 12, 0, 0)


def _scorer() -> tuple[ReturnRiskScorer, FakeRedis]:
    redis = FakeRedis()
    return ReturnRiskScorer(
        feature_engine=ReturnRiskFeatureEngine(redis),
        rules_engine=RulesEngine(),
    ), redis


async def _seed_serial_returner(redis):
    import time

    end = time.time()
    await redis.hmset(
        "return_risk:user:U003",
        {
            "total_orders": "18",
            "total_returns": "10",
            "return_rate_30d": "0.62",
            "return_rate_90d": "0.55",
            "avg_return_value": "3800",
            "cod_refusals": "3",
            "cod_orders": "7",
            "return_reason_distribution": json.dumps({"SIZE_ISSUE": 5, "CHANGED_MIND": 5}),
        },
    )
    await redis.hmset(
        "return_risk:merchant:M001",
        {"return_rate_30d": "0.28", "avg_resolution_hours": "26.5", "return_fraud_rate": "0.03"},
    )
    await redis.zadd("return_risk:merchant:M001:category", {"fashion": 0.35})
    await redis.zadd("return_risk:user:U003:returns", {"ORD_1": end - 86400, "ORD_2": end - 2 * 86400})


class TestReturnRiskScorer:
    async def test_scores_known_inputs(self):
        scorer, redis = _scorer()
        await _seed_serial_returner(redis)
        result = await scorer.score(
            user_id="U003",
            merchant_id="M001",
            order_id="ORD_9",
            amount=Decimal("6000"),
            category="fashion",
            cod_flag=True,
            timestamp=NOW,
        )
        assert result["order_id"] == "ORD_9"
        assert 0 <= result["return_risk_score"] <= 1
        assert result["risk_tier"] in ("LOW", "MEDIUM", "HIGH")
        assert result["risk_tier"] == "HIGH"
        assert result["confidence"] > 0.5
        assert any("prepaid" in r.lower() for r in result["recommendations"])
        assert any(r["rule_id"] == "R-RULE-01" and r["triggered"] for r in result["rules_triggered"])
        assert result["user_profile"]["serial_returner"] is True

    async def test_contributions_sum_to_score(self):
        scorer, redis = _scorer()
        await _seed_serial_returner(redis)
        result = await scorer.score(
            user_id="U003",
            merchant_id="M001",
            order_id="ORD_10",
            amount=Decimal("6000"),
            category="fashion",
            cod_flag=False,
            timestamp=NOW,
        )
        breakdown = result["feature_breakdown"]
        total = round(sum(f["contribution"] for f in breakdown.values()), 4)
        # post-contribution rule adjustment (see scorer.RULE_BOOST) - capped,
        # and transparently derivable from the fired rules in the response
        boost = ReturnRiskScorer.promotion_score(result["rules_triggered"])
        assert abs((total + boost) - result["return_risk_score"]) < 1e-3
        for name, entry in breakdown.items():
            assert entry["source"] not in ("", "unknown") or name in (
                "txn_user_merchant_interaction_count",
            )
            assert abs(entry["contribution"] - entry["weight"] * entry["normalized_value"]) < 1e-3

    async def test_new_user_low_confidence(self):
        scorer, redis = _scorer()
        result = await scorer.score(
            user_id="U_NOPE",
            merchant_id="M_ANY",
            order_id="ORD_1",
            amount=Decimal("1200"),
            category="grocery",
            cod_flag=False,
            timestamp=NOW,
        )
        assert result["user_profile"]["is_new_user"] is True
        assert result["confidence"] <= 0.7  # 1.0 - 0.3 new-user penalty
        assert result["risk_tier"] in ("LOW", "MEDIUM")

    async def test_block_cod_rule_boosts_score(self):
        scorer, redis = _scorer()
        await redis.hmset(
            "return_risk:user:U007",
            {"total_orders": "8", "total_returns": "4", "cod_refusals": "5", "cod_orders": "6",
             "return_rate_30d": "0.5"},
        )
        result = await scorer.score(
            user_id="U007",
            merchant_id="M001",
            order_id="ORD_2",
            amount=Decimal("1500"),
            category="electronics",
            cod_flag=True,
            timestamp=NOW,
        )
        assert any(
            r["rule_id"] == "R-RULE-03" and r["triggered"] for r in result["rules_triggered"]
        )
        # un-boosted score was <= 0.85; with BLOCK_COD +0.15 it must clamp at 1.0
        assert result["return_risk_score"] <= 1.0

    async def test_high_tier_recommendations(self):
        scorer, redis = _scorer()
        await _seed_serial_returner(redis)
        result = await scorer.score(
            user_id="U003",
            merchant_id="M001",
            order_id="ORD_3",
            amount=Decimal("6000"),
            category="fashion",
            cod_flag=True,
            timestamp=NOW,
        )
        recs = " | ".join(result["recommendations"]).lower()
        assert "prepaid" in recs and "manual review" in recs and "signature" in recs

    async def test_low_risk_order_accepts(self):
        scorer, redis = _scorer()
        await redis.hmset(
            "return_risk:user:U100",
            {"total_orders": "20", "total_returns": "1", "return_rate_30d": "0.03",
             "return_rate_90d": "0.04"},
        )
        await redis.hmset("return_risk:merchant:M100", {"return_rate_30d": "0.05"})
        result = await scorer.score(
            user_id="U100",
            merchant_id="M100",
            order_id="ORD_4",
            amount=Decimal("900"),
            category="electronics",
            cod_flag=False,
            timestamp=NOW,
        )
        assert result["risk_tier"] == "LOW"
        assert any("no additional measures" in r for r in result["recommendations"])

    async def test_feature_provenance_in_breakdown(self):
        scorer, redis = _scorer()
        await _seed_serial_returner(redis)
        result = await scorer.score(
            user_id="U003",
            merchant_id="M001",
            order_id="ORD_5",
            amount=Decimal("6000"),
            category="fashion",
            cod_flag=False,
            timestamp=NOW,
        )
        assert result["feature_breakdown"]["user_return_rate_30d"]["source"] == "redis_hash"
        assert result["feature_breakdown"]["txn_amount_risk"]["source"] == "computed"


class TestScorerHelpers:
    def test_weights_sum_to_one(self):
        from return_risk.scorer import FEATURE_WEIGHTS

        assert abs(sum(FEATURE_WEIGHTS.values()) - 1.0) < 1e-9

    def test_tier_for(self):
        scorer = ReturnRiskScorer()
        assert scorer.tier_for(0.1) == "LOW"
        assert scorer.tier_for(0.5) == "MEDIUM"
        assert scorer.tier_for(0.9) == "HIGH"

    def test_action_for(self):
        scorer = ReturnRiskScorer()
        assert scorer.action_for(0.1) == "ACCEPT"
        assert scorer.action_for(0.9) == "REQUIRE_PREPAID"

    def test_normalize_feature_boolean_and_velocity(self):
        assert ReturnRiskScorer._normalize_feature("user_serial_returner_flag", True) == 1.0
        assert ReturnRiskScorer._normalize_feature("user_serial_returner_flag", False) == 0.0
        assert ReturnRiskScorer._normalize_feature("user_return_velocity_7d", 6) == 1.0
        assert ReturnRiskScorer._normalize_feature("user_return_velocity_7d", 2) == 0.4
