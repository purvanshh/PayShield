"""Unit tests for the LLM investigation pipeline: narrative parsing,
fallback generation, and the Celery task itself (all external calls mocked).
"""
# ruff: noqa: ARG001, ARG002, ARG005 -- test doubles mirror the client interface

import json

import pytest

from llm.parser import FallbackGenerator, NarrativeParser
from tests.fake_redis import FakeSyncRedis

GOOD_JSON = json.dumps({
    "narrative": "User sent 6 transactions of 10000 INR to a single beneficiary "
                 "within 5 minutes, matching a mule-ring pattern.",
    "fraud_type": "MULE_RING",
    "confidence": "HIGH",
    "recommended_action": "BLOCK",
    "reasoning": "Velocity burst and single-beneficiary clustering detected.",
    "key_evidence": [
        "6 transactions in 5 minutes",
        "Same beneficiary for all transfers",
    ],
})


class TestNarrativeParser:
    def test_parses_valid_json(self):
        report = NarrativeParser().parse(GOOD_JSON, txn_id="TXN1")
        assert report.txn_id == "TXN1"
        assert report.fraud_type == "MULE_RING"
        assert report.recommended_action == "BLOCK"
        assert report.confidence == "HIGH"
        assert len(report.key_evidence) == 2

    def test_handles_wrapped_json(self):
        wrapped = "Here is the analysis:\n```json\n" + GOOD_JSON + "\n```\nDone."
        report = NarrativeParser().parse(wrapped)
        assert report.fraud_type == "MULE_RING"

    def test_tolerates_trailing_comma(self):
        malformed = GOOD_JSON[:-1] + ',"extra": 1}'
        report = NarrativeParser().parse(malformed)
        assert report.recommended_action == "BLOCK"

    def test_falls_back_to_key_value(self):
        raw = (
            "Fraud Type: BURST_ATTACK\n"
            "Confidence: MEDIUM\n"
            "Recommended Action: REVIEW\n"
            "Narrative: Rapid successive transactions from the same device.\n"
        )
        report = NarrativeParser().parse(raw)
        assert report.fraud_type == "BURST_ATTACK"
        assert report.recommended_action == "REVIEW"
        assert report.confidence == "MEDIUM"
        assert len(report.narrative) > 20

    def test_invalid_values_coerce_to_defaults(self):
        raw = json.dumps({
            "narrative": "A sufficiently long narrative to pass validation.",
            "fraud_type": "NOT_A_TYPE",
            "confidence": "EXTREME",
            "recommended_action": "UNKNOWN",
            "key_evidence": ["one"],
        })
        report = NarrativeParser().parse(raw)
        assert report.fraud_type == "OTHER"
        assert report.confidence == "LOW"
        assert report.recommended_action == "ALLOW"

    def test_less_conservative_action_flagged(self, caplog):
        raw = json.dumps({
            "narrative": "A sufficiently long narrative to pass validation with "
                         "some detail and reasoning included for the quality check.",
            "fraud_type": "BURST_ATTACK",
            "confidence": "HIGH",
            "recommended_action": "ALLOW",
            "key_evidence": ["evidence one", "evidence two"],
        })
        report = NarrativeParser().parse(raw, expected_action="BLOCK")
        assert report.recommended_action == "ALLOW"
        assert report.quality_score < 0.5

    def test_quality_scoring(self):
        report = NarrativeParser().parse(GOOD_JSON)
        assert 0.0 <= report.quality_score <= 1.0
        assert report.quality_score > 0.5

    def test_to_dict_roundtrip(self):
        report = NarrativeParser().parse(GOOD_JSON, txn_id="TXN1")
        data = report.to_dict()
        assert data["fraud_type"] == "MULE_RING"
        assert data["txn_id"] == "TXN1"


