import pytest

from engine.ensemble import (
    ConfidenceCalibrator,
    EnsembleFusionEngine,
    EnsembleResult,
    Layer2Result,
)
from engine.statistical_filter import Layer1Result


class TestEnsembleFusionEngine:
    def test_ensemble_initialization(self):
        ensemble = EnsembleFusionEngine()
        assert ensemble.layer1_weight == 0.3
        assert ensemble.layer2_weight == 0.7
        assert ensemble.fraud_threshold == 0.85

    def test_allows_low_probability(self):
        ensemble = EnsembleFusionEngine()
        l1 = Layer1Result(decision="ALLOW", confidence=0.0)
        l2 = Layer2Result(fraud_probability=0.1)
        result = ensemble.fuse(l1, l2)
        assert result.decision == "ALLOW"
        assert result.source in ("L2_GNN", "ENSEMBLE")

    def test_blocks_high_probability(self):
        ensemble = EnsembleFusionEngine()
        l1 = Layer1Result(decision="ALLOW", confidence=0.0)
        l2 = Layer2Result(fraud_probability=0.95)
        result = ensemble.fuse(l1, l2)
        assert result.decision == "BLOCK"

    def test_l1_block_overrides(self):
        ensemble = EnsembleFusionEngine()
        l1 = Layer1Result(decision="BLOCK", confidence=1.0,
                          triggered_rules=["V-RULE-01"])
        l2 = Layer2Result(fraud_probability=0.0)
        result = ensemble.fuse(l1, l2)
        assert result.decision == "BLOCK"
        assert result.source == "L1_STATISTICAL"

    def test_l1_escalate_boosts(self):
        ensemble = EnsembleFusionEngine(fraud_threshold=1.0)
        l1 = Layer1Result(decision="ESCALATE", confidence=0.6,
                          triggered_rules=["V-RULE-02"])
        l2 = Layer2Result(fraud_probability=0.3)
        result = ensemble.fuse(l1, l2)
        assert result.decision in ("REVIEW", "ALLOW")
        assert result.source == "ENSEMBLE"
        assert result.layer1_result is l1
        assert result.layer2_result is l2

    def test_review_threshold(self):
        ensemble = EnsembleFusionEngine()
        l1 = Layer1Result(decision="ALLOW", confidence=0.0)
        l2 = Layer2Result(fraud_probability=0.6)
        result = ensemble.fuse(l1, l2)
        assert result.decision == "REVIEW"

    def test_ensemble_result_defaults(self):
        r = EnsembleResult()
        assert r.decision == "ALLOW"
        assert r.confidence == 0.0


class TestLayer2Result:
    def test_defaults(self):
        r = Layer2Result()
        assert r.fraud_probability is None
        assert r.source == "L2_GNN"


class TestConfidenceCalibrator:
    def test_unfitted_calibrate_passthrough(self):
        cal = ConfidenceCalibrator()
        assert cal.calibrate(0.7) == 0.7

    def test_fit_then_calibrate_monotone(self):
        cal = ConfidenceCalibrator()
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        labels = [0, 0, 0, 0, 1, 1, 1, 1, 1]
        cal.fit(confidences, labels)
        assert cal._fitted
        calibrated = cal.calibrate(0.5)
        assert 0.0 <= calibrated <= 1.0
        assert cal.calibrate(0.9) >= calibrated

    def test_above_support_passes_through(self):
        cal = ConfidenceCalibrator()
        cal.fit([0.1, 0.2, 0.3], [0, 0, 1])
        assert cal.calibrate(0.99) == 0.99

    def test_save_and_load_roundtrip(self, tmp_path):
        cal = ConfidenceCalibrator()
        cal.fit([0.1, 0.2, 0.3, 0.4], [0, 0, 1, 1])
        path = tmp_path / "calibrator.pkl"
        cal.save(path)
        loaded = ConfidenceCalibrator()
        loaded.load(path)
        assert loaded._fitted
        assert abs(loaded.calibrate(0.25) - cal.calibrate(0.25)) < 1e-6


class TestFusionMath:
    def test_l2_none_falls_back_to_l1(self):
        ensemble = EnsembleFusionEngine(fraud_threshold=0.9)
        l1 = Layer1Result(decision="ALLOW", confidence=0.4)
        result = ensemble.fuse(l1, Layer2Result(fraud_probability=None))
        assert result.confidence == 0.4
        assert result.decision == "ALLOW"

    def test_weighted_fusion_math(self):
        ensemble = EnsembleFusionEngine(layer1_weight=0.3, layer2_weight=0.7, fraud_threshold=0.9)
        l1 = Layer1Result(decision="ALLOW", confidence=0.5)
        l2 = Layer2Result(fraud_probability=0.5)
        result = ensemble.fuse(l1, l2)
        assert result.confidence == pytest.approx(0.5)  # 0.3*0.5 + 0.7*0.5

    def test_l2_floor_keeps_confident_l2(self):
        ensemble = EnsembleFusionEngine(layer1_weight=0.3, layer2_weight=0.7, fraud_threshold=0.9)
        l1 = Layer1Result(decision="ALLOW", confidence=0.0)
        l2 = Layer2Result(fraud_probability=0.8)
        result = ensemble.fuse(l1, l2)
        assert result.confidence == pytest.approx(0.8)

    def test_escalate_forced_review(self):
        ensemble = EnsembleFusionEngine(fraud_threshold=1.0, review_threshold=0.6)
        l1 = Layer1Result(decision="ESCALATE", confidence=0.2, triggered_rules=["V-RULE-02"])
        result = ensemble.fuse(l1, None)
        assert result.decision == "REVIEW"
        assert result.source == "ENSEMBLE"

    def test_disagreement_logged(self):
        ensemble = EnsembleFusionEngine(fraud_threshold=0.85)
        l1 = Layer1Result(decision="ALLOW", confidence=0.0)
        l2 = Layer2Result(fraud_probability=0.9)
        ensemble.fuse(l1, l2)
        assert len(ensemble.disagreements) == 1
        assert ensemble.disagreements[0]["description"] == "ALLOW_vs_BLOCK"
