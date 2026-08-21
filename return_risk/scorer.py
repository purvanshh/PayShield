"""Return-risk scorer (Track 02 - Phases 8/15).

Phase 8: loads the composite weight map and risk-tier thresholds from
configs/return_risk_rules.yaml + feature registry so the pipeline can be
assembled. The full scoring pipeline (extract -> rules -> weighted sum ->
tier) is implemented in Phase 15.
"""

from pathlib import Path
from typing import Any

import yaml

from return_risk.feature_engine import FeatureRegistry
from return_risk.rules_engine import RulesEngine, ReturnRule


class ReturnRiskScorer:
    """Shell of the scorer.

    Constructed with live ``FeatureRegistry`` and ``RulesEngine`` instances so
    Phase 15 only adds the ``score()`` orchestration method.
    """

    def __init__(
        self,
        registry: FeatureRegistry | None = None,
        rules: RulesEngine | None = None,
        rules_path: Path | str = "configs/return_risk_rules.yaml",
    ):
        self.registry = registry or FeatureRegistry()
        self.rules_engine = rules or RulesEngine(rules_path)
        self.weights = self.registry.composite_weights
        self.risk_tiers: dict[str, dict[str, Any]] = self.rules_engine.risk_tiers

    def weights_sum(self) -> float:
        return round(sum(self.weights.values()), 4)

    def tier_for(self, score: float) -> str:
        """Map a score in [0,1] to LOW/MEDIUM/HIGH from the configured tiers."""
        for tier in ("LOW", "MEDIUM", "HIGH"):
            config = self.risk_tiers.get(tier)
            if config and score <= float(config.get("max_score", 1.0)):
                return tier
        return "HIGH"

    def action_for(self, score: float) -> str:
        tier = self.tier_for(score)
        config = self.risk_tiers.get(tier, {})
        return str(config.get("action", "FLAG_FOR_REVIEW"))

    @staticmethod
    def normalize_features(features: dict[str, Any], registry: FeatureRegistry) -> dict[str, float]:
        """Clamp each feature to its declared [min_val, max_val] range.

        Later wired into the Phase 15 pipeline; exposed here so weights/tiers
        can be unit-tested without a Redis connection.
        """
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
