"""RazorpayClient tests (Phase 11) - mock mode and httpx MockTransport."""
# ruff: noqa: ARG001 -- handler doubles ignore the request object

import httpx
import pytest

from api.schemas.chargeback import ChargebackRebuttalDocument
from chargeback.exceptions import RazorpayAPIError
from chargeback.razorpay_client import RazorpayClient
from chargeback.razorpay_mock_fixtures import (
    mock_contest_response,
    mock_get_chargeback,
    mock_upload_response,
)


def _rebuttal(dispute_id="disp_1") -> ChargebackRebuttalDocument:
    return ChargebackRebuttalDocument(
        dispute_id=dispute_id,
        payment_id="pay_1",
        transaction_id="TXN_1",
        reason_code="10.4",
        response_type="REJECT",
        response_deadline="2026-09-01T00:00:00Z",
        razorpay_payload={"contest": True, "evidence": {"summary": "ok"}},
    )


class TestMockMode:
    async def test_get_chargeback_returns_realistic_entity(self):
        client = RazorpayClient(mock_mode=True)
        data = await client.get_chargeback("disp_2Vw9aZ0q3X")
        assert data["entity"] == "dispute"
        assert data["reason_code"] in ("10.4", "10.5")
        assert data["respond_by"] > data["created_at"]
        assert data["status"] == "open"
        await client.close()

    async def test_contest_chargeback_envelope(self):
        client = RazorpayClient(mock_mode=True)
        result = await client.contest_chargeback("disp_1", _rebuttal())
        assert result["status"] == "SUCCESS"
        assert result["mock"] is True
        assert result["razorpay_response"]["status"] == "under_review"
        assert result["razorpay_response"]["contest"] is True
        await client.close()

    async def test_contest_accept_rebuttal_yields_accepted(self):
        doc = _rebuttal()
        doc = doc.model_copy(update={"razorpay_payload": {"contest": False}})
        client = RazorpayClient(mock_mode=True)
        result = await client.contest_chargeback("disp_1", doc)
        assert result["razorpay_response"]["status"] == "accepted"
        await client.close()

    async def test_upload_evidence_file_mock(self):
        client = RazorpayClient(mock_mode=True)
        out = await client.upload_evidence_file("disp_1", "invoice.pdf", "invoice")
        assert out["file_id"] == "file_mock_1"
        await client.close()

    async def test_custom_mock_response_override(self):
        client = RazorpayClient(
            mock_mode=True,
            mock_responses={"disp_9": {"status": "won", "id": "disp_9", "entity": "dispute"}},
        )
        data = await client.get_chargeback("disp_9")
        assert data["status"] == "won"
        await client.close()


class TestRealMode:
    def _client(self, handler) -> RazorpayClient:
        return RazorpayClient(
            api_key="key_id", api_secret="key_secret", transport=httpx.MockTransport(handler)
        )

    async def test_submit_contest_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/disputes/disp_1/contest"
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"status": "contested", "id": "disp_1"})

        client = self._client(handler)
        out = await client.submit_contest("disp_1", {"contest": True, "evidence": {}})
        assert out["status"] == "contested"
        await client.close()

    async def test_contest_chargeback_posts_document_payload(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/disputes/disp_1/contest"
            return httpx.Response(200, json={"status": "under_review", "id": "disp_1"})

        client = self._client(handler)
        out = await client.contest_chargeback("disp_1", _rebuttal())
        assert out["status"] == "SUCCESS"
        assert out["razorpay_response"]["status"] == "under_review"
        assert out["rebuttal_id"] == "disp_1"
        await client.close()

    async def test_rejection_raises_with_metadata(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422, json={"error": {"code": "BAD_REQUEST", "description": "Invalid evidence"}}
            )

        client = self._client(handler)
        with pytest.raises(RazorpayAPIError) as exc_info:
            await client.get_chargeback("disp_bad")
        assert exc_info.value.status_code == 422
        assert exc_info.value.razorpay_error["error"]["code"] == "BAD_REQUEST"
        assert "Invalid evidence" in str(exc_info.value)
        await client.close()

    async def test_submit_error_metadata(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"description": "bad"}})

        client = self._client(handler)
        with pytest.raises(RazorpayAPIError) as exc_info:
            await client.submit_contest("disp_1", {})
        assert exc_info.value.status_code == 400
        assert exc_info.value.razorpay_error["error"]["description"] == "bad"
        await client.close()

    async def test_unreachable_produces_503_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = self._client(handler)
        with pytest.raises(RazorpayAPIError) as exc_info:
            await client.submit_contest("disp_1", {})
        assert exc_info.value.status_code == 503
        await client.close()

    async def test_fetch_merchant_evidence_returns_none_on_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        client = self._client(handler)
        assert await client.fetch_merchant_evidence("TXN_1", "disp_1") is None
        await client.close()


class TestMockFixtures:
    def test_status_sequence_valid(self):
        for outcome in ("under_review", "won", "lost"):
            data = mock_contest_response("disp_1", outcome=outcome)
            assert data["status"] == outcome
            assert data["contest"] is True

    def test_mock_get_chargeback_payment_id(self):
        data = mock_get_chargeback("disp_ABCDEF", scenario="service")
        assert data["payment_id"] == "pay_ABCDEF"
        assert data["reason_code"] == "13.1"

    def test_mock_upload(self):
        data = mock_upload_response("disp_1", file_id="file_7")
        assert data["file_id"] == "file_7"
