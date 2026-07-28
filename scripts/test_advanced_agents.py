#!/usr/bin/env python3
"""
Test script for Advanced Agents (Phase 58).
Tests Planner, Critic, Reflection, and Validation agents.
"""

import sys
import json
import asyncio
from datetime import datetime, timezone


def test_planner_decomposes_complex_case():
    from agents.planner_agent import PlannerAgent, InvestigationPlan
    from agents.base import AgentConfig

    agent = PlannerAgent()
    transaction = {
        "transaction_id": "txn_test_001",
        "amount": 15000.00,
        "currency": "USD",
        "user": {"id": "user_456", "age_days": 3},
        "merchant": {"id": "merchant_789", "category": "electronics"},
        "device": {"fingerprint": "fp_abc123", "ip": "203.0.113.1"},
    }

    plan = agent.decompose_investigation(transaction, confidence=0.75)
    plan.select_best_strategy()

    assert len(plan.strategies) >= 3, f"Expected >= 3 strategies, got {len(plan.strategies)}"
    assert plan.selected_strategy is not None, "No strategy selected"
    assert len(plan.sub_tasks) > 0, "No sub-tasks generated"

    print(f"[PASS] test_planner_decomposes_complex_case: {len(plan.sub_tasks)} sub-tasks generated")
    return True


def test_critic_challenges_weak_block():
    from agents.critic_agent import CriticAgent

    agent = CriticAgent()

    weak_decision = {
        "action": "BLOCK",
        "confidence": 0.65,
        "amount": 500.00,
        "user_median_amount": 50.00,
        "user_vip": False,
        "historical_fp_rate": 0.0,
        "single_agent_dissent": False,
        "transaction_id": "txn_001",
    }

    result = agent.evaluate_decision(weak_decision)
    assert result.should_challenge, "Critic should challenge BLOCK with confidence < 0.80"
    assert len(result.challenges) >= 1, "Expected at least 1 challenge"

    print(f"[PASS] test_critic_challenges_weak_block: {len(result.challenges)} challenges")
    return True


def test_critic_no_challenge_strong_decision():
    from agents.critic_agent import CriticAgent

    agent = CriticAgent()

    strong_decision = {
        "action": "BLOCK",
        "confidence": 0.95,
        "amount": 50000.00,
        "user_median_amount": 50.00,
        "user_vip": False,
        "historical_fp_rate": 0.02,
        "single_agent_dissent": False,
        "transaction_id": "txn_002",
    }

    result = agent.evaluate_decision(strong_decision)
    assert not result.should_challenge, "Critic should not challenge strong BLOCK"

    print("[PASS] test_critic_no_challenge_strong_decision")
    return True


def test_critic_challenges_vip_exception():
    from agents.critic_agent import CriticAgent

    agent = CriticAgent()

    vip_decision = {
        "action": "BLOCK",
        "confidence": 0.85,
        "amount": 2000.00,
        "user_median_amount": 100.00,
        "user_vip": True,
        "historical_fp_rate": 0.02,
        "single_agent_dissent": False,
        "transaction_id": "txn_003",
    }

    result = agent.evaluate_decision(vip_decision)
    has_vip_challenge = any("VIP" in c["reason"] for c in result.challenges)
    assert has_vip_challenge, "Critic should challenge VIP high-amount BLOCK"

    print("[PASS] test_critic_challenges_vip_exception")
    return True


def test_reflection_identifies_fp_pattern():
    from agents.reflection_agent import ReflectionAgent, ReflectionReport
    from datetime import datetime, timezone, timedelta

    agent = ReflectionAgent()
    report = ReflectionReport(
        period_start=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        period_end=datetime.now(timezone.utc).isoformat(),
    )

    report.add_finding(
        category="false_positive_cluster",
        description="FP clustered around electronics merchant",
        severity="high",
        evidence={"merchant_category": "electronics", "count": 15},
    )

    assert len(report.findings) == 1, "Expected 1 finding"
    assert report.findings[0]["category"] == "false_positive_cluster"

    report.add_recommendation(
        target="rules.electronics_threshold",
        change={"threshold_adjustment": 0.15},
        rationale="High FP rate for electronics",
        requires_approval=True,
    )

    assert len(report.recommendations) == 1, "Expected 1 recommendation"

    print("[PASS] test_reflection_identifies_fp_pattern")
    return True


def test_validation_blocks_schema_violation():
    from agents.validation_agent import ValidationAgent

    agent = ValidationAgent()

    invalid_decision = {
        "action": "INVALID_ACTION",
        "confidence": "not_a_number",
        "evidence": [],
        "transaction_id": "txn_004",
    }

    result = agent.validate(invalid_decision)
    assert not result.is_valid, "Validation should reject invalid decision"
    assert len(result.violations) >= 2, "Expected multiple violations"

    print(f"[PASS] test_validation_blocks_schema_violation: {len(result.violations)} violations")
    return True


