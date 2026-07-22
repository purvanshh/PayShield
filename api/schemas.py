from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GeoPoint(BaseModel):
    lat: float
    lon: float


class TransactionEvent(BaseModel):
    txn_id: str
    user_id: str
    merchant_id: str
    amount: float
    timestamp: datetime
    device_fingerprint: str
    location: GeoPoint
    mcc_code: str
    txn_type: Literal["P2P", "P2M", "COLLECT"]


class FraudScoreResponse(BaseModel):
    txn_id: str
    decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    fraud_probability: float
    layer_triggered: Literal["L1_STATISTICAL", "L2_GNN", "L3_LLM"]
    evidence: dict
    latency_ms: float
    model_version: str


class BatchScoreRequest(BaseModel):
    transactions: list[TransactionEvent]


class BatchScoreResponse(BaseModel):
    results: list[FraudScoreResponse]


class InvestigationReport(BaseModel):
    txn_id: str
    narrative: str
    fraud_type: Literal["MULE_RING", "BURST_ATTACK", "MERCHANT_COLLUSION", "ATO", "OTHER"]
    confidence: float
    recommended_action: str
    generated_at: datetime


class FeedbackRequest(BaseModel):
    txn_id: str
    analyst_id: str
    correct_decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    message: str
