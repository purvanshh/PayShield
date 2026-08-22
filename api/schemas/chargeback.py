"""Chargeback evidence and rebuttal schemas (Track 02 - AI Risk Manager).

Contracts for the chargeback evidence responder. Every evidence source is
traceable: L1 (velocity / geo / Benford filter results), L2 (GNN graph
evidence), L3 (LLM investigation) and merchant-provided data (delivery
proof, customer communication, refund policy, terms of service).

Policy (Phase 3):
- Every field has a source -> audit trails stay honest.
- Evidence absence is represented as ``None``, never fabricated.
- ``completeness_score`` quantifies bundle coverage (0..1).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

NetworkName = Literal["UPI", "VISA", "MASTERCARD", "AMEX", "RUPAY"]
ResponseType = Literal["ACCEPT", "REJECT", "PARTIAL"]


class AuditLogEntry(BaseModel):
    """Single step of the evidence assembly chain (tamper-evident context)."""

    timestamp: datetime
    action: str = Field(..., description="e.g. L1_EVIDENCE_COLLECTED")
    agent: str = Field(..., description="e.g. transaction_agent")
    detail: str = ""


class TransactionProof(BaseModel):
    """Transaction-level proof pulled from the PayShield audit log."""

    txn_timestamp: datetime
    amount: Decimal
    currency: str = "INR"
    payment_method: str = "UPI"
    auth_code: str | None = None
    settlement_id: str | None = None
    merchant_id: str = ""
    was_blocked: bool = False


class VelocityEvidence(BaseModel):
    """L1 velocity filter snapshot taken at transaction time."""

    rules_triggered: list[str] = Field(
        default_factory=list, description="e.g. V-RULE-02, V-RULE-03"
    )
    txn_count_5m: int = 0
    txn_count_1h: int = 0
    amount_total_1h: Decimal = Decimal("0")
    explanation: str = ""


class GeoEvidence(BaseModel):
    """L1 geo filter snapshot taken at transaction time."""

    rules_triggered: list[str] = Field(default_factory=list)
    location: str | None = None
    previous_location: str | None = None
    geo_velocity_kmh: float | None = None
    explanation: str = ""


class BenfordEvidence(BaseModel):
    """L1 Benford's-law snapshot for the merchant at transaction time."""

    rules_triggered: list[str] = Field(default_factory=list)
    chi2_statistic: float | None = None
    observed_counts: list[int] = Field(default_factory=list)
    total_transactions: int = 0
    is_anomalous: bool = False
    explanation: str = ""


class RiskPath(BaseModel):
    path: list[str] = Field(default_factory=list)
    score: float = 0.0
    description: str = ""


class EntitySummary(BaseModel):
    entity_id: str = ""
    entity_type: str = ""
    summary: str = ""
    risk_score: float = 0.0


class GraphEvidence(BaseModel):
    """L2 GNN evidence snapshot taken at transaction time."""

    risk_paths_found: list[RiskPath] = Field(default_factory=list)
    connected_entities: list[EntitySummary] = Field(default_factory=list)
    gnn_score: float = 0.0
    anomaly_type: str | None = None


class InvestigationReport(BaseModel):
    """L3 LLM investigation report (issued asynchronously post-scoring)."""

    summary: str = ""
    narrative: str = ""
    fraud_type: str = "OTHER"
    confidence: str = "LOW"
    recommended_action: str = "ALLOW"
    key_evidence: list[str] = Field(default_factory=list)
    quality_score: float = 0.0


class DeviceFingerprint(BaseModel):
    """Device evidence (retrieved from the device index, not re-scored)."""

    device_id: str
    user_id: str = ""
    ip_address: str = ""
    user_agent: str = ""
    screen_resolution: str = ""
    timezone: str = ""
    language: str = ""
    canvas_hash: str = ""
    webgl_hash: str = ""
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    is_new_device: bool = True
    proxy_score: float = 0.0


class IPGeolocation(BaseModel):
    ip_address: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    isp: str = ""
    is_proxy: bool = False
    latitude: float | None = None
    longitude: float | None = None
    match_score: float | None = None


class DeliveryProof(BaseModel):
    courier_company: str = ""
    tracking_id: str = ""
    dispatched_at: datetime | None = None
    delivered_at: datetime | None = None
    delivered_address: str = ""
    proof_url: str = ""
    signature_available: bool = False
    weight_verified: bool = False
    recipient_confirmation: bool = False


class CommunicationRecord(BaseModel):
    channel: Literal["WHATSAPP", "SMS", "EMAIL", "APP_CHAT", "PHONE"] = "APP_CHAT"
    direction: Literal["INBOUND", "OUTBOUND"] = "INBOUND"
    timestamp: datetime
    participant: str = ""
    summary: str = ""
    attachment_urls: list[str] = Field(default_factory=list)