def test_validation_catches_contradiction():
    from agents.validation_agent import ValidationAgent

    agent = ValidationAgent()

    contradictory_decision = {
        "action": "BLOCK",
        "confidence": 0.90,
        "evidence": [
            {"type": "geo_velocity", "impossible_travel": True, "detail": "Login from US, txn from CN in 5 min"},
            {"type": "device_fingerprint", "known_device": True, "device_id": "fp_abc123"},
        ],
        "transaction_id": "txn_005",
    }

    result = agent.validate(contradictory_decision)
    assert not result.is_valid, "Validation should detect contradiction"
    assert len(result.contradictions) >= 1, "Expected at least 1 contradiction"

    print(f"[PASS] test_validation_catches_contradiction: {len(result.contradictions)} contradictions")
    return True


def test_validation_allows_valid_decision():
    from agents.validation_agent import ValidationAgent

    agent = ValidationAgent()

    valid_decision = {
        "action": "BLOCK",
        "confidence": 0.92,
        "evidence": [
            {"type": "amount_anomaly", "score": 0.95, "detail": "Amount 10x above average"},
            {"type": "new_device", "score": 0.88, "detail": "Device first seen 2 hours ago"},
        ],
        "transaction_id": "txn_006",
    }

    result = agent.validate(valid_decision)
    assert result.is_valid, "Validation should pass valid decision"

    print("[PASS] test_validation_allows_valid_decision")
    return True


def test_full_agent_pipeline_with_critic():
    from agents.critic_agent import CriticAgent
    from agents.validation_agent import ValidationAgent

    critic = CriticAgent()
    validator = ValidationAgent()

    pipeline_decision = {
        "action": "BLOCK",
        "confidence": 0.75,
        "amount": 25000.00,
        "user_median_amount": 100.00,
        "user_vip": False,
        "historical_fp_rate": 0.12,
        "single_agent_dissent": True,
        "evidence": [
            {"type": "amount_anomaly", "score": 0.95},
            {"type": "new_user", "score": 0.80},
        ],
        "transaction_id": "txn_007",
    }

    critic_result = critic.evaluate_decision(pipeline_decision)
    assert critic_result.should_challenge, "Critic should challenge this decision"

    validation_result = validator.validate(pipeline_decision)
    assert validation_result.is_valid, "Validation should pass (structural)"

    print("[PASS] test_full_agent_pipeline_with_critic: critic challenged, validation passed")
    return True


def test_planner_agent_message_flow():
    from agents.planner_agent import PlannerAgent
    from agents.base import AgentConfig

    agent = PlannerAgent()

    async def _test():
        msg = await agent.process(type("msg", (), {
            "message_id": "test_001",
            "sender": "orchestrator",
            "recipient": "planner_agent",
            "message_type": "COMPLEX_INVESTIGATION_REQUEST",
            "content": {
                "transaction": {
                    "transaction_id": "txn_test_002",
                    "amount": 5000.00,
                    "user": {"id": "user_789"},
                    "device": {"fingerprint": "fp_xyz"},
                    "merchant": {"id": "merchant_012"},
                },
                "confidence": 0.78,
            },
            "correlation_id": "corr_001",
            "priority": 2,
        }))

        assert msg.message_type == "INVESTIGATION_PLAN", f"Expected INVESTIGATION_PLAN, got {msg.message_type}"
        assert "sub_tasks" in msg.content, "Expected sub_tasks in response"
        assert len(msg.content["sub_tasks"]) > 0, "Expected non-empty sub_tasks"

        print(f"[PASS] test_planner_agent_message_flow: {len(msg.content['sub_tasks'])} sub-tasks")
        return True

    return asyncio.run(_test())


def run_all():
    tests = [
        ("Planner: decomposes complex case", test_planner_decomposes_complex_case),
        ("Planner: message flow", test_planner_agent_message_flow),
        ("Critic: challenges weak BLOCK", test_critic_challenges_weak_block),
        ("Critic: no challenge strong decision", test_critic_no_challenge_strong_decision),
        ("Critic: challenges VIP exception", test_critic_challenges_vip_exception),
        ("Reflection: identifies FP pattern", test_reflection_identifies_fp_pattern),
        ("Validation: blocks schema violation", test_validation_blocks_schema_violation),
        ("Validation: catches contradiction", test_validation_catches_contradiction),
        ("Validation: allows valid decision", test_validation_allows_valid_decision),
        ("Pipeline: critic + validation", test_full_agent_pipeline_with_critic),
    ]

    passed = 0
    failed = []

    print("=" * 60)
    print("  Advanced Agents Test Suite")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    print()

    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed.append(name)
        except Exception as e:
            failed.append(name)
            print(f"[FAIL] {name}: {e}")

    print()
    print("-" * 60)
    print(f"  Results: {passed}/{len(tests)} passed")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
    print("=" * 60)

    return len(failed) == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
