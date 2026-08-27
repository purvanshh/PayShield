"""Track 2 risk-suite reflection — methods added to ReflectionAgent.

The nightly reflection loop gains two analyses: return-risk scoring
accuracy against actual return outcomes, and chargeback rebuttal outcomes.
Both run over an injected record list (in production: the outcomes store;
in tests: fake records), so the logic is deterministic and unit-testable.
"""

from typing import Any

HIGH_PRECISION_FLOOR = 0.70
REJECT_LOSS_RATIO_FLOOR = 0.30

DEFAULT_HIGH_THRESHOLD = 0.70
RECOMMENDED_HIGH_THRESHOLD = 0.75


def analyze_return_risk_accuracy(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Precision/recall of the HIGH tier against actual return labels.

    ``records`` items: {"risk_tier", "returned", "user_type"}. Null tier /
    returned values are skipped. Returns counts, HIGH precision,
    ``tier_misses`` (returned orders not flagged HIGH) and
    ``false_positives`` (HIGH flags that never returned).
    """
    high_total = 0
    high_returned = 0
    misses = 0
    misses_by_type: dict[str, int] = {}
    false_positives = 0
    for rec in records:
        tier = rec.get("risk_tier")
        returned = rec.get("returned")
        if tier is None or returned is None:
            continue
        if tier == "HIGH":
            high_total += 1
            if returned:
                high_returned += 1
            else:
                false_positives += 1
        elif returned:
            # returned but not flagged HIGH -> a tier miss
            user_type = rec.get("user_type", "unknown")
            misses += 1
            misses_by_type[user_type] = misses_by_type.get(user_type, 0) + 1

    precision = high_returned / high_total if high_total else 0.0
    return {
        "high_risk_total": high_total,
        "high_risk_returned": high_returned,
        "high_risk_precision": round(precision, 4),
        "tier_misses": misses,
        "misses_by_user_type": misses_by_type,
        "false_positives": false_positives,
    }


def analyze_chargeback_outcomes(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Outcome matrix by response type.

    ``records`` items: {"response_type", "outcome", "count"}.
    """
    matrix = [
        {
            "response": rec.get("response_type", ""),
            "outcome": rec.get("outcome", ""),
            "count": int(rec.get("count", 0) or 1),
        }
        for rec in records
        if rec.get("response_type") and rec.get("outcome")
    ]
    return {"outcome_matrix": matrix}


def generate_risk_suite_recommendations(
    return_accuracy: dict[str, Any], chargeback_outcomes: dict[str, Any], drift_detected: bool = False
) -> list[dict[str, Any]]:
    """Turn the analyses into actionable recommendations."""
    recommendations: list[dict[str, Any]] = []

    precision = float(return_accuracy.get("high_risk_precision", 1.0))
    if 0.0 < precision < HIGH_PRECISION_FLOOR:
        recommendations.append(
            {
                "type": "threshold_adjustment",
                "target": "return_risk.risk_tiers.HIGH.max_score",
                "current": DEFAULT_HIGH_THRESHOLD,
                "recommended": RECOMMENDED_HIGH_THRESHOLD,
                "reason": f"HIGH-tier precision {precision:.2f} below the {HIGH_PRECISION_FLOOR:.2f} floor",
            }
        )

    matrix = chargeback_outcomes.get("outcome_matrix", [])
    reject_total = sum(1 for o in matrix if o["response"] == "REJECT")
    reject_lost = sum(1 for o in matrix if o["response"] == "REJECT" and o["outcome"] == "lost")
    if reject_total and reject_lost / reject_total > REJECT_LOSS_RATIO_FLOOR:
        recommendations.append(
            {
                "type": "strategy_adjustment",
                "target": "chargeback.response_type",
                "current": "REJECT when completeness > 0.8",
                "recommended": "REJECT when completeness > 0.9",
                "reason": f"{reject_lost}/{reject_total} REJECT responses were lost",
            }
        )

    if drift_detected:
        recommendations.append(
            {
                "type": "retraining",
                "target": "return_risk.feature_weights",
                "reason": "Feature drift detected in return-risk profile inputs",
            }
        )

    return recommendations


def build_risk_suite_reflection(
    return_records: list[dict[str, Any]],
    chargeback_records: list[dict[str, Any]],
    drift_detected: bool = False,
) -> dict[str, Any]:
    """One-shot reflection payload for the risk suite (also usable standalone)."""
    accuracy = analyze_return_risk_accuracy(return_records)
    outcomes = analyze_chargeback_outcomes(chargeback_records)
    recommendations = generate_risk_suite_recommendations(accuracy, outcomes, drift_detected)
    return {
        "return_risk": accuracy,
        "chargeback": outcomes,
        "drift_detected": drift_detected,
        "recommendations": recommendations,
    }
