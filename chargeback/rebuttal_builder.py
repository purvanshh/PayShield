"""Chargeback rebuttal builder (Track 02 - Phase 10).

Takes the evidence bundle and assembles a complete
:class:`api.schemas.chargeback.ChargebackRebuttalDocument`:

1. determine the merchant response (ACCEPT / REJECT / PARTIAL) - rule-based,
   because chargeback decisions are governed by evidence availability, not
   probabilistic risk (a model would hide the rationale a bank officer needs);
2. generate the narrative - reuses the existing Ollama client with a
   chargeback-specific Jinja2 template, falling back to a deterministic
   story when the LLM is unavailable;
3. compute urgency from the network deadline and confidence from evidence
   completeness;
4. build the exact Razorpay contest payload.

The document is *assembled*, not submitted: human (or admin) oversight is
required before POST /v1/chargeback/{dispute_id}/submit.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from api.schemas.chargeback import (
    AuditLogEntry,
    ChargebackRebuttalDocument,
    InvestigationNarrative,
)
from chargeback.narrative_generator import NarrativeGenerator

logger = logging.getLogger(__name__)

FRAUD_REASON_CODES = {"10.4", "10.5", "FRAUD", "UNAUTHORIZED"}
SERVICE_REASON_CODES = {"13.1", "13.2", "SERVICES_NOT_PROVIDED"}

DEFAULT_RESPONSE_WINDOWS = {"UPI": 7, "VISA": 30, "MASTERCARD": 30, "AMEX": 20, "RUPAY": 15}


class ChargebackRebuttalBuilder:
    """Assembles a ChargebackRebuttalDocument from an EvidenceBundle."""

    def __init__(
        self,
        evidence_collector: Any,
        llm_client: Any = None,
        razorpay_client: Any = None,
        narrative_generator: NarrativeGenerator | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.evidence_collector = evidence_collector
        self.llm_client = llm_client
        self.razorpay_client = razorpay_client
        self.config = config or {}
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.6))
        self.narrative_generator = narrative_generator or NarrativeGenerator(
            llm_client=llm_client,
            model_name=self.config.get("narrative_model", "llama3.1:8b"),
        )

    async def build_rebuttal(
        self,
        dispute_id: str,
        payment_id: str,
        transaction_id: str,
        network: str = "UPI",
        reason_code: str = "",
        reason_description: str = "",
        response_deadline: datetime | None = None,
    ) -> ChargebackRebuttalDocument:
        """Build a complete rebuttal document.

        Orchestration:
        1. collect evidence
        2. determine response type
        3. generate narrative
        4. calculate urgency and confidence
        5. build the Razorpay payload
        6. assemble the document with its audit trail

        Raises:
            ChargebackTransactionNotFoundError: via the evidence collector when the
                transaction is absent from the audit chain. A low-confidence
                draft is still produced for human review.
        """
        evidence = await self.evidence_collector.collect_evidence(
            transaction_id=transaction_id, dispute_id=dispute_id
        )

        response_type = self._determine_response_type(evidence, reason_code)
        narrative = await self.narrative_generator.generate(
            evidence=evidence,
            reason_code=reason_code,
            reason_description=reason_description,
            response_type=response_type,
        )

        now = datetime.utcnow()
        if response_deadline is None:
            response_deadline = now + timedelta(days=self._get_response_window(network))
        urgency = self._calculate_urgency(response_deadline, now, network)
        confidence = self._calculate_confidence(evidence.completeness_score, response_type)

        razorpay_payload = self._build_razorpay_payload(
            payment_id=payment_id,
            response_type=response_type,
            narrative=narrative,
            evidence=evidence,
        )

        audit_trail = list(evidence.audit_trail)
        audit_trail.append(
            AuditLogEntry(
                timestamp=now,
                action="REBUTTAL_ASSEMBLED",
                agent="chargeback_agent_v1.0.0",
                detail=f"response_type={response_type} confidence={confidence:.2f}",
            )
        )

        rebuttal = ChargebackRebuttalDocument(
            dispute_id=dispute_id,
            payment_id=payment_id,
            transaction_id=transaction_id,
            network=network,
            reason_code=reason_code,
            reason_description=reason_description,
            response_type=response_type,
            response_deadline=response_deadline,
            response_urgency=round(urgency, 4),
            evidence=evidence,
            narrative=narrative,
            generated_at=now,
            generated_by="chargeback_agent_v1.0.0",
            audit_trail=audit_trail,
            confidence_score=round(confidence, 4),
            razorpay_payload=razorpay_payload,
        )
        if confidence < self.confidence_threshold:
            logger.warning(
                "rebuttal confidence %.2f below threshold %.2f for %s",
                confidence,
                self.confidence_threshold,
                dispute_id,
            )
        return rebuttal

    @staticmethod
    def rebuttal_id_for(dispute_id: str, transaction_id: str, generated_at: datetime) -> str:
        digest = hashlib.sha256(
            f"{dispute_id}:{transaction_id}:{generated_at.isoformat()}".encode()
        ).hexdigest()[:12]
        return f"reb_{digest}"

    @staticmethod
    def _determine_response_type(evidence: Any, reason_code: str) -> str:
        """Rule-based disposition.

        - ACCEPT: completeness below thresholds or service reason without
          delivery proof (we cannot win; admitting keeps the dispute clean).
        - REJECT: strong evidence (fraud codes with full bundle, service
          reason with delivery proof on file).
        - PARTIAL: overlap - evidence exists but not enough to fully reject.
        """
        completeness = evidence.completeness_score

        if reason_code in FRAUD_REASON_CODES:
            if completeness >= 0.8:
                return "REJECT"
            if completeness >= 0.5:
                return "PARTIAL"
            return "ACCEPT"

        if reason_code in SERVICE_REASON_CODES:
            merchant = getattr(evidence, "merchant_evidence", None)
            delivery = getattr(merchant, "delivery_proof", None) or getattr(
                evidence, "delivery_proof", None
            )
            if delivery is not None:
                return "REJECT"
            return "ACCEPT"

        if completeness >= 0.7:
            return "REJECT"
        if completeness >= 0.4:
            return "PARTIAL"
        return "ACCEPT"

    def _get_response_window(self, network: str) -> int:
        windows = {**DEFAULT_RESPONSE_WINDOWS, **self.config.get("response_deadline_days", {})}
        return int(windows.get(network, 30))

    @staticmethod
    def _calculate_urgency(deadline: datetime, now: datetime, network: str) -> float:
        """0.0 (days left) .. 1.0 (deadline now/passed).

        Overdue disputes get urgency 1.0: they are next to resolve with the
        network - the honest signal is "critical", not "no time left".
        """
        days_remaining = (deadline.replace(tzinfo=None) - now).total_seconds() / 86400.0
        window = DEFAULT_RESPONSE_WINDOWS.get(network, 30)
        if days_remaining <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (days_remaining / window)))

    @staticmethod
    def _calculate_confidence(completeness: float, response_type: str) -> float:
        base = completeness
        if response_type == "REJECT" and base > 0.8:
            base += 0.1  # fully evidenced rejection is the strongest claim
        if response_type == "ACCEPT":
            base *= 0.8  # admitting defeat: graded down
        return min(1.0, base)

    @staticmethod
    def _build_razorpay_payload(
        payment_id: str,
        response_type: str,
        narrative: InvestigationNarrative,
        evidence: Any,
    ) -> dict[str, Any]:
        """Exact Razorpay contest payload (single place to update on API drift)."""
        evidence_slots: dict[str, list[dict[str, str]]] = {
            "billing_proof": [],
            "shipping_proof": [],
            "proof_of_delivery": [],
            "proof_of_refund": [],
            "cancellation_by_customer": [],
            "customer_communication": [],
            "customer_confirmation": [],
            "other": [],
        }

        def slot(kind: str, url: str, description: str) -> None:
            target = kind if kind in evidence_slots else "other"
            evidence_slots[target].append(
                {"type": "document", "url": url, "description": description}
            )

        tp = evidence.transaction_proof
        invoice_type = tp.payment_method if tp else "payment"
        slot(
            "billing_proof",
            f"payshield://txn/{payment_id}/invoice",
            f"{invoice_type} invoice for {tp.amount} {tp.currency}" if tp else "transaction invoice",
        )
        dev = evidence.device_fingerprint
        if dev:
            slot("billing_proof", "", f"device {dev.device_id} fingerprint record")
            evidence_slots["billing_proof"][-1]["url"] = f"payshield://device/{dev.device_id}"

        merchant = getattr(evidence, "merchant_evidence", None)
        if merchant:
            dp = merchant.delivery_proof
            if dp and dp.proof_url:
                # prepend delivery proof so it reads first in the slot
                evidence_slots["proof_of_delivery"].insert(
                    0,
                    {
                        "type": "document",
                        "url": dp.proof_url,
                        "description": (
                            f"Proof of delivery - {dp.courier_company} {dp.tracking_id}"
                        ),
                    },
                )
            for comm in merchant.customer_communication:
                evidence_slots["customer_communication"].append(
                    {
                        "type": "document",
                        "url": comm.attachment_urls[0] if comm.attachment_urls else "",
                        "description": f"{comm.channel}: {comm.summary}",
                    }
                )

        for att in evidence.attachments:
            slot(att.evidence_type, att.url, att.description or att.evidence_type)

        evidence_slots = {k: v for k, v in evidence_slots.items() if v}
        amount = int(float(tp.amount)) if tp and tp.amount is not None else None
        payload: dict[str, Any] = {
            "contest": response_type == "REJECT",
            "evidence": {"summary": narrative.summary},
        }
        if amount is not None:
            payload["evidence"]["amount"] = amount
        if narrative.full_report:
            payload["evidence"]["detailed_reason"] = narrative.full_report
        payload["evidence"].update(evidence_slots)
        return payload
