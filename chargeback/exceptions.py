"""Chargeback domain exceptions (Track 02 - Phase 8)."""


class ChargebackError(Exception):
    """Base error for the evidence responder.

    Raised when a rebuttal cannot be assembled or submitted; never causes a
    bare 500 - the API maps it to 404/422/502 per the error strategy in
    docs/technical/chargeback_error_handling.md.
    """


class ChargebackTransactionNotFoundError(ChargebackError):
    """The internal transaction id is absent from the audit chain."""


class ChargebackDisputeNotFoundError(ChargebackError):
    """The dispute id is unknown (wrong webhook payload, or outside retention)."""


class InsufficientEvidenceError(ChargebackError):
    """Evidence completeness below threshold - do not submit on air."""


class RazorpaySubmitError(ChargebackError):
    """Razorpay rejected or was unreachable during submission.

    Carries ``response`` (the JSON error body when present) and ``status_code``.
    """

    def __init__(self, message: str, status_code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}
