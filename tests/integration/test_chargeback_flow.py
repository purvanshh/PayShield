"""End-to-end chargeback flow integration tests (Phase 20).

Tests the complete story: transaction scored and stored -> dispute filed ->
evidence reconstruction from the audit chain -> rebuttal assembly ->
Razorpay payload validation -> mock submission. Runs entirely against the
in-memory Redis and a directory-local audit chain - no external services.

Scenarios covered:
1. happy path - fraud dispute (10.4) with full evidence -> REJECT
2. incomplete evidence - no device, no L2/L3 record -> conservative
   PARTIAL/ACCEPT with low confidence (graceful degradation)
3. service dispute (13.1) - REJECT with delivery proof, ACCEPT without
4. network windows - UPI 7-day vs Visa 30-day urgency
5. mock Razorpay submission envelope
"""

from datetime import datetime, timedelta
from decimal import Decimal

from api.schemas.chargeback import ChargebackRebuttalDocument
from chargeback.evidence_collector import ChargebackEvidenceCollector
from chargeback.razorpay_client import RazorpayClient
from chargeback.rebuttal_builder import ChargebackRebuttalBuilder
from data.synthetic.chargeback_generator import ChargebackSyntheticGenerator
from store.audit_log import AuditLogReader, AuditLogWriter
from tests.fake_redis import FakeRedis


def _record_chargeback(writer, txn_id, amount, merchant_id="M00001", rules=None, device="DEV-88412"):
    """Persist the score-decision audit entry the collector reads back."""
    payload = {
        "txn_id": txn_id,
        "merchant_id": merchant_id,
        "amount": amount,
        "fraud_probability": 0.12,
        "triggered_rules": rules or [],
    }
    if device:
        payload["device_fingerprint"] = device
    writer.append("SCORE_DECISION", "U000001", "ALLOW", payload)


