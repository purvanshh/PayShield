"""Webhook signature verification tests (Phase 11)."""

from chargeback.signatures import compute_signature, verify_signature


class TestWebhookSignatures:
    def test_round_trip_accepts(self):
        payload = b'{"event": "chargeback.created"}'
        sig = compute_signature("secret-1", payload)
        assert verify_signature("secret-1", payload, sig) is True

    def test_wrong_secret_rejects(self):
        payload = b'{"event": "chargeback.created"}'
        sig = compute_signature("secret-2", payload)
        assert verify_signature("secret-1", payload, sig) is False

    def test_tampered_payload_rejects(self):
        payload = b'{"event": "chargeback.created"}'
        sig = compute_signature("secret-1", payload)
        assert verify_signature("secret-1", payload + b" ", sig) is False

    def test_missing_parts_reject(self):
        payload = b"{}"
        assert verify_signature("", payload, "abc") is False
        assert verify_signature("secret", payload, "") is False

    def test_matches_hmac_sha256_hex(self):
        import hashlib
        import hmac

        secret = "webhook-secret"
        payload = b'{"event":"chargeback.closed"}'
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert compute_signature(secret, payload) == expected
