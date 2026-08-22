"""Return-risk scoring schemas (Track 02 - AI Risk Manager).

Contracts for the proactive return-risk scorer. The scorer is called at
checkout / pre-dispatch and returns an explainable score: every feature's
value, weight and contribution are included so merchants can act on the
*why* and not just the number.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

RiskTier = Literal["LOW", "MEDIUM", "HIGH"]

RETURN_REASONS = {
    "DEFECTIVE",
    "SIZE_ISSUE",
    "SIZE_CONFUSION",
    "CHANGED_MIND",
    "QUALITY_ISSUE",
    "LATE_DELIVERY",
    "NOT_AS_DESCRIBED",
    "DUPLICATE_ORDER",
    "OTHER",
}

_ALIASES = {
    "defective": "DEFECTIVE",
    "damaged": "DEFECTIVE",
    "wrong size": "SIZE_ISSUE",
    "small": "SIZE_ISSUE",
    "large": "SIZE_ISSUE",
    "fit": "SIZE_ISSUE",
    "changed my mind": "CHANGED_MIND",
    "not required": "CHANGED_MIND",
    "quality": "QUALITY_ISSUE",
    "late": "LATE_DELIVERY",
    "not as described": "NOT_AS_DESCRIBED",
    "duplicate": "DUPLICATE_ORDER",
}


def normalize_return_reason(raw: str) -> str:
    """Normalise free-text/notes return reasons into the enum surface.

    Unknown reasons never raise - they map to ``OTHER`` so the caller can
    keep feeding webhook ``notes`` without validation failures (see
    docs/reference/return_risk_patterns.md §6).
    """
    key = (raw or "").strip().lower()
    if key.upper() in RETURN_REASONS:
        return key.upper()
    return _ALIASES.get(key, "OTHER")


# ---------------------------------------------------------------------------
# Phase 6 API contract models
# ---------------------------------------------------------------------------


class ReturnItem(BaseModel):
    sku: str
    name: str = ""
    price: Decimal
    quantity: int = Field(..., ge=1)


class ShippingAddress(BaseModel):
    city: str = ""
    tier: int = Field(0, ge=0, description="1=metro, 2=city, 3=tier-2/3, 0=unknown")
    state: str = ""
    pincode: str = ""


class ReturnScoreRequest(BaseModel):
    order_id: str
    user_id: str
    merchant_id: str
    amount: Decimal = Field(..., gt=0)
    currency: str = "INR"
    category: str = Field("fashion", description="Product category for baseline return rate")
    payment_method: Literal["UPI", "CARD", "COD", "NETBANKING", "WALLET"] = "UPI"
    cod_flag: bool = False
    items: list[ReturnItem] = Field(default_factory=list)
    shipping_address: ShippingAddress = Field(default_factory=ShippingAddress)
    device_fingerprint: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FeatureContribution(BaseModel):
    value: Any
    weight: float
    contribution: float
    normalized_value: float | None = None
    source: str = "unknown"


class RuleTriggered(BaseModel):
    rule_id: str
    name: str
    condition: str = ""
    triggered: bool = True
    action: str = ""
    severity: int = 0
    description: str = ""


class ReturnUserProfile(BaseModel):
    total_orders: int = 0
    total_returns: int = 0
    return_rate_30d: float = 0.0
    return_rate_90d: float = 0.0
    return_rate_lifetime: float = 0.0
    avg_return_value: Decimal = Decimal("0")
    max_return_value: Decimal = Decimal("0")
    cod_refusal_rate: float = 0.0
    serial_returner: bool = False
    return_velocity_7d: int = 0
    is_new_user: bool = False
    last_return_date: str = ""


class ReturnScoreResponse(BaseModel):
    order_id: str
    return_risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_tier: RiskTier = "LOW"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    feature_breakdown: dict[str, FeatureContribution] = Field(default_factory=dict)
    rules_triggered: list[RuleTriggered] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    user_profile: ReturnUserProfile = Field(default_factory=ReturnUserProfile)


class ReturnScoreEnvelopeResponse(BaseModel):
    status: str = "SUCCESS"
    data: ReturnScoreResponse
    latency_ms: float = 0.0


class ReturnStatusUpdateRequest(BaseModel):
    """Merchant return-system callback that refreshes the user profile."""

    user_id: str
    order_id: str
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    category: str = ""
    cod_flag: bool = False
    returned: bool = True
    return_reason: str = ""


class ReturnStatusUpdateResponse(BaseModel):
    status: str = "SUCCESS"
    data: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0


class ReturnProfileData(BaseModel):
    """Merchant-dashboard view of a user's return history."""

    user_id: str
    total_orders: int = 0
    total_returns: int = 0
    return_rate_30d: float = 0.0
    return_rate_lifetime: float = 0.0
    serial_returner: bool = False
    avg_return_value: Decimal = Decimal("0")
    is_new_user: bool = False
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Phase 4 feature-store records (Redis shapes, keys prefixed return_risk:)
# ---------------------------------------------------------------------------


class ReturnUserFeatures(BaseModel):
    """Values stored in the Redis hash ``return_risk:user:{user_id}``."""

    return_rate_30d: float = 0.0
    return_rate_90d: float = 0.0
    return_rate_lifetime: float = 0.0
    total_orders: int = 0
    total_returns: int = 0
    avg_return_value: Decimal = Decimal("0")
    max_return_value: Decimal = Decimal("0")
    return_reason_distribution: dict[str, int] = Field(default_factory=dict)
    cod_refusal_rate: float = 0.0
    cod_refusals: int = 0
    serial_returner_flag: bool = False
    return_velocity_7d: int = 0
    first_return_days: int = 0
    return_pattern_score: float = 0.0
    last_return_ts: str = ""
