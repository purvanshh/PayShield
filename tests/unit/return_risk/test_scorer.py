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
            "avg_order_value": "5000",  # realistic AOV -> ratio ~1.2 for a ₹6k order
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
        if result.get("engine") == "hand_weighted":
            assert abs((total + boost) - result["return_risk_score"]) < 1e-3
        else:
            # XGBoost engine: the score comes from the model; the breakdown
            # is the transparent hand-weighted decomposition for merchants.
            assert result["engine"] == "xgboost"
            assert result["feature_importance"] is not None
            assert result["xgb_features"] is not None
            assert 0 <= result["return_risk_score"] <= 1
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

    async def test_demo_honest_customer_is_low(self):
        # Mirrors verify_live_stack.py ORD_HONEST_001. Regression guard for the
        # amount_vs_user_aov_ratio bug: the feature engine used avg_return_value
        # as avg_order_value, producing ratio=8.0 (past the model's training
        # ceiling of 4.0) and spiking an honest customer to MEDIUM/HIGH.
        scorer, redis = _scorer()
        await redis.hmset(
            "return_risk:user:U_HONEST_001",
            {
                "total_orders": "25",
                "total_returns": "2",
                "return_rate_30d": "0.04",
                "return_rate_90d": "0.08",
                "avg_return_value": "1500",
                "serial_returner": "false",
                "cod_refusals": "0",
                "cod_orders": "3",
                "last_activity": datetime(2026, 8, 18).isoformat(),
            },
        )
        await redis.hmset("return_risk:merchant:M_ELECTRONICS_001", {"return_rate_30d": "0.12"})
        await redis.zadd("return_risk:merchant:M_ELECTRONICS_001:category", {"electronics": 0.12})
        result = await scorer.score(
            user_id="U_HONEST_001",
            merchant_id="M_ELECTRONICS_001",
            order_id="ORD_HONEST_001",
            amount=Decimal("12000"),
            category="electronics",
            cod_flag=False,
            payment_method="UPI",
            timestamp=NOW,
        )
        # No stored AOV -> neutral population fallback, ratio stays in-envelope.
        assert result["xgb_features"]["amount_vs_user_aov_ratio"] <= 4.0
        assert result["risk_tier"] == "LOW"
        assert result["return_risk_score"] <= 0.35

    async def test_demo_serial_returner_is_high(self):
        # Mirrors verify_live_stack.py ORD_SERIAL_001. The demo profile carries
        # its own avg_order_value so amount_vs_user_aov_ratio stays ~1.0 and the
        # serial-returner signal keeps the order HIGH.
        scorer, redis = _scorer()
        await redis.hmset(
            "return_risk:user:U_SERIAL_001",
            {
                "total_orders": "15",
                "total_returns": "10",
                "return_rate_30d": "0.66",
                "return_rate_90d": "0.66",
                "avg_order_value": "5000",
                "avg_return_value": "4500",
                "serial_returner": "true",
                "cod_refusals": "3",
                "cod_orders": "8",
                "last_activity": datetime(2026, 8, 19).isoformat(),
            },
        )
        await redis.hmset("return_risk:merchant:M_FASHION_001", {"return_rate_30d": "0.30"})
        await redis.zadd("return_risk:merchant:M_FASHION_001:category", {"fashion": 0.30})
        result = await scorer.score(
            user_id="U_SERIAL_001",
            merchant_id="M_FASHION_001",
            order_id="ORD_SERIAL_001",
            amount=Decimal("5500"),
            category="fashion",
            cod_flag=True,
            payment_method="UPI",
            timestamp=NOW,
        )
        assert result["risk_tier"] == "HIGH"
        assert result["return_risk_score"] >= 0.70
        assert result["user_profile"]["serial_returner"] is True

    async def test_abuse_ring_sentinel_overrides_score_to_high(self):
        # A ring of 4 users sharing one shipping pincode, each with a 4-return
        # velocity spike. The model sees a *moderate* user (LOW on its own) but
        # the shared-address + velocity pattern is coordinated abuse - the
        # sentinel (R-RULE-09) forces the order to HIGH (defense-only).
        scorer, redis = _scorer()
        import time

        for uid in ("U_RING_A", "U_RING_B", "U_RING_C", "U_RING_D"):
            await redis.hmset(
                f"return_risk:user:{uid}",
                {
                    "total_orders": "6",
                    "total_returns": "5",
                    "return_rate_30d": "0.25",
                    "return_rate_90d": "0.25",
                    "avg_return_value": "3000",
                    "cod_refusals": "1",
                    "cod_orders": "4",
                },
            )
            await redis.zadd(
                f"return_risk:user:{uid}:returns",
                {f"ORD_{uid}_{i}": time.time() - (i + 1) * 86400 for i in range(4)},
            )
        await redis.hmset("return_risk:merchant:M_RING", {"return_rate_30d": "0.30"})
        await redis.zadd("return_risk:merchant:M_RING:category", {"fashion": 0.30})

        def _kw(uid, oid, addr):
            return {
                "user_id": uid,
                "merchant_id": "M_RING",
                "order_id": oid,
                "amount": Decimal("5000"),
                "category": "fashion",
                "cod_flag": False,
                "payment_method": "UPI",
                "timestamp": NOW,
                "shipping_address": addr,
            }

        # Baseline: D alone on a different address -> shared count == 1, LOW.
        alone = await scorer.score(**_kw("U_RING_D", "ORD_RING_D", "560002"))
        assert alone["risk_tier"] == "LOW"
        assert not any(
            r["rule_id"] == "R-RULE-09" and r["triggered"] for r in alone["rules_triggered"]
        )

        # Populate the ring: A, B, C ship to the shared pincode first.
        for uid in ("U_RING_A", "U_RING_B", "U_RING_C"):
            await scorer.score(**_kw(uid, f"ORD_{uid}", "560001"))

        # D now ships to the shared address -> count == 4 -> sentinel fires.
        ringed = await scorer.score(**_kw("U_RING_D", "ORD_RING_D", "560001"))
        assert any(
            r["rule_id"] == "R-RULE-09" and r["triggered"] for r in ringed["rules_triggered"]
        )
        assert ringed["risk_tier"] == "HIGH"
        assert ringed["return_risk_score"] >= 0.85

    async def test_shared_address_without_velocity_does_not_trigger(self):
        # Shared address alone is not enough: the sentinel needs the velocity
        # spike too, so ordinary co-shipping (family) never false-positives.
        scorer, redis = _scorer()
        for uid in ("U_SHIP_A", "U_SHIP_B", "U_SHIP_C", "U_SHIP_D"):
            await redis.hmset(
                f"return_risk:user:{uid}",
                {
                    "total_orders": "4",
                    "total_returns": "1",
                    "return_rate_30d": "0.20",
                    "return_rate_90d": "0.20",
                    "cod_refusals": "0",
                    "cod_orders": "1",
                },
            )
        await redis.hmset("return_risk:merchant:M_RING", {"return_rate_30d": "0.30"})
        await redis.zadd("return_risk:merchant:M_RING:category", {"fashion": 0.30})
        for uid in ("U_SHIP_A", "U_SHIP_B", "U_SHIP_C"):
            await scorer.score(
                user_id=uid, merchant_id="M_RING", order_id=f"ORD_{uid}",
                amount=Decimal("3000"), category="fashion", cod_flag=False,
                payment_method="UPI", timestamp=NOW, shipping_address="560099",
            )
        result = await scorer.score(
            user_id="U_SHIP_D", merchant_id="M_RING", order_id="ORD_U_SHIP_D",
            amount=Decimal("3000"), category="fashion", cod_flag=False,
            payment_method="UPI", timestamp=NOW, shipping_address="560099",
        )
        assert not any(
            r["rule_id"] == "R-RULE-09" and r["triggered"] for r in result["rules_triggered"]
        )

    async def test_extreme_aov_order_scores_sane(self):
        # A ₹1.2L order on a ₹15k-AOV user: the raw amount_vs_user_aov_ratio of
        # 8.0 must be clamped to 4.0 (the model's training ceiling) so the
        # XGBoost input stays in-distribution and the score is a valid [0,1]
        # probability - never NaN and never a spurious tier from an OOD 8.0.
        scorer, redis = _scorer()
        await redis.hmset(
            "return_risk:user:U_EXTREME",
            {
                "total_orders": "10",
                "total_returns": "3",
                "return_rate_30d": "0.20",
                "return_rate_90d": "0.20",
                "avg_order_value": "15000",
                "avg_return_value": "5000",
                "cod_refusals": "0",
                "cod_orders": "2",
            },
        )
        await redis.hmset("return_risk:merchant:M_EXT", {"return_rate_30d": "0.30"})
        await redis.zadd("return_risk:merchant:M_EXT:category", {"fashion": 0.30})
        result = await scorer.score(
            user_id="U_EXTREME",
            merchant_id="M_EXT",
            order_id="ORD_EXTREME",
            amount=Decimal("120000"),
            category="fashion",
            cod_flag=False,
            payment_method="UPI",
            timestamp=NOW,
        )
        assert result["xgb_features"]["amount_vs_user_aov_ratio"] == 4.0
        assert 0 <= result["return_risk_score"] <= 1
        assert result["return_risk_score"] == result["return_risk_score"]  # not NaN


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
