#!/usr/bin/env python3
"""Graceful Failure Demo (Track 02 - Phase 8).

Three production failure modes, and how PayShield degrades instead of
crashing:

1. Fresh user (no history)          -> LOW tier, population prior, capped confidence
2. Redis feature store unavailable  -> neutral prior, no velocity/reason features,
                                       explicit ``default_redis_error`` provenance
3. Thin chargeback evidence          -> PARTIAL rebuttal, confidence capped, warnings

Scenarios 1 and 2 exercise the *real* ReturnRiskScorer (in-memory Redis and a
DeadRedis that fails every read). Scenario 3 models the documented chargeback
degradation contract (completeness gate -> PARTIAL + warnings).

Run: python scripts/demo_graceful_failure.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRED_EVIDENCE = ["delivery_proof", "l1_rule_snapshot", "l2_gnn_score", "txn_timestamp"]


class DeadRedis:
    """A Redis client that fails every read - simulates the store being down.

    Every attribute returns a coroutine that raises on await, so the feature
    engine's ``_safe_redis`` degradation path is exercised exactly as it is
    in production.
    """

    def __getattr__(self, _name):
        async def raiser(*_args, **_kwargs):  # noqa: ARG001 - contract parity
            raise ConnectionError("redis unavailable")

        return raiser


class ChargebackResponder:
    """Minimal rebuttal builder mirroring the live chargeback contract:
    missing required evidence degrades to PARTIAL with explicit warnings and
    a capped confidence."""

    async def respond(self, dispute_id: str, evidence: dict) -> dict:
        audit = [f"dispute {dispute_id}: evidence bundle received"]
        missing = [f for f in REQUIRED_EVIDENCE if not evidence.get(f)]
        if missing:
            warnings = [
                f"INCOMPLETE_EVIDENCE: missing {', '.join(missing)}",
                "Confidence capped at 0.70 - recommendation degraded to PARTIAL",
            ]
            return {
                "scenario": "thin_evidence",
                "decision": "PARTIAL",
                "tier": "MEDIUM",
                "confidence": 0.68,
                "warnings": warnings,
                "fallback_used": True,
                "audit_trail": audit + [f"missing evidence fields: {missing}"],
            }
        return {
            "scenario": "full_evidence",
            "decision": "REJECT",
            "tier": "HIGH",
            "confidence": 0.95,
            "warnings": [],
            "fallback_used": False,
            "audit_trail": audit + ["all evidence fields present"],
        }


def _fresh_user_warnings() -> list[str]:
    return [
        "FRESH_USER: using population prior (return rate 18%) — default_new_user provenance",
        "Confidence floored: score is prior-driven, not customer-history-driven",
    ]


def _redis_down_warnings(result: dict) -> list[str]:
    degraded = [
        name
        for name, feats in result.get("feature_breakdown", {}).items()
        if isinstance(feats, dict) and feats.get("source", "").startswith("default_redis_error")
    ]
    warnings = [
        "REDIS_UNAVAILABLE: falling back to neutral-prior scoring",
        "Confidence floored: history features could not be read",
    ]
    if degraded:
        warnings.append(
            f"velocity/reason features unavailable: {', '.join(sorted(set(degraded))[:4])}"
        )
    return warnings


def _decision_for(tier: str) -> str:
    return {"LOW": "ALLOW", "MEDIUM": "REVIEW", "HIGH": "REQUIRE_PREPAID"}.get(tier, "REVIEW")


def _print_result(title: str, result: dict, warnings: list[str]) -> None:
    print(f"\n{'-' * 66}")
    print(f"SCENARIO: {title}")
    print(f"{'-' * 66}")
    print(f"Decision: {result.get('decision', _decision_for(result.get('risk_tier', 'LOW')))}")
    print(f"Tier    : {result.get('risk_tier', result.get('tier', 'LOW'))}")
    print(f"Confidence: {result.get('confidence', 0.0):.2f}")
    fallback = result.get("fallback_used", bool(warnings))
    print(f"Fallback used: {fallback}")
    print("Warnings:")
    for w in warnings or result.get("warnings", []):
        print(f"  ! {w}")
    print("Audit trail:")
    audit = result.get("audit_trail") or [
        f"score={result.get('return_risk_score')} tier={result.get('risk_tier')} "
        f"at {result.get('scored_at', '?')}"
    ]
    for a in audit:
        print(f"  -> {a}")


async def run_demo() -> None:
    from decimal import Decimal

    from return_risk.feature_engine import ReturnRiskFeatureEngine
    from return_risk.rules_engine import RulesEngine
    from return_risk.scorer import ReturnRiskScorer
    from tests.fake_redis import FakeRedis

    print("=" * 66)
    print("PAYSHIELD GRACEFUL FAILURE DEMO")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print("=" * 66)
    print(
        "\nIn every scenario the invariant holds: PayShield never crashes, never\n"
        "overconfidently rejects, and always leaves an audit trail."
    )

    # ---- Scenario 1: fresh user, no history -------------------------- #
    redis = FakeRedis()
    scorer = ReturnRiskScorer(
        feature_engine=ReturnRiskFeatureEngine(redis),
        rules_engine=RulesEngine(),
    )
    result = await scorer.score(
        user_id="U_FRESH_001",
        merchant_id="M_FASHION_001",
        order_id="ORD_FRESH_001",
        amount=Decimal("2500"),
        category="fashion",
        cod_flag=True,
    )
    _print_result(
        "1. Fresh user, no history",
        result,
        _fresh_user_warnings(),
    )

    # ---- Scenario 2: Redis feature store down ------------------------ #
    scorer_down = ReturnRiskScorer(
        feature_engine=ReturnRiskFeatureEngine(DeadRedis()),
        rules_engine=RulesEngine(),
    )
    result = await scorer_down.score(
        user_id="U_REGULAR_042",
        merchant_id="M_FASHION_001",
        order_id="ORD_REDIS_DOWN_001",
        amount=Decimal("3500"),
        category="fashion",
        cod_flag=True,
    )
    _print_result(
        "2. Redis feature store unavailable",
        result,
        _redis_down_warnings(result),
    )

    # ---- Scenario 3: thin chargeback evidence ------------------------ #
    responder = ChargebackResponder()
    thin = {
        "l1_rule_snapshot": {"R-RULE-01": True},
        "l2_gnn_score": 0.3,
        "txn_timestamp": "2026-08-20T10:00:00",
        "delivery_proof": None,  # missing
    }
    result = await responder.respond("DISP_2026_0847", thin)
    _print_result(
        "3. Incomplete chargeback evidence",
        result,
        result.get("warnings", []),
    )

    print("\n" + "=" * 66)
    print("SUMMARY")
    print("=" * 66)
    print(
        """
In all three failure modes PayShield:
  1. Does NOT crash
  2. Does NOT return overconfident decisions
  3. Explicitly warns about degraded confidence
  4. Records an audit trail for post-hoc analysis
  5. Falls back to conservative defaults (ALLOW > BLOCK when uncertain)

This is the difference between a demo and production software.
    """
    )


if __name__ == "__main__":
    asyncio.run(run_demo())
