from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.schemas.chargeback import (
    ChargebackRespondRequest,
    ChargebackRespondResponse,
    ChargebackSubmitRequest,
    ChargebackSubmitResponse,
)

__all__ = [
    "GeoPoint",
    "ScoreRequest",
    "BatchScoreRequest",
    "FraudScoreResponse",
    "BatchScoreResponse",
    "InvestigationReportResponse",
    "FeedbackRequest",
    "FeedbackResponse",
    "HealthCheckResponse",
    "AgentHealthResponse",
    "ConfigUpdateRequest",
    "ConfigUpdateResponse",
    "AlertPayload",
    "InvestigationListResponse",
    "PaginatedResponse",
    "ErrorResponse",
    "ChargebackRespondRequest",
    "ChargebackRespondResponse",
    "ChargebackSubmitRequest",
    "ChargebackSubmitResponse",
]


class GeoPoint(BaseModel):
    lat: float
    lon: float


class ScoreRequest(BaseModel):
    txn_id: str = Field(..., description="Unique transaction identifier")
    user_id: str
    merchant_id: str
    amount: float = Field(..., gt=0)
    timestamp: datetime
    device_fingerprint: str = ""
    location: GeoPoint | None = None
    mcc_code: str = ""
    txn_type: Literal["P2P", "P2M", "COLLECT"] = "P2P"
    counterparty_user_id: str | None = Field(
        default=None,
        description="Recipient user id for P2P transactions (wired into the graph)",
    )


class BatchScoreRequest(BaseModel):
    transactions: list[ScoreRequest]


class FraudScoreResponse(BaseModel):
    txn_id: str
    decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    fraud_probability: float
    layer_triggered: Literal["L1_STATISTICAL", "L2_GNN", "ENSEMBLE"]
    evidence: dict[str, Any]
    latency_ms: float
    model_version: str


class BatchScoreResponse(BaseModel):
    results: list[FraudScoreResponse]
    batch_latency_ms: float


class InvestigationReportResponse(BaseModel):
    txn_id: str
    narrative: str
    fraud_type: Literal["MULE_RING", "BURST_ATTACK", "MERCHANT_COLLUSION", "ACCOUNT_TAKEOVER", "OTHER"]
    confidence: str
    recommended_action: str
    key_evidence: list[str]
    reasoning: str
    generated_at: datetime


class FeedbackRequest(BaseModel):
    txn_id: str
    analyst_id: str
    original_decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    analyst_decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    reason: str = ""
    category: Literal["FALSE_POSITIVE", "FALSE_NEGATIVE", "TRUE_POSITIVE", "TRUE_NEGATIVE"] = "TRUE_POSITIVE"


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str = ""
    message: str = ""


class HealthCheckResponse(BaseModel):
    status: str
    checks: dict[str, str]


class AgentHealthResponse(BaseModel):
    agents: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


class ConfigUpdateResponse(BaseModel):
    status: str
    key: str
    old_value: Any = None
    new_value: Any = None


class AlertPayload(BaseModel):
    txn_id: str
    fraud_probability: float
    decision: str
    fraud_type: str = ""
    narrative_preview: str = ""
    timestamp: str = ""
    priority: int = 3


class InvestigationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[dict]


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[dict]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str = ""
