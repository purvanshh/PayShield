import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)


class ExperimentType(str, enum.Enum):
    MODEL_CHALLENGER = "MODEL_CHALLENGER"
    RULE_UPDATE = "RULE_UPDATE"
    THRESHOLD_TUNING = "THRESHOLD_TUNING"
    FEATURE_ABLATION = "FEATURE_ABLATION"


class ExperimentStatus(str, enum.Enum):
    SHADOW = "shadow"
    CANARY = "canary"
    A_B = "a_b"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class Experiment:
    experiment_id: str = ""
    name: str = ""
    experiment_type: str = ExperimentType.MODEL_CHALLENGER
    champion_version: str = ""
    challenger_version: str = ""
    traffic_split: float = 0.0
    status: str = ExperimentStatus.SHADOW
    start_date: str = ""
    end_date: str = ""
    created_by: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExperimentResult:
    experiment_id: str
    champion_metrics: dict[str, float] = field(default_factory=dict)
    challenger_metrics: dict[str, float] = field(default_factory=dict)
    p_value: float = 1.0
    statistically_significant: bool = False
    winner: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ABTestFramework:
    def __init__(self, db_session=None):
        self._db = db_session
        self._experiments: dict[str, Experiment] = {}
        self._active_experiment: Experiment | None = None

    def register_experiment(self, name: str, challenger_version: str,
                            traffic_split: float = 0.0,
                            duration_days: int = 14,
                            experiment_type: str = ExperimentType.MODEL_CHALLENGER,
                            champion_version: str = "",
                            created_by: str = "system") -> Experiment:
        if self._active_experiment and traffic_split > 0.0:
            raise RuntimeError(
                f"Active experiment '{self._active_experiment.name}' in progress. "
                "Maximum 1 active A/B test at a time."
            )

        if traffic_split < 0.0 or traffic_split > 1.0:
            raise ValueError("traffic_split must be between 0 and 1")

        experiment = Experiment(
            experiment_id=str(uuid.uuid4()),
            name=name,
            experiment_type=experiment_type,
            champion_version=champion_version,
            challenger_version=challenger_version,
            traffic_split=traffic_split,
            status=ExperimentStatus.SHADOW if traffic_split == 0.0 else ExperimentStatus.CANARY,
            start_date=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if traffic_split > 0.0:
            self._active_experiment = experiment

        self._experiments[experiment.experiment_id] = experiment
        logger.info(f"Registered experiment: {name} ({experiment.experiment_id}) "
                    f"challenger={challenger_version} split={traffic_split}")
        return experiment

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        return self._experiments.get(experiment_id)

    def list_experiments(self) -> list[Experiment]:
        return list(self._experiments.values())

    def update_status(self, experiment_id: str, status: ExperimentStatus):
        exp = self._experiments.get(experiment_id)
        if exp:
            exp.status = status
            if status in (ExperimentStatus.PROMOTED, ExperimentStatus.ROLLED_BACK, ExperimentStatus.FAILED):
                exp.end_date = datetime.now(timezone.utc).isoformat()
                if exp == self._active_experiment:
                    self._active_experiment = None
            logger.info(f"Experiment {experiment_id} status updated to {status}")

    def evaluate_experiment(self, experiment_id: str) -> ExperimentResult:
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment not found: {experiment_id}")

        champion_scores = self._get_model_scores(exp.champion_version)
        challenger_scores = self._get_model_scores(exp.challenger_version)

        champion_metrics = self._compute_metrics(champion_scores)
        challenger_metrics = self._compute_metrics(challenger_scores)

        t_stat, p_value = scipy_stats.ttest_ind(
            champion_scores.get("fvar", [0]),
            challenger_scores.get("fvar", [0]),
            equal_var=False,
        )

        significant = p_value < 0.05
        winner = ""
        if significant:
            champ_fvar = np.mean(champion_scores.get("fvar", [0]))
            chall_fvar = np.mean(challenger_scores.get("fvar", [0]))
            winner = exp.challenger_version if chall_fvar < champ_fvar else exp.champion_version

        recommendation = ""
        if significant:
            if winner == exp.challenger_version:
                recommendation = "Challenger outperforms champion with statistical significance. Recommend promotion."
            else:
                recommendation = "Champion outperforms challenger. No action needed."
        else:
            recommendation = "No statistically significant difference detected. Continue experiment or consider longer duration."

        return ExperimentResult(
            experiment_id=experiment_id,
            champion_metrics=champion_metrics,
            challenger_metrics=challenger_metrics,
            p_value=p_value,
            statistically_significant=significant,
            winner=winner,
            recommendation=recommendation,
        )

    def promote(self, experiment_id: str) -> None:
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment not found: {experiment_id}")

        if exp.status not in (ExperimentStatus.A_B, ExperimentStatus.CANARY):
            raise ValueError(f"Cannot promote experiment in status: {exp.status}")

        from ml.registry import ModelRegistry
        registry = ModelRegistry()
        registry.promote(exp.challenger_version, "production")

        self.update_status(experiment_id, ExperimentStatus.PROMOTED)
        logger.info(f"Promoted challenger {exp.challenger_version} to production")

    def rollback(self, experiment_id: str) -> None:
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment not found: {experiment_id}")

        from ml.registry import ModelRegistry
        registry = ModelRegistry()
        registry.rollback(exp.champion_version)

        self.update_status(experiment_id, ExperimentStatus.ROLLED_BACK)
        logger.info(f"Rolled back to champion {exp.champion_version}")

    def _get_model_scores(self, version: str) -> dict[str, list[float]]:
        return {
            "fvar": list(np.random.randn(100) * 0.1 + 0.5),
            "precision": list(np.random.rand(100) * 0.1 + 0.85),
            "recall": list(np.random.rand(100) * 0.1 + 0.88),
        }

    def _compute_metrics(self, scores: dict[str, list[float]]) -> dict[str, float]:
        return {
            "fvar_mean": float(np.mean(scores.get("fvar", [0]))),
            "fvar_std": float(np.std(scores.get("fvar", [0]))),
            "precision_mean": float(np.mean(scores.get("precision", [0]))),
            "recall_mean": float(np.mean(scores.get("recall", [0]))),
        }


class ExperimentGuardrails:
    MAX_ACTIVE_A_B_TESTS = 1
    MIN_SHADOW_DAYS = 7
    MIN_SAMPLE_SIZE = 100_000
    AUTO_ROLLBACK_LATENCY_INCREASE = 0.20
    AUTO_ROLLBACK_ERROR_RATE = 0.001

    @staticmethod
    def validate_experiment(experiment: Experiment) -> list[str]:
        violations = []
        if experiment.traffic_split > 0.1 and experiment.created_by != "admin":
            violations.append("Traffic split > 10% requires admin approval")
        return violations

    @staticmethod
    def should_auto_rollback(experiment: Experiment, current_latency_p99: float,
                             baseline_latency_p99: float, current_error_rate: float) -> bool:
        if baseline_latency_p99 > 0:
            latency_increase = (current_latency_p99 - baseline_latency_p99) / baseline_latency_p99
            if latency_increase > ExperimentGuardrails.AUTO_ROLLBACK_LATENCY_INCREASE:
                logger.warning(f"Auto-rollback: latency increased {latency_increase:.1%}")
                return True
        if current_error_rate > ExperimentGuardrails.AUTO_ROLLBACK_ERROR_RATE:
            logger.warning(f"Auto-rollback: error rate {current_error_rate:.4f} > threshold")
            return True
        return False


class RuleABTesting:
    def __init__(self):
        self._shadow_rules: dict[str, dict] = {}

    def register_rule(self, rule_id: str, rule_config: dict):
        self._shadow_rules[rule_id] = {
            "config": rule_config,
            "evaluations": 0,
            "agreements": 0,
            "disagreements": 0,
            "false_positives": 0,
        }
        logger.info(f"Registered shadow rule: {rule_id}")

    def evaluate(self, rule_id: str, existing_decision: dict, proposed_decision: dict) -> dict:
        shadow = self._shadow_rules.get(rule_id)
        if not shadow:
            return {"action": "pass", "reason": "Rule not in shadow mode"}

        shadow["evaluations"] += 1

        if existing_decision.get("action") == proposed_decision.get("action"):
            shadow["agreements"] += 1
            return {"action": "agree", "reason": "Both rules agree"}
        else:
            shadow["disagreements"] += 1
            disagreement = {
                "action": "disagree",
                "existing": existing_decision["action"],
                "proposed": proposed_decision["action"],
                "evaluations": shadow["evaluations"],
                "disagreement_rate": shadow["disagreements"] / shadow["evaluations"],
            }
            if proposed_decision.get("action") == "BLOCK" and shadow["disagreements"] > 100:
                fp_risk = shadow["false_positives"] / max(shadow["disagreements"], 1)
                if fp_risk < 0.05:
                    disagreement["recommendation"] = "Consider promoting rule"
            return disagreement

    def get_stats(self, rule_id: str) -> dict:
        return self._shadow_rules.get(rule_id, {})
