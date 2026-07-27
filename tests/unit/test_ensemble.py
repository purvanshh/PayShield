import pytest

from engine.ensemble import EnsembleFusionEngine, EnsembleResult, Layer2Result
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
        assert r.fraud_probability == 0.0
        assert r.source == "L2_GNN"
