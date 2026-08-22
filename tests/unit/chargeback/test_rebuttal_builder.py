"""ChargebackRebuttalBuilder tests (Phase 10)."""

import json
from datetime import datetime, timedelta

from api.schemas.chargeback import (
    Attachment,
    DeviceFingerprint,
    EvidenceBundle,
    MerchantEvidence,
    DeliveryProof,
    TransactionProof,
)
from chargeback.narrative_generator import NarrativeGenerator
from chargeback.rebuttal_builder import ChargebackRebuttalBuilder
from tests.fake_redis import FakeRedis


class FakeCollector:
    def __init__(self, bundle: EvidenceBundle):
        self.bundle = bundle
        self.calls = []

    async def collect_evidence(self, transaction_id, dispute_id=""):
        self.calls.append((transaction_id, dispute_id))
        return self.bundle


class FakeLLM:
    async def generate(self, prompt, max_tokens=None, temperature=None):
        return json.dumps(
            {
                "summary": "Transaction was legitimate. Audit trail complete.",
                "full_report": "L1 velocity normal, device fingerprint matched history.",
                "key_evidence": ["V-RULE-02 velocity check passed", "Device fingerprint consistent"],
                "quality_score": 0.82,
            }
        )


def _bundle(completeness: float = 0.9, delivery: bool = True) -> EvidenceBundle:
    merchant = None
    if delivery:
        merchant = MerchantEvidence(
            delivery_proof=DeliveryProof(
                courier_company="BlueDart",
                tracking_id="BD-991",
                delivered_at=datetime(2026, 7, 25),
                proof_url="https://pod/1.jpg",
                signature_available=True,
                recipient_confirmation=True,
                delivered_address="Mumbai",
            )
        )
    return EvidenceBundle(
        transaction_proof=TransactionProof(
            txn_timestamp=datetime(2026, 7, 20),
            amount=4500,
            currency="INR",
            payment_method="UPI",
            merchant_id="M00001",
        ),
        device_fingerprint=DeviceFingerprint(device_id="DEV-88412", is_new_device=False),
        merchant_evidence=merchant,
        attachments=[
            Attachment(evidence_type="invoice", url="https://inv/1.pdf", description="Invoice"),
            Attachment(evidence_type="proof_of_delivery", url="https://pod/2.jpg", description="POD"),
        ],
        completeness_score=completeness,
    )


class FakeCollectorNoOp:
    """Nothing returns (used to prove builder never calls it twice)."""


