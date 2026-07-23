from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class FraudPattern(str, Enum):
    MULE_RING = "MULE_RING"
    BURST_ATTACK = "BURST_ATTACK"
    MERCHANT_COLLUSION = "MERCHANT_COLLUSION"
    ACCOUNT_TAKEOVER = "ATO"


class User(BaseModel):
    user_id: str
    age: int = Field(ge=18, le=100)
    income_tier: int = Field(ge=1, le=5)
    city_tier: int = Field(ge=1, le=4)
    credit_score: int = Field(ge=300, le=900)
    account_age_days: int = Field(ge=0)
    kyc_tier: int = Field(ge=1, le=3)
    preferred_mcc_categories: list[str] = Field(default_factory=list)
    typical_txn_hour: int = Field(ge=0, le=23)
    typical_txn_amount_median: float = Field(gt=0)
    avg_monthly_txn_count: int = Field(ge=0)
    device_count: int = Field(ge=1, le=5)
    city: str = ""
    lat: float = 0.0
    lon: float = 0.0
    income_tier_label: str = "medium"


class Merchant(BaseModel):
    merchant_id: str
    name: str = ""
    mcc_code: str
    city_tier: int = Field(ge=1, le=4)
    avg_txn_amount: float = Field(gt=0)
    refund_rate: float = Field(ge=0.0, le=1.0)
    account_age_days: int = Field(ge=0)
    is_shell: bool = False
    category: str = "small"
    benford_chi2: float = 0.0


class Device(BaseModel):
    device_id: str
    os_family: Literal["android", "ios"]
    app_version: str
    is_emulator: bool = False
    first_seen_timestamp: datetime
    user_id: str = ""


class Transaction(BaseModel):
    txn_id: str
    user_id: str
    merchant_id: str
    amount: float = Field(gt=0)
    timestamp: datetime
    device_fingerprint: str
    location: tuple[float, float]
    mcc_code: str
    txn_type: Literal["P2P", "P2M", "COLLECT"]
    status: Literal["SUCCESS", "FAILED", "PENDING"] = "SUCCESS"
    is_fraud: bool = False
    fraud_pattern: FraudPattern | None = None
