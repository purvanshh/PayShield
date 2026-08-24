"""Return-risk rules engine (Track 02 - Phase 14).

Config-driven rule evaluation for return-risk scoring, following the same
pattern as ``engine/statistical_filter.py`` but with return-specific rules
and merchant-actionable actions (``FLAG_FOR_REVIEW``, ``REQUIRE_PREPAID``,
``BLOCK_COD``, ``ACCEPT``).

Conditions are Python expressions from YAML evaluated with a restricted
scope: only whitelisted builtins plus the flattened feature names - no
``__builtins__``, no config-file code injection. A rule that fails to
evaluate degrades to an error entry instead of crashing the whole score.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RULES_PATH = Path("configs/return_risk_rules.yaml")

_SAFE_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    "bool": bool,
    "Decimal": Decimal,
}


@dataclass
class ReturnRule:
    """A single return-risk rule definition."""

    rule_id: str
    name: str
    condition: str = ""
    action: str = "FLAG_FOR_REVIEW"
    severity: int = 3
    description: str = ""
    enabled: bool = True
    extras: dict[str, Any] = field(default_factory=dict)


class RulesEngine:
    """Evaluates the config-driven rule catalogue against features."""

    def __init__(self, rules_path: Path | str = DEFAULT_RULES_PATH):
        self.rules_path = Path(rules_path)
        self.rules: list[ReturnRule] = []
        self.risk_tiers: dict[str, dict[str, Any]] = {}
        self.operating_point: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.rules_path.exists():
            return
        with open(self.rules_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        kept = ("rule_id", "name", "condition", "action", "severity", "description", "enabled")
        self.rules = [
            ReturnRule(
                rule_id=r["rule_id"],
                name=r.get("name", r["rule_id"]),
                condition=r.get("condition", ""),
                action=r.get("action", "FLAG_FOR_REVIEW"),
                severity=int(r.get("severity", 3)),
                description=r.get("description", ""),
                enabled=bool(r.get("enabled", True)),
                extras={k: v for k, v in r.items() if k not in kept},
            )
            for r in data.get("rules", [])
        ]
        self.risk_tiers = data.get("risk_tiers", {})
        self.operating_point = data.get("operating_point", {})

    def reload_rules(self) -> None:
        """Reload rules from the configured YAML file."""
        self.rules = []
        self.risk_tiers = {}
        self.operating_point = {}
        self._load()

    def get_rule_by_id(self, rule_id: str) -> ReturnRule | None:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    # ------------------------------------------------------------------ #

    def evaluate(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate all enabled rules against the feature set.

        Returns triggered rules sorted by severity (highest first), plus
        error entries for rules that could not be evaluated.
        """
        flat = self._flatten_features(features)
        triggers: list[dict[str, Any]] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            try:
                result = _safe_eval(rule.condition, flat)
            except Exception as e:
                triggers.append(
                    {
                        "rule_id": rule.rule_id,
                        "name": rule.name,
                        "error": str(e),
                        "triggered": False,
                    }
                )
                continue
            if result:
                triggers.append(
                    {
                        "rule_id": rule.rule_id,
                        "name": rule.name,
                        "description": rule.description,
                        "condition": rule.condition,
                        "action": rule.action,
                        "severity": rule.severity,
                        "triggered": True,
                    }
                )
        triggers.sort(key=lambda t: t.get("severity", 0), reverse=True)
        return triggers

    @staticmethod
    def _flatten_features(features: dict[str, Any]) -> dict[str, Any]:
        """Extract raw values from ``{"value", "source"}`` feature dicts."""
        flat = {}
        for key, value in features.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict) and "value" in value:
                flat[key] = value["value"]
            else:
                flat[key] = value
        return flat


def _safe_eval(condition: str, features: dict[str, Any]) -> bool:
    """Evaluate a rule condition against features with a restricted scope."""
    scope = {**_SAFE_BUILTINS, **features}
    return bool(eval(condition, {"__builtins__": {}}, scope))  # nosec B307 - whitelisted scope (no builtins, no config); conditions are repo YAML, never user input  # noqa: S307