class RefundPolicy(BaseModel):
    policy_url: str = ""
    policy_version: str = ""
    returns_allowed_days: int = 7
    restocking_fee_percent: float = 0.0
    return_conditions: list[str] = Field(default_factory=list)
    effective_from: datetime | None = None


class TermsOfService(BaseModel):
    tos_url: str = ""
    tos_version: str = ""
    relevant_clause: str = ""
    effective_from: datetime | None = None


class MerchantEvidence(BaseModel):
    """Merchant-provided evidence pulled from the merchant's own systems.

    Retrieved by ``razorpay_client.fetch_merchant_evidence`` (Phase 11) or
    supplied via the API request ``evidence_override``.
    """

    delivery_proof: DeliveryProof | None = None
    customer_communication: list[CommunicationRecord] = Field(default_factory=list)
    refund_policy: RefundPolicy | None = None
    terms_of_service: TermsOfService | None = None


class Attachment(BaseModel):
    evidence_type: str = Field(..., description="e.g. invoice, proof_of_delivery")
    url: str
    description: str = ""
    filename: str = ""
    content_type: str = ""
    checksum: str = ""
    size_bytes: int = 0


class EvidenceBundle(BaseModel):
    """Categorised evidence pulled from PayShield L1/L2/L3 and merchant data."""

    velocity_evidence: VelocityEvidence | None = None
    geo_evidence: GeoEvidence | None = None
    benford_evidence: BenfordEvidence | None = None
    graph_evidence: GraphEvidence | None = None
    investigation_report: InvestigationReport | None = None
    merchant_evidence: MerchantEvidence | None = None
    transaction_proof: TransactionProof | None = None
    device_fingerprint: DeviceFingerprint | None = None
    ip_geolocation: IPGeolocation | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    audit_trail: list[AuditLogEntry] = Field(default_factory=list)
    completeness_score: float = 0.0


class InvestigationNarrative(BaseModel):
    """AI-generated rebuttal narrative (from the chargeback LLM template)."""

    summary: str = ""
    full_report: str = ""
    key_evidence: list[str] = Field(default_factory=list)
    quality_score: float = 0.0


class ChargebackRebuttalDocument(BaseModel):
    """Complete chargeback rebuttal ready for submission to Razorpay/NPCI."""

    dispute_id: str
    payment_id: str
    transaction_id: str
    network: NetworkName = "UPI"
    reason_code: str
    reason_description: str = ""
    response_type: ResponseType
    response_deadline: datetime
    response_urgency: float = 0.0
    evidence: EvidenceBundle = Field(default_factory=EvidenceBundle)
    narrative: InvestigationNarrative = Field(default_factory=InvestigationNarrative)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generated_by: str = "chargeback_agent_v1.0.0"
    audit_trail: list[AuditLogEntry] = Field(default_factory=list)
    confidence_score: float = 0.0
    razorpay_payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 5 API contract models
# ---------------------------------------------------------------------------


class EvidenceOverride(BaseModel):
    """Human-supplied evidence the merchant wants merged into the bundle."""

    delivery_proof_url: str | None = None
    customer_notes: str = ""
    attachment_urls: list[str] = Field(default_factory=list)


class ChargebackRespondRequest(BaseModel):
    dispute_id: str
    payment_id: str
    transaction_id: str
    network: NetworkName = "UPI"
    auto_submit: bool = False
    evidence_override: EvidenceOverride | None = None
    reason_code: str | None = None
    reason_description: str = ""
    response_deadline: datetime | None = None


class ChargebackRespondData(BaseModel):
    rebuttal_id: str
    dispute_id: str
    response_type: ResponseType
    confidence_score: float
    evidence_completeness: float
    narrative: dict[str, Any]
    razorpay_payload: dict[str, Any]
    audit_trail: list[AuditLogEntry]
    warnings: list[str] = Field(default_factory=list)


class ChargebackRespondResponse(BaseModel):
    status: str = "SUCCESS"
    data: ChargebackRespondData
    latency_ms: float = 0.0


class ChargebackSubmitRequest(BaseModel):
    strike: Literal["contest", "accept", "partial"] = "contest"
    comment: str = ""


class ChargebackSubmitData(BaseModel):
    submission_id: str
    dispute_id: str
    razorpay_status: str = ""
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0


class ChargebackSubmitResponse(BaseModel):
    status: str = "SUBMITTED"
    data: ChargebackSubmitData
    latency_ms: float = 0.0