class TestFallbackGenerator:
    def test_generates_report_without_ollama(self):
        context = type("Ctx", (), {
            "txn_id": "TXN_FB",
            "evidence_items": [
                type("E", (), {"type": "BENFORD", "description": "Benford anomaly", "severity": 5}),
                type("E", (), {"type": "RULE", "description": "V-RULE-04 fired", "severity": 4}),
            ],
            "summary_stats": {"txn_count_5min": 12, "layer2_probability": 0.7},
            "ensemble_decision": "REVIEW",
        })()
        report = FallbackGenerator().generate(context)
        assert report.txn_id == "TXN_FB"
        assert report.recommended_action == "REVIEW"
        assert report.fraud_type == "BURST_ATTACK"
        assert report.confidence == "HIGH"
        assert report.quality_score == 0.7
        assert len(report.narrative) >= 50

    def test_empty_context(self):
        context = type("Ctx", (), {
            "txn_id": "TXN_EMPTY",
            "evidence_items": [],
            "summary_stats": {},
            "ensemble_decision": "ALLOW",
        })()
        report = FallbackGenerator().generate(context)
        assert report.recommended_action == "ALLOW"
        assert report.fraud_type == "OTHER"


class TestInvestigationTask:
    @pytest.fixture(autouse=True)
    def _patch_task_deps(self, monkeypatch):
        # The task body re-imports these inside the function, so patch the
        # source modules, not the task module's globals.
        self.redis = FakeSyncRedis()

        class FakeOllama:
            def __init__(self, *a, **k):
                self.calls = 0

            def health_sync(self):
                return True

            def generate_sync(self, prompt, max_tokens=512, temperature=0.1):
                self.calls += 1
                return GOOD_JSON

        class FakeUnhealthyOllama(FakeOllama):
            def health_sync(self):
                return False

        self.ollama_cls = FakeOllama
        self.unhealthy_cls = FakeUnhealthyOllama
        monkeypatch.setattr("llm.client.OllamaClient", FakeOllama)
        monkeypatch.setattr("llm.config.OllamaConfig", lambda: None)
        monkeypatch.setattr(
            "tasks.investigation_task.create_redis", lambda mode="sync": self.redis
        )

    def _run_task(self, task_module, txn_id: str, decision: str = "BLOCK"):
        ensemble_json = json.dumps({
            "txn_id": txn_id,
            "decision": decision,
            "layer1_decision": "ALLOW",
            "layer1_confidence": 0.0,
            "layer2_probability": 0.9,
            "layer2_source": "L2_GNN",
            "triggered_rules": ["V-RULE-04"],
            "graph_features": {},
        })
        return task_module.generate_investigation.run(txn_id, ensemble_json)

    def test_healthy_ollama_generates_and_stores_report(self, monkeypatch):
        import tasks.investigation_task as task_module
        result = self._run_task(task_module, "TXN_TASK_01")
        assert result["status"] == "success"
        assert result["report"]["fraud_type"] == "MULE_RING"
        stored = self.redis.get("investigation:TXN_TASK_01")
        assert stored is not None
        assert json.loads(stored)["report"]["recommended_action"] == "BLOCK"

    def test_unhealthy_ollama_uses_fallback(self, monkeypatch):
        import tasks.investigation_task as task_module
        monkeypatch.setattr("llm.client.OllamaClient", self.unhealthy_cls)
        result = self._run_task(task_module, "TXN_TASK_02")
        assert result["status"] == "success"
        assert result["report"]["quality_score"] == 0.7
        assert "Fraud investigation" in result["report"]["narrative"]

    def test_exception_returns_failed_and_retries(self, monkeypatch):
        import tasks.investigation_task as task_module

        class ExplodingOllama:
            def __init__(self, *a, **k):
                pass

            def health_sync(self):
                return True

            def generate_sync(self, prompt, max_tokens=512, temperature=0.1):
                raise RuntimeError("model timeout")

        monkeypatch.setattr("llm.client.OllamaClient", ExplodingOllama)
        result = self._run_task(task_module, "TXN_TASK_03")
        assert result["status"] == "failed"
        assert "model timeout" in result["error"]