class TestEndToEndChargebackFlow:
    def _pipeline(self, tmp_path, redis=None, merchant_provider=None, config_extra=None):
        writer = AuditLogWriter(str(tmp_path), max_entries_per_file=1000)
        reader = AuditLogReader(str(tmp_path))
        collector = ChargebackEvidenceCollector(
            redis=redis or FakeRedis(),
            audit_reader=reader,
            merchant_evidence_provider=merchant_provider,
        )
        builder = ChargebackRebuttalBuilder(
            evidence_collector=collector,
            llm_client=None,
            razorpay_client=RazorpayClient(mock_mode=True),
            config={"confidence_threshold": 0.6, **(config_extra or {})},
        )
        return writer, builder

    async def test_happy_path_full_evidence_rejects(self, tmp_path):
        writer, builder = self._pipeline(tmp_path)
        _record_chargeback(
            writer,
            "TXN_1",
            4500.0,
            rules=["V-RULE-02", "G-RULE-01"],
        )
        deadline = datetime.utcnow() + timedelta(days=8)

        rebuttal = await builder.build_rebuttal(
            dispute_id="disp_A",
            payment_id="pay_A",
            transaction_id="TXN_1",
            network="VISA",
            reason_code="10.4",
            reason_description="Cardholder fraud probe",
            response_deadline=deadline,
        )

        assert rebuttal.dispute_id == "disp_A"
        assert rebuttal.transaction_id == "TXN_1"
        assert rebuttal.response_type == "REJECT"
        assert 0.9 <= rebuttal.confidence_score <= 1.0
        assert rebuttal.evidence.completeness_score >= 0.8
        assert rebuttal.evidence.graph_evidence is None  # L2 not stored -> warning path
        assert rebuttal.razorpay_payload["contest"] is True
        assert "summary" in rebuttal.razorpay_payload["evidence"]
        assert "billing_proof" in rebuttal.razorpay_payload["evidence"]
        # audit trail: action required, timestamp present and ISO-parseable
        from datetime import datetime as _dt

        for entry in rebuttal.audit_trail:
            assert entry.action
            assert isinstance(entry.timestamp, _dt)
            assert entry.timestamp.isoformat()
        assert rebuttal.audit_trail[-1].action == "REBUTTAL_ASSEMBLED"

    async def test_incomplete_evidence_is_conservative(self, tmp_path):
        writer, builder = self._pipeline(tmp_path, config_extra={"confidence_threshold": 0.7})
        # no device, no velocity/geo rules -> minimal bundle (proof only)
        writer.append(
            "SCORE_DECISION",
            "U_NEW001",
            "ALLOW",
            {"txn_id": "TXN_INCOMPLETE", "merchant_id": "M_ANY", "amount": 5000.0},
        )
        rebuttal = await builder.build_rebuttal(
            dispute_id="CB_INCOMPLETE",
            payment_id="pay_INCOMPLETE",
            transaction_id="TXN_INCOMPLETE",
            network="UPI",
            reason_code="10.4",
            reason_description="Fraud",
            response_deadline=datetime.utcnow() + timedelta(days=7),
        )

        assert rebuttal.evidence.graph_evidence is None
        assert rebuttal.evidence.investigation_report is None
        assert rebuttal.evidence.device_fingerprint is None
        assert rebuttal.response_type in ("PARTIAL", "ACCEPT")
        # honesty: completeness caps at proof + velocity/geo snapshots only
        assert rebuttal.evidence.completeness_score <= 0.62
        assert rebuttal.confidence_score < 0.7

    async def test_service_dispute_delivery_proof_swings_rebuttal(self, tmp_path):
        invalid_provider = None
        writer, builder = self._pipeline(tmp_path, merchant_provider=invalid_provider)
        _record_chargeback(writer, "TXN_SVC", 2200.0, rules=[])

        # without delivery proof -> accept (cannot win this one)
        accepted = await builder.build_rebuttal(
            dispute_id="disp_SVC1",
            payment_id="pay_SVC1",
            transaction_id="TXN_SVC",
            network="MASTERCARD",
            reason_code="13.1",
            reason_description="Goods or services not provided",
        )
        assert accepted.response_type == "ACCEPT"

        # with delivery proof (merchant evidence provider) -> reject
        _, builder_with_proof = self._pipeline(
            tmp_path, merchant_provider=_delivery_provider_for("TXN_SVC")
        )
        rejected = await builder_with_proof.build_rebuttal(
            dispute_id="disp_SVC2",
            payment_id="pay_SVC2",
            transaction_id="TXN_SVC",
            network="MASTERCARD",
            reason_code="13.1",
            reason_description="Goods or services not provided",
        )
        assert rejected.response_type == "REJECT"
        assert any("BlueDart" in e["description"] for e in rejected.razorpay_payload["evidence"]["proof_of_delivery"])

    async def test_network_windows_drive_urgency(self, tmp_path):
        # urgency = fraction of the network's response window already
        # elapsed: UPI 3 days elapsed of a 7-day window (deadline in 4)
        # vs Visa 21 days elapsed of a 30-day window (deadline in 9)
        upi = await self._build_with_deadline(
            tmp_path, "disp_UPI", "TXN_UPI", "UPI", datetime.utcnow() + timedelta(days=4)
        )
        visa = await self._build_with_deadline(
            tmp_path, "disp_VISA", "TXN_UPI", "VISA", datetime.utcnow() + timedelta(days=9)
        )
        assert abs(upi.response_urgency - (1 - 4 / 7)) < 0.01
        assert abs(visa.response_urgency - (1 - 9 / 30)) < 0.01
        # urgency is the fraction of the network's window that has elapsed -
        # cross-network comparison is valid only on the same network, so
        # verify monotonicity: a nearer deadline must be strictly more urgent
        later = await self._build_with_deadline(
            tmp_path, "disp_UPI2", "TXN_UPI", "UPI", datetime.utcnow() + timedelta(days=2)
        )
        assert later.response_urgency > upi.response_urgency

    async def _build_with_deadline(self, tmp_path, dispute_id, txn_id, network, deadline):
        writer, builder = self._pipeline(tmp_path)
        _record_chargeback(writer, txn_id, 1500.0)
        return await builder.build_rebuttal(
            dispute_id=dispute_id,
            payment_id=f"pay_{dispute_id}",
            transaction_id=txn_id,
            network=network,
            reason_code="10.4",
            response_deadline=deadline,
        )

    async def test_mock_razorpay_submission(self, tmp_path):
        writer, builder = self._pipeline(tmp_path)
        _record_chargeback(writer, "TXN_SUB", 3300.0, rules=["V-RULE-02"])
        rebuttal = await builder.build_rebuttal(
            dispute_id="disp_SUB",
            payment_id="pay_SUB",
            transaction_id="TXN_SUB",
            network="RUPAY",
            reason_code="10.4",
        )
        result = await builder.razorpay_client.contest_chargeback(
            dispute_id=rebuttal.dispute_id, rebuttal=rebuttal
        )

        assert result["status"] == "SUCCESS"
        assert result["mock"] is True
        assert result["razorpay_response"]["status"] == "under_review"
        assert result["razorpay_response"]["contest"] is True
        assert result["rebuttal_id"] == "disp_SUB"
        await builder.razorpay_client.close()

    async def test_synthetic_generator_feeds_flow(self, tmp_path):
        """The Phase-18 generator transaction wires into the real collector."""
        generator = ChargebackSyntheticGenerator(seed=7)
        txn = generator.generate_transaction("U_GEN1", "M_GEN1", "TXN_GEN1")
        chargeback = generator.generate_chargeback(txn, dispute_type="fraud")

        writer, builder = self._pipeline(tmp_path)
        rules = txn["l1_result"]["velocity_rules"] + txn["l1_result"]["geo_rules"]
        writer.append(
            "SCORE_DECISION",
            "U_GEN1",
            "ALLOW",
            {
                "txn_id": txn["txn_id"],
                "merchant_id": txn["merchant_id"],
                "amount": txn["amount"],
                "device_fingerprint": txn["device_fingerprint"],
                "triggered_rules": rules,
            },
        )

        rebuttal = await builder.build_rebuttal(
            dispute_id=chargeback["dispute_id"],
            payment_id=chargeback["payment_id"],
            transaction_id=txn["txn_id"],
            network=chargeback["network"],
            reason_code=chargeback["reason_code"],
            reason_description=chargeback["reason_description"],
            response_deadline=datetime.fromisoformat(chargeback["respond_by"]),
        )

        assert ChargebackRebuttalDocument.model_validate(rebuttal.model_dump()) is not None
        assert rebuttal.response_type in ("ACCEPT", "REJECT", "PARTIAL")
        assert rebuttal.evidence.transaction_proof is not None
        assert Decimal(str(rebuttal.evidence.transaction_proof.amount)) == Decimal(
            str(txn["amount"])
        )
        assert rebuttal.razorpay_payload["evidence"]["summary"]
        assert rebuttal.response_urgency > 0


def _delivery_provider_for(txn_id):
    async def provider(transaction_id, dispute_id=""):  # noqa: ARG001 - collector interface
        if transaction_id != txn_id:
            return None
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

    return provider
