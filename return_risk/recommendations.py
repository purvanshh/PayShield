"""Return-risk recommendation texts (Track 02 - Phase 8).

Maps a rule/action keyword (from configs/return_risk_rules.yaml) to the
merchant-facing recommendation strings returned by /v1/return/score.
"""

ACTION_RECOMMENDATIONS = {
    "ACCEPT": ["Proceed with checkout"],
    "FLAG_FOR_REVIEW": [
        "Flag order for manual review before dispatch",
        "Send return policy reminder at checkout",
    ],
    "REQUIRE_PREPAID": [
        "Require prepaid payment (no COD) for this user",
        "Flag order for manual review before dispatch",
        "Send return policy reminder at checkout",
    ],
    "REQUIRE_PREPAID_ONLY": [
        "Require prepaid payment (no COD) for this user",
        "Send return policy reminder at checkout",
    ],
    "CAP_QUANTITY_2": [
        "Cap quantity to 2 units for this order",
        "Send return policy reminder at checkout",
    ],
}

RULE_ACTION_HINTS = {
    "FLAG_FOR_REVIEW": "Flag order for manual review before dispatch",
    "REQUIRE_PREPAID_ONLY": "Require prepaid payment (no COD) for this user",
    "CAP_QUANTITY_2": "Cap quantity to 2 units for this order",
}


def recommendations_for_action(action: str) -> list[str]:
    """Return the recommendation texts for a risk-tier / rule action."""
    return list(ACTION_RECOMMENDATIONS.get(action, []))


def recommendation_for_rule(rule_action: str) -> str | None:
    """Single-line hint for a fired rule (used by Phase 14 rules engine)."""
    return RULE_ACTION_HINTS.get(rule_action)
