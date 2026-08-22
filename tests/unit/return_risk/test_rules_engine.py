"""RulesEngine tests (Phase 14)."""

import yaml

from return_risk.rules_engine import RulesEngine


def _features(**overrides):
    base = {
        "user_return_rate_30d": {"value": 0.0, "source": "redis_hash"},
        "user_return_rate_lifetime": {"value": 0.0, "source": "computed"},
        "user_total_orders": {"value": 8, "source": "redis_hash"},
        "user_serial_returner_flag": {"value": False, "source": "computed"},
        "user_return_velocity_7d": {"value": 0, "source": "redis_zset"},
        "user_cod_refusal_rate": {"value": 0.0, "source": "computed"},
        "user_cod_orders": {"value": 0, "source": "redis_hash"},
        "user_is_new": {"value": False, "source": "inferred"},
        "merchant_return_rate_30d": {"value": 0.12, "source": "redis_hash"},
        "txn_amount_risk": {"value": 0.05, "source": "computed"},
        "txn_category_return_baseline": {"value": 0.32, "source": "lookup_table"},
        "txn_time_of_day_risk": {"value": 0.0, "source": "computed"},
        "_meta": {"extracted_at": "2026-08-21T12:00:00"},
    }
    base.update(overrides)
    return base


def _flags(rule_id: str, value: bool) -> dict[str, dict]:
    return {rule_id: {"value": value, "source": "test"}}


class TestRulesEngine:
    def test_loads_eight_rules(self):
        engine = RulesEngine()
        ids = [r.rule_id for r in engine.rules]
        assert ids == [f"R-RULE-0{i}" for i in range(1, 9)]
        assert all(r.enabled for r in engine.rules)
        assert engine.risk_tiers["HIGH"]["action"] == "REQUIRE_PREPAID"

    def test_serial_returner_triggers(self):
        engine = RulesEngine()
        out = engine.evaluate(_features(**_flags("user_serial_returner_flag", True)))
        fired = [r["rule_id"] for r in out if r["triggered"]]
        assert "R-RULE-01" in fired
        entry = next(r for r in out if r["rule_id"] == "R-RULE-01")
        assert entry["action"] == "FLAG_FOR_REVIEW"
        assert entry["severity"] == 5

    def test_high_value_fashion_triggers(self):
        engine = RulesEngine()
        features = _features(
            **_flags("user_return_rate_30d", 0.35),
            **_flags("txn_amount_risk", 0.5),
            **_flags("txn_category_return_baseline", 0.35),
        )
        out = engine.evaluate(features)
        assert any(r["rule_id"] == "R-RULE-02" and r["triggered"] for r in out)

    def test_cod_refusal_pattern_triggers(self):
        engine = RulesEngine()
        features = _features(
            **_flags("user_cod_refusal_rate", 0.45),
            **_flags("user_cod_orders", 5),
        )
        out = engine.evaluate(features)
        assert any(r["rule_id"] == "R-RULE-03" and r["action"] == "BLOCK_COD" for r in out)

    def test_new_user_high_value_triggers(self):
        engine = RulesEngine()
        features = _features(
            **_flags("user_is_new", True),
            **_flags("txn_amount_risk", 0.8),
            **_flags("txn_category_return_baseline", 0.3),
        )
        out = engine.evaluate(features)
        assert any(r["rule_id"] == "R-RULE-05" and r["triggered"] for r in out)

    def test_low_risk_profile_accepts(self):
        engine = RulesEngine()
        features = _features(
            **_flags("user_return_rate_lifetime", 0.05),
            **_flags("user_total_orders", 12),
        )
        out = engine.evaluate(features)
        assert any(r["rule_id"] == "R-RULE-08" and r["action"] == "ACCEPT" for r in out)

    def test_results_sorted_by_severity(self):
        engine = RulesEngine()
        features = _features(
            **_flags("user_serial_returner_flag", True),
            **_flags("user_return_velocity_7d", 3),
            **_flags("txn_time_of_day_risk", 0.3),
        )
        out = engine.evaluate(features)
        severities = [r["severity"] for r in out if r["triggered"]]
        assert severities == sorted(severities, reverse=True)
        assert severities[0] == 5

    def test_missing_feature_degrades_to_error_entry(self):
        engine = RulesEngine()
        out = engine.evaluate({"user_is_new": {"value": True}})  # many features missing
        errors = [r for r in out if not r["triggered"] and "error" in r]
        assert errors  # entries with errors, no crash

    def test_reload_picks_up_rule_changes(self, tmp_path):
        path = tmp_path / "rules.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {
                            "rule_id": "T-RULE-01",
                            "name": "Test Rule",
                            "condition": "user_total_orders > 100",
                            "action": "FLAG_FOR_REVIEW",
                            "severity": 2,
                            "enabled": True,
                        }
                    ],
                    "risk_tiers": {"LOW": {"max_score": 0.3, "action": "ACCEPT"}},
                }
            )
        )

        engine = RulesEngine(path)
        assert engine.get_rule_by_id("T-RULE-01") is not None
        assert engine.evaluate(_features()) == []

        path.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {
                            "rule_id": "T-RULE-01",
                            "name": "Test Rule",
                            "condition": "user_total_orders > 3",
                            "action": "FLAG_FOR_REVIEW",
                            "severity": 2,
                            "enabled": True,
                        }
                    ],
                    "risk_tiers": {"LOW": {"max_score": 0.3, "action": "ACCEPT"}},
                }
            )
        )
        engine.reload_rules()
        out = engine.evaluate(_features())
        assert any(r["rule_id"] == "T-RULE-01" and r["triggered"] for r in out)

    def test_disabled_rules_never_fire(self, tmp_path):
        path = tmp_path / "rules.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {
                            "rule_id": "D-01",
                            "name": "Disabled",
                            "condition": "user_total_orders > 0",
                            "action": "ACCEPT",
                            "severity": 1,
                            "enabled": False,
                        }
                    ]
                }
            )
        )
        engine = RulesEngine(path)
        assert engine.evaluate(_features()) == []

    def test_get_rule_by_id(self):
        engine = RulesEngine()
        rule = engine.get_rule_by_id("R-RULE-04")
        assert rule is not None
        assert rule.action == "FLAG_FOR_REVIEW"
        assert engine.get_rule_by_id("NOPE") is None
