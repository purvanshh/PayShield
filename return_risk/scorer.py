"""Return-risk scorer (Track 02 - Phase 15).

Main scoring engine: feature extraction -> rule evaluation -> weighted
composite score -> risk tier -> actionable recommendations -> honest
confidence. The score is transparent: every feature's value, normalised
value, weight and contribution is reported, so 0.73 can be explained
down to the penny.

Weights are loaded from ``configs/feature_registry_return.yaml`` (falling
back to the tuned defaults below when the registry is empty); risk tiers
come from ``configs/return_risk_rules.yaml``.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from return_risk.feature_engine import FeatureRegistry, ReturnRiskFeatureEngine
from return_risk.rules_engine import RulesEngine

FEATURE_WEIGHTS = {
    "user_return_rate_30d": 0.25,
    "user_serial_returner_flag": 0.20,
    "merchant_return_rate_30d": 0.15,
    "txn_category_return_baseline": 0.15,
    "txn_amount_risk": 0.10,
    "user_cod_refusal_rate": 0.10,
    "user_return_velocity_7d": 0.05,
}

RISK_TIERS = {
    "LOW": {"max_score": 0.30, "action": "ACCEPT"},
    "MEDIUM": {"max_score": 0.70, "action": "FLAG_FOR_REVIEW"},
    "HIGH": {"max_score": 1.00, "action": "REQUIRE_PREPAID"},
}

CRITICAL_FEATURES = [
    "user_return_rate_30d",
    "merchant_return_rate_30d",
    "txn_category_return_baseline",
]

# Rule-based score adjustments (Phase 15 design note): rules carry domain
# knowledge - a proven COD-refusal pattern, a serial-returner flag, a
# velocity spike - which is why fired rules nudge the composite rather than
# only flagging. Total adjustment is capped so stacking rules never drowns
# the weighted signal.
RULE_BOOST = {
    "R-RULE-01": 0.15,  # serial returner
    "R-RULE-02": 0.10,  # high-value fashion order
    "R-RULE-03": 0.15,  # COD refusal pattern
    "R-RULE-04": 0.05,  # return velocity spike
    "R-RULE-05": 0.10,  # new user high value
    "R-RULE-08": -0.05,  # low-risk profile (reduces score)
}
BOOST_CAP = 0.25


class ReturnRiskScorer:
    """Combines features, rules and weights into a return-risk assessment."""

    def __init__(
        self,
        feature_engine: ReturnRiskFeatureEngine | None = None,
        rules_engine: RulesEngine | None = None,
        registry: FeatureRegistry | None = None,
    ):
        self.registry = registry or FeatureRegistry()
        if feature_engine is None:
            import warnings

            warnings.warn(
                "ReturnRiskScorer without feature_engine: only registry/tier helpers usable; "
                "call score() only for introspection tests",
                stacklevel=2,
            )
        self.feature_engine = feature_engine
        self.rules_engine = rules_engine or RulesEngine()

        weighted = self.registry.composite_weights or {}
        self.weights: dict[str, float] = weighted or dict(FEATURE_WEIGHTS)
        self.risk_tiers: dict[str, dict[str, Any]] = (
            self.rules_engine.risk_tiers or dict(RISK_TIERS)
        )

    # ------------------------------------------------------------------ #
    # pipeline                                                            #
    # ------------------------------------------------------------------ #

    async def score(
        self,
        user_id: str,
        merchant_id: str,
        order_id: str,
        amount: Decimal,
        category: str,
        cod_flag: bool,
        payment_method: str = "UPI",  # noqa: ARG002 - API contract parity
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Score an order for return-risk.

        Returns the complete assessment: score, tier, feature breakdown
        (value/weight/contribution/source), triggered rules, recommendations,
        user profile and confidence.
        """
        if self.feature_engine is None:
            raise ValueError("ReturnRiskScorer requires a feature engine to score orders")

        timestamp = timestamp or datetime.utcnow()
        features = await self.feature_engine.extract_features(
            user_id=user_id,
            merchant_id=merchant_id,
            category=category,
            amount=amount,
            cod_flag=cod_flag,
            timestamp=timestamp,
        )

        rules_triggered = self.rules_engine.evaluate(features)
        score, breakdown = self._compute_score(features, rules_triggered)
        risk_tier = self._determine_tier(score)
        recommendations = self._generate_recommendations(risk_tier, rules_triggered, features)
        confidence = self._calculate_confidence(features)
        user_profile = self._build_user_profile(features)

        return {
            "order_id": order_id,
            "return_risk_score": round(score, 4),
            "risk_tier": risk_tier,
            "confidence": round(confidence, 4),
            "feature_breakdown": breakdown,
            "rules_triggered": rules_triggered,
            "recommendations": recommendations,
            "user_profile": user_profile,
            "scored_at": timestamp.isoformat(),
        }

    def _compute_score(
        self, features: dict[str, Any], rules_triggered: list[dict[str, Any]]
    ) -> tuple[float, dict[str, dict[str, Any]]]:
        """Weighted composite score with per-feature contributions.

        The weighted sum carries the signal; fired domain rules nudge it
        (capped) so stacked-risk profiles land in the right tier.
        """
        score = 0.0
        breakdown = {}

        for feature_name, weight in self.weights.items():
            feature_data = features.get(feature_name, {})
            raw_value = feature_data.get("value", 0) if isinstance(feature_data, dict) else 0
            source = feature_data.get("source", "unknown") if isinstance(feature_data, dict) else "missing"

            normalized_value = self._normalize_feature(feature_name, raw_value)
            contribution = normalized_value * weight
            score += contribution

            breakdown[feature_name] = {
                "value": raw_value,
                "normalized_value": round(normalized_value, 4),
                "weight": weight,
                "contribution": round(contribution, 4),
                "source": source,
            }

        score += self.promotion_score(rules_triggered)
        score = max(0.0, min(1.0, score))
        return score, breakdown

    @staticmethod
    def promotion_score(rules_triggered: list[dict[str, Any]]) -> float:
        """Post-contribution adjustment from fired rules (capped, [-0.05, +0.25])."""
        boost = sum(RULE_BOOST.get(r.get("rule_id", ""), 0.0) for r in rules_triggered if r.get("triggered"))
        return max(-0.05, min(BOOST_CAP, boost))

    @staticmethod
    def _normalize_feature(feature_name: str, value: Any) -> float:
        """Map a raw feature value into the [0, 1] contribution space."""
        if feature_name == "user_serial_returner_flag":
            return 1.0 if value else 0.0
        if feature_name == "user_return_velocity_7d":
            return min(1.0, float(value) / 5.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _determine_tier(self, score: float) -> str:
        for tier in ("LOW", "MEDIUM", "HIGH"):
            max_score = float(self.risk_tiers.get(tier, {}).get("max_score", 1.0))
            if score <= max_score:
                return tier
        return "HIGH"

    @staticmethod
    def _generate_recommendations(
        tier: str,
        rules: list[dict[str, Any]],
        features: dict[str, Any],
    ) -> list[str]:
        recommendations = []

        if tier == "HIGH":
            recommendations += [
                "Require prepaid payment (no COD) for this user",
                "Flag order for manual review before dispatch",
                "Require signature on delivery",
            ]
        elif tier == "MEDIUM":
            recommendations += [
                "Flag order for manual review before dispatch",
                "Send return policy reminder at checkout",
            ]
        else:
            recommendations.append("Standard processing - no additional measures required")

        for rule in rules:
            if not rule.get("triggered"):
                continue
            if rule.get("rule_id") == "R-RULE-03":
                recommendations.append("Block COD for this user - require prepaid payment")
            elif rule.get("rule_id") == "R-RULE-04":
                recommendations.append("Temporarily limit order frequency for this user")
            elif rule.get("rule_id") == "R-RULE-05":
                recommendations.append("Verify phone number and email before dispatch")

        cod = features.get("txn_cod_flag", {}).get("value", False)
        if cod and tier in ("MEDIUM", "HIGH"):
            recommendations.append("Consider converting COD to prepaid with discount incentive")

        return sorted(set(recommendations))

    @staticmethod
    def _calculate_confidence(features: dict[str, Any]) -> float:
        """Confidence drops for new users, default-sourced features and gaps."""
        confidence = 1.0

        if features.get("user_is_new", {}).get("value", False):
            confidence -= 0.3

        default_count = sum(
            1
            for f in features.values()
            if isinstance(f, dict) and f.get("source", "").startswith("default")
        )
        confidence -= default_count * 0.05

        missing = sum(1 for name in CRITICAL_FEATURES if name not in features)
        confidence -= missing * 0.1

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _build_user_profile(features: dict[str, Any]) -> dict[str, Any]:
        def _value(name: str, default: Any = 0) -> Any:
            return features.get(name, {}).get("value", default)

        return {
            "total_orders": _value("user_total_orders"),
            "total_returns": _value("user_total_returns"),
            "return_rate_30d": _value("user_return_rate_30d"),
            "return_rate_lifetime": _value("user_return_rate_lifetime"),
            "avg_return_value": _value("user_avg_return_value"),
            "serial_returner": _value("user_serial_returner_flag", False),
            "is_new_user": _value("user_is_new", False),
        }

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #

    def weights_sum(self) -> float:
        return round(sum(self.weights.values()), 4)

    def tier_for(self, score: float) -> str:
        """Map a score in [0,1] to LOW/MEDIUM/HIGH (tier introspection)."""
        return self._determine_tier(score)

    def action_for(self, score: float) -> str:
        tier = self.tier_for(score)
        return str(self.risk_tiers.get(tier, {}).get("action", "FLAG_FOR_REVIEW"))

    @staticmethod
    def normalize_features(features: dict[str, Any], registry: FeatureRegistry) -> dict[str, float]:
        """Clamp features to declared [min_val, max_val] range (debug helper)."""
        normalized = {}
        for record in registry.features:
            name = record.get("name")
            if name not in features:
                continue
            value = float(features[name])
            lo = float(record.get("min_val", 0.0))
            hi = float(record.get("max_val", 1.0))
            normalized[name] = max(lo, min(hi, value))
        return normalized
