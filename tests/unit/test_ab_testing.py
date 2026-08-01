import pytest

from ml.ab_testing import (
    ABTestFramework,
    Experiment,
    ExperimentGuardrails,
    ExperimentResult,
    ExperimentStatus,
    ExperimentType,
    RuleABTesting,
)


class TestExperimentRegistration:
    def test_register_shadow_experiment(self):
        framework = ABTestFramework()
        exp = framework.register_experiment(
            name="shadow-test",
            challenger_version="v2",
            traffic_split=0.0,
        )
        assert exp.status == ExperimentStatus.SHADOW
        assert framework.get_experiment(exp.experiment_id) is exp
        assert framework._active_experiment is None

    def test_register_canary_with_split(self):
        framework = ABTestFramework()
        exp = framework.register_experiment(
            name="canary-test",
            challenger_version="v2",
            traffic_split=0.1,
        )
        assert exp.status == ExperimentStatus.CANARY
        assert framework._active_experiment is exp

    def test_only_one_active_ab_test(self):
        framework = ABTestFramework()
        framework.register_experiment("first", "v2", traffic_split=0.1)
        with pytest.raises(RuntimeError):
            framework.register_experiment("second", "v3", traffic_split=0.1)

    def test_invalid_traffic_split_rejected(self):
        framework = ABTestFramework()
        with pytest.raises(ValueError):
            framework.register_experiment("bad", "v2", traffic_split=1.5)
        with pytest.raises(ValueError):
            framework.register_experiment("bad2", "v2", traffic_split=-0.1)

    def test_multiple_shadow_experiments_allowed(self):
        framework = ABTestFramework()
        framework.register_experiment("s1", "v2")
        framework.register_experiment("s2", "v3")
        assert len(framework.list_experiments()) == 2


class TestExperimentLifecycle:
    def test_update_status_terminates_active_experiment(self):
        framework = ABTestFramework()
        exp = framework.register_experiment("life", "v2", traffic_split=0.1)
        framework.update_status(exp.experiment_id, ExperimentStatus.PROMOTED)
        assert exp.status == ExperimentStatus.PROMOTED
        assert exp.end_date
        assert framework._active_experiment is None

    def test_update_status_missing_id_is_noop(self):
        framework = ABTestFramework()
        framework.update_status("does-not-exist", ExperimentStatus.FAILED)

    def test_evaluate_unknown_experiment_raises(self):
        framework = ABTestFramework()
        with pytest.raises(ValueError):
            framework.evaluate_experiment("nope")

    def test_evaluate_produces_result(self):
        framework = ABTestFramework()
        exp = framework.register_experiment("eval", "v2", traffic_split=0.1)
        result = framework.evaluate_experiment(exp.experiment_id)
        assert isinstance(result, ExperimentResult)
        assert "fvar_mean" in result.champion_metrics
        assert "fvar_mean" in result.challenger_metrics
        assert 0.0 <= result.p_value <= 1.0
        assert result.recommendation

    def test_promote_and_rollback_require_valid_status(self, monkeypatch):
        framework = ABTestFramework()
        exp = framework.register_experiment("promo", "v2", traffic_split=0.1)
        from ml import registry as registry_module

        registry = registry_module.ModelRegistry()
        monkeypatch.setattr(registry_module, "ModelRegistry", lambda: registry)
        monkeypatch.setattr(registry, "promote", lambda *_a, **_k: None)
        framework.promote(exp.experiment_id)
        assert exp.status == ExperimentStatus.PROMOTED

        exp2 = framework.register_experiment("roll", "v2", traffic_split=0.1)
        monkeypatch.setattr(registry, "rollback", lambda *_a, **_k: None)
        framework.rollback(exp2.experiment_id)
        assert exp2.status == ExperimentStatus.ROLLED_BACK

    def test_promote_rejects_wrong_status(self):
        framework = ABTestFramework()
        exp = framework.register_experiment("badpromo", "v2")
        with pytest.raises(ValueError):
            framework.promote(exp.experiment_id)


class TestExperimentGuardrails:
    def test_split_over_ten_percent_requires_admin(self):
        experiment = Experiment(traffic_split=0.2, created_by="analyst")
        assert ExperimentGuardrails.validate_experiment(experiment)

    def test_admin_can_request_large_split(self):
        experiment = Experiment(traffic_split=0.5, created_by="admin")
        assert ExperimentGuardrails.validate_experiment(experiment) == []

    def test_auto_rollback_on_latency_increase(self):
        experiment = Experiment()
        assert ExperimentGuardrails.should_auto_rollback(
            experiment, current_latency_p99=1.3, baseline_latency_p99=1.0,
            current_error_rate=0.0001,
        )
        assert not ExperimentGuardrails.should_auto_rollback(
            experiment, current_latency_p99=1.05, baseline_latency_p99=1.0,
            current_error_rate=0.0001,
        )

    def test_auto_rollback_on_error_rate(self):
        experiment = Experiment()
        assert ExperimentGuardrails.should_auto_rollback(
            experiment, current_latency_p99=1.0, baseline_latency_p99=1.0,
            current_error_rate=0.01,
        )


class TestRuleABTesting:
    def test_unknown_rule_passes_through(self):
        framework = RuleABTesting()
        decision = framework.evaluate("unknown", {"action": "ALLOW"}, {"action": "BLOCK"})
        assert decision["action"] == "pass"

    def test_shadow_rule_agreement(self):
        framework = RuleABTesting()
        framework.register_rule("R1", {"enabled": True})
        decision = framework.evaluate("R1", {"action": "ALLOW"}, {"action": "ALLOW"})
        assert decision["action"] == "agree"
        stats = framework.get_stats("R1")
        assert stats["evaluations"] == 1
        assert stats["agreements"] == 1

    def test_shadow_rule_disagreement_tracks_stats(self):
        framework = RuleABTesting()
        framework.register_rule("R2", {"enabled": True})
        decision = framework.evaluate("R2", {"action": "ALLOW"}, {"action": "BLOCK"})
        assert decision["action"] == "disagree"
        assert decision["disagreement_rate"] == 1.0
        stats = framework.get_stats("R2")
        assert stats["disagreements"] == 1

    def test_no_promotion_recommendation_below_sample_threshold(self):
        framework = RuleABTesting()
        framework.register_rule("R3", {"enabled": True})
        for _ in range(50):
            framework.evaluate("R3", {"action": "ALLOW"}, {"action": "BLOCK"})
        decision = framework.evaluate("R3", {"action": "ALLOW"}, {"action": "BLOCK"})
        assert "recommendation" not in decision


class TestExperimentTypeDefaults:
    def test_default_type(self):
        exp = Experiment()
        assert exp.experiment_type == ExperimentType.MODEL_CHALLENGER

    def test_to_dict_roundtrip(self):
        framework = ABTestFramework()
        exp = framework.register_experiment("dict", "v2", traffic_split=0.05)
        data = exp.to_dict()
        assert data["experiment_id"] == exp.experiment_id
        assert data["status"] == ExperimentStatus.CANARY
