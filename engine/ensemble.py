import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from engine.constants import Decision, LayerName, L2Status
from configs.config_loader import settings

logger = logging.getLogger(__name__)

try:
    from sklearn.isotonic import IsotonicRegression
    _has_sklearn = True
except ImportError:
    IsotonicRegression = None
    _has_sklearn = False

CALIBRATION_DIR = Path("models/calibration")


@dataclass
class Layer2Result:
    fraud_probability: float = 0.0
    source: str = LayerName.L2_GNN.value
    graph_features: dict | None = None
    latency_ms: float = 0.0
    status: L2Status = L2Status.SUCCESS


@dataclass
class EnsembleResult:
    decision: Literal["ALLOW", "REVIEW", "BLOCK"] = Decision.ALLOW
    confidence: float = 0.0
    source: LayerName = LayerName.L2_GNN
    triggered_rules: list[str] = field(default_factory=list)
    layer1_result: Any = None
    layer2_result: Any = None
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ConfidenceCalibrator:
    def __init__(self):
        self.model = None
        self._fitted = False

    def fit(self, confidences: list[float], labels: list[int]):
        if not _has_sklearn:
            logger.warning("sklearn not available; calibration skipped")
            return
        self.model = IsotonicRegression(out_of_bounds="clip")
        self.model.fit(confidences, labels)
        self._fitted = True
        logger.info(f"Calibrator fitted on {len(confidences)} samples")

    def calibrate(self, confidence: float) -> float:
        if not self._fitted or self.model is None:
            return confidence
        return float(self.model.predict([[confidence]])[0])

    def save(self, path: Path | None = None):
        if not _has_sklearn:
            return
        import joblib
        path = path or CALIBRATION_DIR / "ensemble_calibrator.pkl"
        os.makedirs(path.parent, exist_ok=True)
        joblib.dump(self.model, path)
        logger.info(f"Calibrator saved: {path}")

    def load(self, path: Path | None = None):
        if not _has_sklearn:
            return
        import joblib
        path = path or CALIBRATION_DIR / "ensemble_calibrator.pkl"
        if path.exists():
            self.model = joblib.load(path)
            self._fitted = True
            logger.info(f"Calibrator loaded: {path}")


class EnsembleFusionEngine:
    def __init__(self, layer1_weight: float = 0.3, layer2_weight: float = 0.7,
                 fraud_threshold: float | None = None,
                 calibrator: ConfidenceCalibrator | None = None):
        self.layer1_weight = layer1_weight
        self.layer2_weight = layer2_weight
        self.fraud_threshold = fraud_threshold if fraud_threshold is not None else settings.thresholds.block_probability
        self.calibrator = calibrator or ConfidenceCalibrator()
        self.disagreements: list[dict] = []

    def fuse(self, layer1_result, layer2_result: Layer2Result | None = None) -> EnsembleResult:
        start = time.perf_counter()
        l1_decision = getattr(layer1_result, "decision", "ALLOW")
        l1_rules = getattr(layer1_result, "triggered_rules", [])
        l1_confidence = getattr(layer1_result, "confidence", 0.0)

        if l1_decision == "BLOCK":
            elapsed = (time.perf_counter() - start) * 1000
            return EnsembleResult(
                decision="BLOCK",
                confidence=1.0,
                source=LayerName.L1_STATISTICAL,
                triggered_rules=l1_rules,
                layer1_result=layer1_result,
                latency_ms=round(elapsed, 3),
            )

        l2_prob = layer2_result.fraud_probability if layer2_result else 0.0

        if l1_decision == "ESCALATE":
            boosted_score = min(1.0, l2_prob + 0.15)
            calibrated = self.calibrator.calibrate(boosted_score)
            decision: Literal["ALLOW", "REVIEW", "BLOCK"] = Decision.BLOCK if boosted_score >= self.fraud_threshold else Decision.REVIEW
            elapsed = (time.perf_counter() - start) * 1000
            return EnsembleResult(
                decision=decision,
                confidence=round(calibrated, 4),
                source=LayerName.ENSEMBLE,
                triggered_rules=l1_rules,
                layer1_result=layer1_result,
                layer2_result=layer2_result,
                latency_ms=round(elapsed, 3),
            )

        calibrated = self.calibrator.calibrate(l2_prob)
        if l2_prob >= self.fraud_threshold:
            decision = Decision.BLOCK
        elif l2_prob >= 0.5:
            decision = Decision.REVIEW
        else:
            decision = Decision.ALLOW

        if l1_decision == "ALLOW" and decision == "BLOCK":
            self._log_disagreement(layer1_result, layer2_result, "ALLOW_vs_BLOCK")
        elif l1_decision == "ALLOW" and decision == "REVIEW":
            self._log_disagreement(layer1_result, layer2_result, "ALLOW_vs_REVIEW")

        elapsed = (time.perf_counter() - start) * 1000
        return EnsembleResult(
            decision=decision,
            confidence=round(calibrated, 4),
            source=LayerName.L2_GNN,
            triggered_rules=l1_rules,
            layer1_result=layer1_result,
            layer2_result=layer2_result,
            latency_ms=round(elapsed, 3),
        )

    def _log_disagreement(self, l1, l2, description: str):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "description": description,
            "layer1_decision": getattr(l1, "decision", None),
            "layer2_probability": l2.fraud_probability if l2 else None,
        }
        self.disagreements.append(entry)
        logger.info(f"Disagreement logged: {description}")

    def calibrate(self, confidences: list[float], labels: list[int]):
        self.calibrator.fit(confidences, labels)

    def save_calibrator(self, path: Path | None = None):
        self.calibrator.save(path)

    def load_calibrator(self, path: Path | None = None):
        self.calibrator.load(path)
