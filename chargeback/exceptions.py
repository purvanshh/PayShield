"""Chargeback domain exceptions (Track 02 - Phase 8)."""

from typing import Any


class ChargebackError(Exception):
    """Base error for the evidence responder.

    Raised when a rebuttal cannot be assembled or submitted; never causes a
    bare 500 - the API maps it to 404/422/502 per the error strategy in
    docs/technical/chargeback_error_handling.md.
    """


class RazorpayAPIError(ChargebackError):
    """Raised when Razorpay returns an error (mirrors status + body)."""

    def __init__(self, message: str, status_code: int = 0, razorpay_error: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.razorpay_error = razorpay_error or {}


class RazorpaySubmitError(RazorpayAPIError):
    """Razorpay rejected or was unreachable during submission.

    Backwards-compatible alias exposing ``response`` for the JSON error body
    in addition to ``razorpay_error``.
    """

    def __init__(self, message: str, status_code: int = 0, response: dict[str, Any] | None = None):
        super().__init__(message, status_code=status_code, razorpay_error=response)
        self.response = self.razorpay_error


class ChargebackTransactionNotFoundError(ChargebackError):
    """The internal transaction id is absent from the audit chain."""


class ChargebackDisputeNotFoundError(ChargebackError):
    """The dispute id is unknown (wrong webhook payload, or outside retention)."""


class InsufficientEvidenceError(ChargebackError):
    """Evidence completeness below threshold - do not submit on air."""
