import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


DRIFT_THRESHOLDS = {
    "psi": 0.25,
    "false_positive_rate": 0.01,
    "model_age_days": 30,
    "feedback_volume": 1000,
}


class ContinuousImprovementLoop:
    def __init__(self, db_session=None, model_registry=None):
        self._db = db_session
        self._model_registry = model_registry

    def check_retrain_trigger(self) -> dict[str, Any]:
        triggers = {}
        reasons = []

        fp_count = self._get_false_positive_count(hours=24)
        if fp_count > DRIFT_THRESHOLDS["false_positive_rate"] * DRIFT_THRESHOLDS["feedback_volume"]:
            triggers["false_positive_rate"] = fp_count
            reasons.append(f"False positive count ({fp_count}) exceeds threshold")

        psi = self._calculate_psi()
        if psi > DRIFT_THRESHOLDS["psi"]:
            triggers["psi"] = psi
            reasons.append(f"Population Stability Index ({psi:.3f}) exceeds {DRIFT_THRESHOLDS['psi']}")

        model_age = self._get_model_age_days()
        if model_age > DRIFT_THRESHOLDS["model_age_days"]:
            triggers["model_age_days"] = model_age
            reasons.append(f"Model age ({model_age}d) exceeds {DRIFT_THRESHOLDS['model_age_days']}d")

        feedback_count = self._get_feedback_count(hours=24)
        if feedback_count > DRIFT_THRESHOLDS["feedback_volume"]:
            triggers["feedback_volume"] = feedback_count
            reasons.append(f"Feedback volume ({feedback_count}) exceeds {DRIFT_THRESHOLDS['feedback_volume']}")

        return {
            "should_retrain": len(triggers) > 0,
            "triggers": triggers,
            "reasons": reasons,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def trigger_retrain(self) -> str:
        logger.info("Triggering automated retraining...")
        try:
            import subprocess
            result = subprocess.run(
                ["python", "ml/train.py", "--auto", "--base-model", "current_production"],
                capture_output=True, text=True, timeout=3600,
            )
            if result.returncode == 0:
                version = self._parse_version(result.stdout)
                logger.info(f"Retraining complete. New model: {version}")
                return version
            else:
                logger.error(f"Retraining failed: {result.stderr}")
                return ""
        except Exception as e:
            logger.error(f"Retraining error: {e}")
            return ""

    def generate_improvement_report(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_health": self._get_model_health(),
            "data_drift": self._calculate_psi(),
            "feedback_stats": self._get_feedback_stats(),
            "recommendations": self._generate_recommendations(),
        }

    def _get_false_positive_count(self, hours: int = 24) -> int:
        return 0

    def _get_feedback_count(self, hours: int = 24) -> int:
        return 0

    def _calculate_psi(self) -> float:
        return 0.0

    def _get_model_age_days(self) -> float:
        try:
            from ml.registry import ModelRegistry
            registry = ModelRegistry()
            versions = registry.list_versions()
            if versions:
                latest = versions[0]
                created = latest.get("created_at", "")
                if created:
                    created_dt = datetime.fromisoformat(created)
                    return (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
        except Exception:
            pass
        return 0.0

    def _parse_version(self, output: str) -> str:
        for line in output.splitlines():
            if "version" in line.lower() or "v" in line:
                parts = line.strip().split()
                for p in parts:
                    if p.startswith("v") and "." in p:
                        return p
        return "unknown"

    def _get_model_health(self) -> dict:
        return {"status": "unknown", "metrics": {}}

    def _get_feedback_stats(self) -> dict:
        return {"total": 0, "false_positives": 0, "false_negatives": 0}

    def _generate_recommendations(self) -> list[str]:
        return []
