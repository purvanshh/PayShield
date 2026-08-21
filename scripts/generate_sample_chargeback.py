#!/usr/bin/env python3
"""Generate a synthetic sample chargeback rebuttal document (Phase 3 demo aid).

The sample is built through the real Pydantic contracts with fully synthetic
(safe-to-share) data so the chargeback evidence responder can be demonstrated
and JSON-referenced without a live Razorpay account.

Usage: python scripts/generate_sample_chargeback.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def _sample() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from api.schemas.chargeback import (
        Attachment,
        AuditLogEntry,
        BenfordEvidence,
        ChargebackRebuttalDocument,
        CommunicationRecord,
        DeliveryProof,
        DeviceFingerprint,
        EvidenceBundle,
        EvidenceOverride,
        GeoEvidence,
        GraphEvidence,
        InvestigationNarrative,
        InvestigationReport,
        MerchantEvidence,
        RiskPath,
        TransactionProof,
        VelocityEvidence,
    )

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=9)

    evidence = EvidenceBundle(
        transaction_proof=TransactionProof(
            txn_timestamp=now - timedelta(days=31),
            amount=Decimal("4500.00"),
            currency="INR",
            payment_method="UPI",
            auth_code="AUTH-88271",
            settlement_id="set_4Kj2",
            merchant_id="M00042",
            was_blocked=False,
        ),
        velocity_evidence=VelocityEvidence(
            rules_triggered=["V-RULE-02"],
            txn_count_5m=1,
            txn_count_1h=4,
            amount_total_1h=Decimal("9800.00"),
            explanation="User performed 4 transactions in 1 hour totaling Rs.9,800 - within normal range",
        ),
        geo_evidence=GeoEvidence(
            rules_triggered=[],
            location="Mumbai, IN",
            previous_location="Mumbai, IN",
            geo_velocity_kmh=3.2,
            explanation="Location consistent with historical geofence (delta 3.2 km/h)",
        ),
        benford_evidence=BenfordEvidence(
            rules_triggered=[],
            chi2_statistic=9.1,
            observed_counts=[18, 15, 12, 10, 9, 7, 10, 4, 5],
            total_transactions=90,
            is_anomalous=False,
            explanation="Merchant amount distribution follows Benford expectation",
        ),
        graph_evidence=GraphEvidence(
            risk_paths_found=[],
            connected_entities=[],
            gnn_score=0.12,
            anomaly_type=None,
        ),
        investigation_report=InvestigationReport(
            summary="No fraudulent pattern detected; transaction consistent with user history.",
            narrative="",
            fraud_type="OTHER",
            confidence="LOW",
            recommended_action="ALLOW",
            key_evidence=["54 matching transactions in user history"],
            quality_score=0.78,
        ),
        merchant_evidence=MerchantEvidence(
            delivery_proof=DeliveryProof(
                courier_company="BlueDart",
                tracking_id="BD-991-4412",
                dispatched_at=now - timedelta(days=29),
                delivered_at=now - timedelta(days=27),
                delivered_address="12 Marine Lines, Mumbai",
                proof_url="https://storage.payshield.dev/pod/BD-991-4412.jpg",
                signature_available=True,
                weight_verified=True,
                recipient_confirmation=True,
            ),
            customer_communication=[
                CommunicationRecord(
                    channel="WHATSAPP",
                    direction="OUTBOUND",
                    timestamp=now - timedelta(days=27),
                    participant="+91-98xxxxxx21",
                    summary="Customer confirmed delivery and satisfaction",
                    attachment_urls=[],
                )
            ],
        ),
        device_fingerprint=DeviceFingerprint(
            device_id="DEV-88412",
            user_id="U001_82417",
            ip_address="10.12.44.88",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) ...",
            screen_resolution="390x844",
            timezone="Asia/Kolkata",
            first_seen=now - timedelta(days=210),
            last_seen=now,
            is_new_device=False,
            proxy_score=0.02,
        ),
        attachments=[
            Attachment(
                evidence_type="invoice",
                url="https://storage.payshield.dev/inv/TXN-2026-08121-000117.pdf",
                description="Transaction invoice",
                filename="invoice.pdf",
                content_type="application/pdf",
            ),
            Attachment(
                evidence_type="proof_of_delivery",
                url="https://storage.payshield.dev/pod/BD-991-4412.jpg",
                description="BlueDart POD",
                filename="pod.jpg",
                content_type="image/jpeg",
            ),
        ],
        completeness_score=0.92,
    )

    narrative = InvestigationNarrative(
        summary="Transaction was legitimate. Device fingerprint is stable across 210 days "
        "of history, geo velocity is consistent, and delivery proof (BlueDart "
        "signature POD, customer WhatsApp confirmation) is on file.",
        full_report=(
            "L1 velocity: 4 txns in 1h totaling Rs 9,800, no V-RULE-* blocks. "
            "Geo: same-city. Benford: merchant distribution conforms. "
            "L2 GNN: 0.12 risk. Delivery: signed POD on 2026-07-25. "
            "Conclusion: the chargeback disclosure ('unauthorized') is contradicted "
            "by 210 days of consistent device telemetry and delivery evidence."
        ),
        key_evidence=[
            "Device fingerprint stable 210 days",
            "Geo velocity 3.2 km/h within geofence",
            "Signed POD received",
            "Customer-confirmed delivery correspondence",
        ],
        quality_score=0.91,
    )

    document = ChargebackRebuttalDocument(
        dispute_id="disp_2Vw9aZ0q3X",
        payment_id="pay_2RzD5mK9bL",
        transaction_id="TXN-2026-08121-000117",
        network="VISA",
        reason_code="10.4",
        reason_description="Cardholder fraud probe",
        response_type="REJECT",
        response_deadline=deadline,
        response_urgency=0.55,
        evidence=evidence,
        narrative=narrative,
        generated_by="chargeback_agent_v1.0.0",
        audit_trail=[
            AuditLogEntry(
                timestamp=now - timedelta(seconds=4),
                action="L1_EVIDENCE_COLLECTED",
                agent="transaction_agent",
                detail="velocity/geo/benford snapshots retrieved",
            ),
            AuditLogEntry(
                timestamp=now - timedelta(seconds=3),
                action="L2_GRAPH_ANALYZED",
                agent="graph_model",
                detail="gnn_score=0.12",
            ),
            AuditLogEntry(
                timestamp=now - timedelta(seconds=2),
                action="L3_NARRATIVE_GENERATED",
                agent="llm_investigator",
                detail="summary generated (quality 0.91)",
            ),
            AuditLogEntry(
                timestamp=now - timedelta(seconds=1),
                action="REBUTTAL_ASSEMBLED",
                agent="chargeback_agent",
                detail="razorpay payload built",
            ),
        ],
        confidence_score=0.87,
        razorpay_payload={
            "contest": True,
            "evidence": {
                "amount": 4500,
                "summary": narrative.summary,
                "detailed_reason": narrative.full_report,
                "billing_proof": [
                    {
                        "type": "document",
                        "url": "https://storage.payshield.dev/inv/TXN-2026-08121-000117.pdf",
                        "description": "Invoice",
                    }
                ],
                "proof_of_delivery": [
                    {
                        "type": "document",
                        "url": "https://storage.payshield.dev/pod/BD-991-4412.jpg",
                        "description": "BlueDart POD",
                    }
                ],
                "customer_communication": [
                    {
                        "type": "document",
                        "url": "https://storage.payshield.dev/chat/BD-991-4412.pdf",
                        "description": "Customer WhatsApp confirmation",
                    }
                ],
            },
        },
    )

    return {
        "sample": document.model_dump(mode="json"),
        "evidence_override": EvidenceOverride(
            delivery_proof_url="https://storage.payshield.dev/pod/BD-991-4412.jpg",
            customer_notes="POD + WhatsApp chat attached",
        ).model_dump(mode="json"),
    }


def main():
    payload = _sample()
    out = Path("reports/sample_chargeback_rebuttal.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
