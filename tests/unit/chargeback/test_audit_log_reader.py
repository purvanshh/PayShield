"""AuditLogReader tests (Phase 9) - JSONL chain read-back."""


from store.audit_log import AuditLogReader, AuditLogWriter


def _make_entry(txn_id="TXN00000001", event="SCORE_DECISION", decision="ALLOW"):
    return {
        "event_type": event,
        "actor": "U000001",
        "decision": decision,
        "payload": {
            "txn_id": txn_id,
            "merchant_id": "M00001",
            "amount": 500.0,
            "device_fingerprint": "DEV-88412",
            "fraud_probability": 0.12,
            "layer_triggered": "L1_STATISTICAL",
            "triggered_rules": ["V-RULE-02"],
        },
    }


class TestAuditLogReader:
    def test_get_transaction_finds_score_entry(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path), max_entries_per_file=10)
        writer.append(
            _make_entry()["event_type"],
            _make_entry()["actor"],
            _make_entry()["decision"],
            _make_entry()["payload"],
        )
        reader = AuditLogReader(str(tmp_path))
        entry = reader.get_transaction("TXN00000001")
        assert entry is not None
        assert entry["payload"]["txn_id"] == "TXN00000001"
        assert entry["payload"]["triggered_rules"] == ["V-RULE-02"]
        assert entry["actor"] == "U000001"

    def test_get_transaction_missing_returns_none(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path))
        writer.append("SCORE_DECISION", "U1", "ALLOW", {"txn_id": "TXN_A"})
        reader = AuditLogReader(str(tmp_path))
        assert reader.get_transaction("TXN_UNKNOWN") is None

    def test_reads_across_rotated_files(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path), max_entries_per_file=1)
        writer.append("SCORE_DECISION", "U1", "ALLOW", {"txn_id": "TXN_A"})
        writer.append("SCORE_DECISION", "U1", "ALLOW", {"txn_id": "TXN_B"})
        reader = AuditLogReader(str(tmp_path))
        ids = {e["payload"]["txn_id"] for e in reader.get_entries("SCORE_DECISION")}
        assert ids == {"TXN_A", "TXN_B"}

    def test_pii_masking_keeps_audit_readable(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path))
        writer.append(
            "SCORE_DECISION",
            "U000001",
            "ALLOW",
            {"txn_id": "TXN00000001", "device_fingerprint": "fp_abcdef123456"},
        )
        reader = AuditLogReader(str(tmp_path))
        entry = reader.get_transaction("TXN00000001")
        assert entry["payload"]["txn_id"] == "TXN00000001"
        assert entry["payload"]["device_fingerprint"] != "fp_abcdef123456"
        assert entry["payload"]["device_fingerprint"].startswith("fp_")

    def test_verify_chain_passes_after_writes(self, tmp_path):
        writer = AuditLogWriter(str(tmp_path))
        writer.append("SCORE_DECISION", "U1", "ALLOW", {"txn_id": "TXN_A"})
        writer.append("CHARGEBACK_REBUTTAL", "U1", "REJECT", {"txn_id": "TXN_A"})
        reader = AuditLogReader(str(tmp_path))
        valid, count = reader.verify_chain()
        assert valid is True
        assert count == 2