class TestChargebackRebuttalBuilder:
    def _builder(self, bundle, llm=True, **kwargs):
        collector = FakeCollector(bundle)
        return ChargebackRebuttalBuilder(
            evidence_collector=collector,
            llm_client=FakeLLM() if llm else None,
            **kwargs,
        ), collector

    async def test_build_rejects_with_full_evidence(self):
        builder, _ = self._builder(_bundle(0.9))
        doc = await builder.build_rebuttal(
            dispute_id="disp_1",
            payment_id="pay_1",
            transaction_id="TXN_1",
            network="VISA",
            reason_code="10.4",
            reason_description="Cardholder fraud probe",
            response_deadline=datetime.utcnow() + timedelta(days=8),
        )
        assert doc.response_type == "REJECT"
        assert doc.narrative.summary.startswith("Transaction was legitimate")
        assert doc.confidence_score > 0.9  # 0.9 + 0.1 boost
        assert doc.razorpay_payload["contest"] is True
        evidence = doc.razorpay_payload["evidence"]
        assert evidence["amount"] == 4500
        assert "billing_proof" in evidence
        assert any("BlueDart" in e["description"] for e in evidence["proof_of_delivery"])
        assert ChargebackRebuttalBuilder.rebuttal_id_for(
            doc.dispute_id, doc.transaction_id, doc.generated_at
        ).startswith("reb_")
        assert any(e.action == "REBUTTAL_ASSEMBLED" for e in doc.audit_trail)

    async def test_accept_when_evidence_is_thin(self):
        builder, _ = self._builder(_bundle(0.2))
        doc = await builder.build_rebuttal(
            dispute_id="disp_1",
            payment_id="pay_1",
            transaction_id="TXN_1",
            reason_code="10.4",
        )
        assert doc.response_type == "ACCEPT"
        assert doc.razorpay_payload["contest"] is False
        assert doc.confidence_score == 0.16  # 0.2 * 0.8
        assert doc.response_urgency <= 1.0

    async def test_partial_for_mid_completeness(self):
        builder, _ = self._builder(_bundle(0.6))
        doc = await builder.build_rebuttal(
            dispute_id="disp_1", payment_id="pay_1", transaction_id="TXN_1", reason_code="10.4"
        )
        assert doc.response_type == "PARTIAL"

    async def test_service_reason_needs_delivery_proof(self):
        builder, _ = self._builder(_bundle(0.9, delivery=True))
        doc = await builder.build_rebuttal(
            dispute_id="disp_1", payment_id="pay_1", transaction_id="TXN_1", reason_code="13.1"
        )
        assert doc.response_type == "REJECT"

        builder2, _ = self._builder(_bundle(0.9, delivery=False))
        doc2 = await builder2.build_rebuttal(
            dispute_id="disp_1", payment_id="pay_1", transaction_id="TXN_1", reason_code="13.1"
        )
        assert doc2.response_type == "ACCEPT"

    async def test_urgency_scales_with_deadline(self):
        builder, _ = self._builder(_bundle())
        future = datetime.utcnow() + timedelta(days=3)
        doc = await builder.build_rebuttal(
            dispute_id="disp_1",
            payment_id="pay_1",
            transaction_id="TXN_1",
            network="UPI",
            reason_code="10.4",
            response_deadline=future,
        )
        # UPI window = 7 days, 3 remaining -> 1 - 3/7
        assert abs(doc.response_urgency - (1 - 3 / 7)) < 0.01

    async def test_urgency_caps_at_one_when_overdue(self):
        builder, _ = self._builder(_bundle())
        past = datetime.utcnow() - timedelta(days=2)
        doc = await builder.build_rebuttal(
            dispute_id="disp_1",
            payment_id="pay_1",
            transaction_id="TXN_1",
            network="VISA",
            reason_code="10.4",
            response_deadline=past,
        )
        assert doc.response_urgency == 1.0

    async def test_fallback_narrative_without_llm(self):
        builder, _ = self._builder(_bundle(0.9), llm=False)
        doc = await builder.build_rebuttal(
            dispute_id="disp_1", payment_id="pay_1", transaction_id="TXN_1", reason_code="10.4"
        )
        assert doc.narrative.summary
        assert doc.narrative.quality_score == 0.5
        assert any("delivery" in k for k in doc.narrative.key_evidence)

    async def test_collector_called_with_expected_args(self):
        bundle = _bundle()
        builder, collector = self._builder(bundle)
        await builder.build_rebuttal(
            dispute_id="disp_2", payment_id="pay_2", transaction_id="TXN_2", reason_code="10.4"
        )
        assert collector.calls == [("TXN_2", "disp_2")]

    def test_determine_response_type_defaults_conservative(self):
        assert ChargebackRebuttalBuilder._determine_response_type(_bundle(0.2), "") == "ACCEPT"
        assert ChargebackRebuttalBuilder._determine_response_type(_bundle(0.5), "") == "PARTIAL"
        assert ChargebackRebuttalBuilder._determine_response_type(_bundle(0.9), "") == "REJECT"


class TestNarrativeGenerator:
    def test_parse_extracts_json_from_noisy_text(self):
        generator = NarrativeGenerator(llm_client=None)
        raw = "Sure! Here you go:\n{\"summary\": \"ok\", \"full_report\": \"details\", \"key_evidence\": [\"a\"], \"quality_score\": 0.7}\nHope this helps"
        narrative = generator.parse(raw)
        assert narrative is not None
        assert narrative.summary == "ok"
        assert narrative.quality_score == 0.7

    def test_parse_returns_none_on_garbage(self):
        generator = NarrativeGenerator(llm_client=None)
        assert generator.parse("no json here at all") is None

    def test_fallback_builds_from_bundle(self):
        generator = NarrativeGenerator(llm_client=None)
        narrative = generator.fallback(_bundle(), "10.4", "fraud probe")
        assert narrative.summary
        assert narrative.key_evidence
        assert narrative.quality_score == 0.5

    def test_prompt_is_rendered(self):
        generator = NarrativeGenerator(llm_client=None)
        prompt = generator.build_prompt(_bundle(), "10.4", "Cardholder fraud probe", "REJECT")
        assert "Cardholder fraud probe" in prompt
        assert "EVIDENCE SUMMARY" in prompt

    async def test_generate_uses_llm_when_available(self):
        generator = NarrativeGenerator(llm_client=FakeLLM())
        narrative = await generator.generate(_bundle(), "10.4", "fraud", "REJECT")
        assert narrative.quality_score == 0.82

    async def test_generate_falls_back_on_client_failure(self):
        class BrokenLLM:
            async def generate(self, prompt, max_tokens=None, temperature=None):
                raise RuntimeError("ollama down")

        generator = NarrativeGenerator(llm_client=BrokenLLM())
        narrative = await generator.generate(_bundle(), "10.4", "fraud", "REJECT")
        assert narrative.quality_score == 0.5
