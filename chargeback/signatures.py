"""Webhook signature verification (Track 02 - Phase 11).

Razorpay signs webhook payloads with an HMAC-SHA256 of the raw body using
the configured webhook secret; the digest is presented as
``X-Razorpay-Signature``. Kept as a pure function so the verification logic
is unit-testable without an HTTP stack.
"""

import hashlib
import hmac


def compute_signature(secret: str, payload: bytes) -> str:
    """HMAC-SHA256 hex digest of the raw payload."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    """Constant-time comparison of supplied vs computed signature.

    Returns False (never raises) on any mismatch or missing secret, so the
    webhook endpoint can reject cleanly with 400.
    """
    if not secret or not signature:
        return False
    computed = compute_signature(secret, payload)
    return hmac.compare_digest(computed, signature)
