"""Return-risk rules engine (Track 02 - Phases 8/14).

Phase 8: loads the R-RULE-* definitions from
``configs/return_risk_rules.yaml`` into :class:`ReturnRule` records so the
scorer pipeline (Phase 14) can evaluate them without re-parsing YAML.

Evaluation of conditions (``evaluate()``) lands in Phase 14 alongside the
feature engine; the *condition strings* are documented in the YAML and match
the feature names in ``configs/feature_registry_return.yaml``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RULES_PATH = Path("configs/return_risk_rules.yaml")


@dataclass
class ReturnRule:
    rule_id: str
    name: str
    condition: str
    action: str
    severity: int = 3
    description: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


class RulesEngine:
    """Holds the rule catalogue for the return-risk scorer."""

    def __init__(self, rules_path: Path | str = DEFAULT_RULES_PATH):
        self.rules_path = Path(rules_path)
        self.rules: list[ReturnRule] = []
        self.risk_tiers: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if not self.rules_path.exists():
            return
        with open(self.rules_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.rules = [
            ReturnRule(
                rule_id=r["rule_id"],
                name=r.get("name", r["rule_id"]),
                condition=r.get("condition", ""),
                action=r.get("action", "FLAG_FOR_REVIEW"),
                severity=int(r.get("severity", 3)),
                description=r.get("description", ""),
                extras={k: v for k, v in r.items() if k not in ("rule_id", "name", "condition", "action", "severity", "description")},
            )
            for r in data.get("rules", [])
        ]
        self.risk_tiers = data.get("risk_tiers", {})

    def get(self, rule_id: str) -> ReturnRule | None:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None
