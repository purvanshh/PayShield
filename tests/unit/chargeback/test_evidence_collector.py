"""ChargebackEvidenceCollector tests (Phase 9)."""
# ruff: noqa: ARG001, ARG002 -- test doubles mirror the collector interfaces

import json
import time
from datetime import datetime

from chargeback.evidence_collector import ChargebackEvidenceCollector
from chargeback.exceptions import ChargebackTransactionNotFoundError
from store.audit_log import AuditLogReader, AuditLogWriter
from tests.fake_redis import FakeRedis

TXN = "TXN00000001"


def _seed_audit(tmp_path, decision="ALLOW", rules=None, amount=500.0):
    writer = AuditLogWriter(str(tmp_path), max_entries_per_file=100)
    entry = {
        "event_type": "SCORE_DECISION",
        "actor": "U000001",
        "decision": decision,
        "payload": {
            "txn_id": TXN,
            "merchant_id": "M00001",
            "amount": amount,
            "device_fingerprint": "DEV-88412",
            "fraud_probability": 0.12,
            "layer_triggered": "L1_STATISTICAL",
            "triggered_rules": rules or [],
        },
    }
    writer.append(entry["event_type"], entry["actor"], entry["decision"], entry["payload"])
    return AuditLogReader(str(tmp_path))


