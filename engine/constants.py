"""Domain-wide enums to eliminate magic strings."""

from enum import Enum


class RuleType(str, Enum):
    VELOCITY = "velocity"
    GEO = "geo"
    BENFORD = "benford"
    BEHAVIOURAL = "behavioural"


class FraudPattern(str, Enum):
    BURST_ATTACK = "BURST_ATTACK"
    MULE_RING = "MULE_RING"
    MERCHANT_COLLUSION = "MERCHANT_COLLUSION"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    CARD_TESTING = "CARD_TESTING"
    SHELL_MERCHANT = "SHELL_MERCHANT"
    VELOCITY_ANOMALY = "VELOCITY_ANOMALY"
    GEO_ANOMALY = "GEO_ANOMALY"
    UNKNOWN = "UNKNOWN"


class LayerName(str, Enum):
    L1_STATISTICAL = "L1_STATISTICAL"
    L2_GNN = "L2_GNN"
    ENSEMBLE = "ENSEMBLE"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class L2Status(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED_NO_GRAPH = "SKIPPED_NO_GRAPH"
    TIMEOUT = "TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    ERROR = "ERROR"
