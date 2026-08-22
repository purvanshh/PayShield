"""Chargeback evidence responder (Track 02 - AI Risk Manager).

Package layout:
- evidence_collector.py  -- retrieve transaction-time evidence from L1/L2/L3
- rebuttal_builder.py    -- assemble a ChargebackRebuttalDocument
- narrative_generator.py -- LLM narrative via Jinja2 + Ollama client
- razorpay_client.py     -- speaks the Razorpay disputes/contest API
- exceptions.py          -- domain error types
"""

from chargeback.exceptions import (
    ChargebackDisputeNotFoundError,
    ChargebackError,
    ChargebackTransactionNotFoundError,
    InsufficientEvidenceError,
    RazorpaySubmitError,
)

__all__ = [
    "ChargebackDisputeNotFoundError",
    "ChargebackError",
    "ChargebackTransactionNotFoundError",
    "InsufficientEvidenceError",
    "RazorpaySubmitError",
]

__version__ = "1.0.0"
