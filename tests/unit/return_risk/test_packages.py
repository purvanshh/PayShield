"""Import/smoke tests for the return-risk package (Phase 8 hello worlds)."""


class TestReturnRiskPackage:
    def test_all_modules_import(self):
        import return_risk.feature_engine  # noqa: F401
        import return_risk.recommendations  # noqa: F401
        import return_risk.rules_engine  # noqa: F401
        import return_risk.scorer  # noqa: F401

    def test_rules_engine_loads_catalogue(self):
        from return_risk.rules_engine import RulesEngine

        engine = RulesEngine()
        ids = [r.rule_id for r in engine.rules]
        assert "R-RULE-01" in ids
        assert engine.risk_tiers["HIGH"]["action"] == "REQUIRE_PREPAID"

    def test_feature_registry_loads_weights(self):
        from return_risk.feature_engine import FeatureRegistry

        registry = FeatureRegistry()
        assert registry.composite_weights["user_return_rate_30d"] == 0.25
        assert registry.weight("user_serial_returner_flag") == 0.20
        assert len(registry.by_kind("txn")) > 0

    def test_scorer_tiers_and_weights(self):
        from return_risk.scorer import ReturnRiskScorer

        scorer = ReturnRiskScorer()
        assert scorer.tier_for(0.1) == "LOW"
        assert scorer.tier_for(0.5) == "MEDIUM"
        assert scorer.tier_for(0.9) == "HIGH"
        assert abs(scorer.weights_sum() - 1.0) < 1e-9

    def test_normalize_features_clamps_range(self):
        from return_risk.feature_engine import FeatureRegistry
        from return_risk.scorer import ReturnRiskScorer

        registry = FeatureRegistry()
        out = ReturnRiskScorer.normalize_features(
            {"user_return_rate_30d": 2.5, "user_return_velocity_7d": -3}, registry
        )
        assert out["user_return_rate_30d"] == 1.0
        assert out["user_return_velocity_7d"] == 0.0

    def test_recommendations(self):
        from return_risk.recommendations import recommendations_for_action

        recs = recommendations_for_action("REQUIRE_PREPAID_ONLY")
        assert any("prepaid" in r.lower() for r in recs)
