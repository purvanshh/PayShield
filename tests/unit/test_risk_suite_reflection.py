"""Risk-suite reflection tests (Phase 37)."""

from agents.risk_suite_reflection import (
    analyze_chargeback_outcomes,
    analyze_return_risk_accuracy,
    build_risk_suite_reflection,
    generate_risk_suite_recommendations,
)


def _records(rows):
    return [
        {
            "risk_tier": tier,
            "returned": returned,
            "user_type": user_type,
        }
        for tier, returned, user_type in rows
    ]


class TestReturnRiskAccuracy:
    def test_precision_computed(self):
        records = _records(
            [
                ("HIGH", True, "serial_returner"),
                ("HIGH", True, "serial_returner"),
                ("HIGH", False, "casual_returner"),
                ("MEDIUM", False, "honest"),
                ("MEDIUM", True, "serial_returner"),
            ]
        )
        out = analyze_return_risk_accuracy(records)
        assert out["high_risk_total"] == 3
        assert out["high_risk_returned"] == 2
        assert out["high_risk_precision"] == round(2 / 3, 4)
        assert out["tier_misses"] == 1
        assert out["misses_by_user_type"] == {"serial_returner": 1}
        assert out["false_positives"] == 1

    def test_empty_records(self):
        out = analyze_return_risk_accuracy([])
        assert out["high_risk_total"] == 0
        assert out["high_risk_precision"] == 0.0

    def test_nulls_skipped(self):
        records = [{"risk_tier": None, "returned": True}]
        out = analyze_return_risk_accuracy(records)
        assert out["high_risk_total"] == 0


class TestChargebackOutcomes:
    def test_outcome_matrix(self):
        out = analyze_chargeback_outcomes(
            [
                {"response_type": "REJECT", "outcome": "won", "count": 3},
                {"response_type": "REJECT", "outcome": "lost", "count": 1},
                {"response_type": "ACCEPT", "outcome": "lost", "count": 2},
            ]
        )
        matrix = out["outcome_matrix"]
        assert len(matrix) == 3
        assert matrix[0]["response"] == "REJECT"
        assert matrix[0]["outcome"] == "won"


class TestRecommendations:
    def test_low_precision_raises_threshold(self):
        accuracy = analyze_return_risk_accuracy(
            _records([("HIGH", True, "a"), ("HIGH", False, "b"), ("HIGH", False, "c")])
        )
        recs = generate_risk_suite_recommendations(accuracy, {"outcome_matrix": []})
        assert any(r["type"] == "threshold_adjustment" for r in recs)
        adjustment = next(r for r in recs if r["type"] == "threshold_adjustment")
        assert adjustment["recommended"] == 0.75
        assert "below the 0.70 floor" in adjustment["reason"]

    def test_high_precision_no_threshold_change(self):
        accuracy = analyze_return_risk_accuracy(
            _records([("HIGH", True, "a"), ("HIGH", True, "b")])
        )
        recs = generate_risk_suite_recommendations(accuracy, {"outcome_matrix": []})
        assert all(r["type"] != "threshold_adjustment" for r in recs)

    def test_lost_rejects_suggest_conservative_strategy(self):
        matrix = [
            {"response_type": "REJECT", "outcome": "lost", "count": 2},
            {"response_type": "REJECT", "outcome": "won", "count": 1},
        ]
        recs = generate_risk_suite_recommendations(
            {"high_risk_precision": 1.0}, analyze_chargeback_outcomes(matrix)
        )
        assert any(r["type"] == "strategy_adjustment" for r in recs)

    def test_drift_triggers_retraining_rec(self):
        recs = generate_risk_suite_recommendations(
            {"high_risk_precision": 1.0}, {"outcome_matrix": []}, drift_detected=True
        )
        assert any(r["type"] == "retraining" for r in recs)


class TestAgentIntegration:
    def test_reflection_agent_delegates(self):
        from agents.base import AgentConfig
        from agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent(AgentConfig(agent_id="r", agent_type="REFLECTION"))
        payload = agent.analyze_risk_suite(
            return_records=_records([("HIGH", True, "serial_returner")]),
            chargeback_records=[{"response_type": "REJECT", "outcome": "won", "count": 1}],
        )
        assert payload["return_risk"]["high_risk_precision"] == 1.0
        assert payload["chargeback"]["outcome_matrix"][0]["response"] == "REJECT"

    def test_build_payload_shape(self):
        payload = build_risk_suite_reflection(
            return_records=_records([("HIGH", False, "x")]),
            chargeback_records=[],
            drift_detected=False,
        )
        assert set(payload.keys()) == {
            "return_risk",
            "chargeback",
            "drift_detected",
            "recommendations",
        }