class TestChargebackEvidenceCollector:
    def setup_method(self):
        self.redis = FakeRedis()

    async def test_collects_full_bundle_from_audit_and_redis(self, tmp_path):
        now = time.time()
        self.redis.seed_velocity(
            "U000001", "DEV-88412", [now - 600, now - 60], [500.0, 700.0], ["M00001", "M00001"]
        )
        reader = _seed_audit(tmp_path, rules=["V-RULE-02"])
        collector = ChargebackEvidenceCollector(redis=self.redis, audit_reader=reader)
        bundle = await collector.collect_evidence(TXN, "disp_1")

        assert bundle.transaction_proof is not None
        assert float(bundle.transaction_proof.amount) == 500.0
        assert bundle.transaction_proof.merchant_id == "M00001"
        assert bundle.velocity_evidence is not None
        assert "V-RULE-02" in bundle.velocity_evidence.rules_triggered
        assert bundle.velocity_evidence.txn_count_1h == 2
        assert float(bundle.velocity_evidence.amount_total_1h) == 1200.0
        assert bundle.geo_evidence is not None
        assert bundle.benford_evidence is None
        assert bundle.device_fingerprint is not None
        assert bundle.device_fingerprint.is_new_device is True
        assert bundle.completeness_score >= 0.8
        assert any(e.action == "L1_EVIDENCE_COLLECTED" for e in bundle.audit_trail)

    async def test_missing_transaction_raises(self, tmp_path):
        reader = _seed_audit(tmp_path)
        collector = ChargebackEvidenceCollector(redis=self.redis, audit_reader=reader)
        try:
            await collector.collect_evidence("TXN_MISSING")
            raised = False
        except ChargebackTransactionNotFoundError:
            raised = True
        assert raised is True

    async def test_graceful_when_redis_empty(self, tmp_path):
        reader = _seed_audit(tmp_path)
        collector = ChargebackEvidenceCollector(redis=self.redis, audit_reader=reader)
        bundle = await collector.collect_evidence(TXN)
        assert bundle.velocity_evidence.txn_count_5m == 0
        assert "No velocity rules fired" in bundle.velocity_evidence.explanation
        assert bundle.completeness_score == 1.0  # txn+device present, velocity+geo optional

    async def test_completeness_penalised_missing_device(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path), max_entries_per_file=100)
        writer.append(
            "SCORE_DECISION",
            "U000001",
            "ALLOW",
            {"txn_id": TXN, "merchant_id": "M00001", "amount": 100.0, "triggered_rules": []},
        )
        collector = ChargebackEvidenceCollector(
            redis=self.redis, audit_reader=AuditLogReader(str(tmp_path))
        )
        bundle = await collector.collect_evidence(TXN)
        assert bundle.transaction_proof is not None
        assert bundle.device_fingerprint is None
        # base 0.5 (txn proof only) + bonus 0.12 (velocity+geo of 5 optional)
        assert bundle.completeness_score == 0.62

    async def test_benford_evidence_from_redis_hash(self, tmp_path):
        await self.redis.hmset("benford:M00001", {"1": 30, "2": 18, "3": 12, "4": 9, "5": 8, "6": 7, "7": 5, "8": 4, "9": 3, "total": 96})
        reader = _seed_audit(tmp_path, rules=["B-RULE-01"])
        collector = ChargebackEvidenceCollector(redis=self.redis, audit_reader=reader)
        bundle = await collector.collect_evidence(TXN)
        assert bundle.benford_evidence is not None
        assert bundle.benford_evidence.rules_triggered == ["B-RULE-01"]
        assert bundle.benford_evidence.total_transactions == 96
        assert bundle.benford_evidence.chi2_statistic is not None

    async def test_device_registered_in_index(self, tmp_path):
        device_data = {
            "user_id": "U000001",
            "user_agent": "Mozilla/5.0 (iPhone)",
            "features": json.dumps(["ip:10.12.44.88", "tz:Asia/Kolkata"]),
            "first_seen": "2025-01-01T00:00:00+00:00",
            "last_seen": "2026-08-21T00:00:00+00:00",
        }
        await self.redis.hmset("dfp:DEV-88412", device_data)
        # the audit chain masks the device id; the collector resolves it via
        # the user -> device index (ud:{user_id})
        await self.redis.sadd("ud:U000001", "DEV-88412")
        reader = _seed_audit(tmp_path)
        collector = ChargebackEvidenceCollector(redis=self.redis, audit_reader=reader)
        bundle = await collector.collect_evidence(TXN)
        assert bundle.device_fingerprint is not None
        assert bundle.device_fingerprint.is_new_device is False
        assert bundle.device_fingerprint.ip_address == "10.12.44.88"
        assert bundle.device_fingerprint.timezone == "Asia/Kolkata"

    async def test_merchant_evidence_provider_merges(self, tmp_path):
        reader = _seed_audit(tmp_path)

        async def provider(txn_id, dispute_id):
            return {
                "delivery_proof": {
                    "courier_company": "BlueDart",
                    "tracking_id": "BD-991",
                    "delivered_address": "Mumbai",
                    "proof_url": "https://pod/1.jpg",
                    "signature_available": True,
                    "recipient_confirmation": True,
                }
            }

        collector = ChargebackEvidenceCollector(
            redis=self.redis, audit_reader=reader, merchant_evidence_provider=provider
        )
        bundle = await collector.collect_evidence(TXN, "disp_1")
        assert bundle.merchant_evidence is not None
        assert bundle.merchant_evidence.delivery_proof.tracking_id == "BD-991"
        assert any(e.action == "MERCHANT_EVIDENCE_COLLECTED" for e in bundle.audit_trail)

    async def test_l3_provider_optional(self, tmp_path):
        reader = _seed_audit(tmp_path)

        class FakeL3:
            def get_report(self, txn_id):
                return {
                    "summary": "No anomaly",
                    "fraud_type": "OTHER",
                    "confidence": "LOW",
                    "recommended_action": "ALLOW",
                    "key_evidence": ["nothing"],
                    "quality_score": 0.5,
                }

        collector = ChargebackEvidenceCollector(
            redis=self.redis, audit_reader=reader, llm_investigator=FakeL3()
        )
        bundle = await collector.collect_evidence(TXN)
        assert bundle.investigation_report is not None
        assert bundle.investigation_report.summary == "No anomaly"

    async def test_explanation_artifact_fallback(self, tmp_path):
        from chargeback.evidence_collector import ChargebackEvidenceCollector

        art_dir = tmp_path / "explanations"
        art_dir.mkdir()
        (art_dir / f"{TXN}.json").write_text(
            json.dumps(
                {
                    "txn_id": TXN,
                    "decision": "REVIEW",
                    "triggered_rules": ["V-RULE-01"],
                    "generated_at": datetime.utcnow().isoformat(),
                    "amount": 999.0,
                    "merchant_id": "M00001",
                    "explanation_source": "L1_STATISTICAL",
                }
            )
        )
        collector = ChargebackEvidenceCollector(redis=FakeRedis(), audit_reader=AuditLogReader(str(tmp_path / "empty")),
                                                explanation_dir=str(art_dir))
        bundle = await collector.collect_evidence(TXN)
        assert bundle.transaction_proof is not None
        assert float(bundle.transaction_proof.amount) == 999.0
        assert bundle.transaction_proof.was_blocked is False
        assert bundle.velocity_evidence.rules_triggered == ["V-RULE-01"]
