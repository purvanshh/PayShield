"""Import/smoke tests for the chargeback package (Phase 8 hello worlds)."""



class TestChargebackPackage:
    def test_exceptions_importable(self):
        from chargeback import (
            ChargebackError,
            ChargebackTransactionNotFoundError,
            InsufficientEvidenceError,
            RazorpaySubmitError,
        )

        assert issubclass(ChargebackTransactionNotFoundError, ChargebackError)
        assert issubclass(InsufficientEvidenceError, ChargebackError)
        assert issubclass(RazorpaySubmitError, ChargebackError)

    def test_all_modules_import(self):
        import chargeback.evidence_collector  # noqa: F401
        import chargeback.narrative_generator  # noqa: F401
        import chargeback.razorpay_client  # noqa: F401
        import chargeback.rebuttal_builder  # noqa: F401

    def test_schemas_import(self):
        from api.schemas.chargeback import (
            Attachment,
            AuditLogEntry,
            ChargebackRebuttalDocument,
            EvidenceBundle,
        )

        doc = ChargebackRebuttalDocument(
            dispute_id="disp_1",
            payment_id="pay_1",
            transaction_id="TXN_1",
            reason_code="10.4",
            response_type="REJECT",
            response_deadline="2026-09-01T00:00:00Z",
            evidence=EvidenceBundle(attachments=[Attachment(evidence_type="invoice", url="https://x")]),
            audit_trail=[AuditLogEntry(timestamp="2026-08-21T00:00:00Z", action="L1_EVIDENCE_COLLECTED", agent="transaction_agent")],
        )
        assert doc.evidence.completeness_score == 0.0
        assert doc.razorpay_payload == {}


class TestRazorpaySubmitError:
    def test_carries_response(self):
        from chargeback import RazorpaySubmitError

        err = RazorpaySubmitError("nope", status_code=502, response={"error": {"code": "BAD"}})
        assert err.status_code == 502
        assert err.response["error"]["code"] == "BAD"
