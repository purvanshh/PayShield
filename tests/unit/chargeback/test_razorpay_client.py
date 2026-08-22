"""RazorpayClient tests (Phase 10) - httpx MockTransport."""

import httpx
import pytest

from chargeback.exceptions import RazorpaySubmitError
from chargeback.razorpay_client import RazorpayClient


class TestRazorpayClient:
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

    async def test_submit_contest_rejection_raises_with_metadata(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422, json={"error": {"code": "BAD_REQUEST", "description": "Invalid evidence"}}
            )

        client = self._client(handler)
        with pytest.raises(RazorpaySubmitError) as exc_info:
            await client.submit_contest("disp_1", {"contest": True})
        assert exc_info.value.status_code == 422
        assert exc_info.value.response["error"]["code"] == "BAD_REQUEST"
        assert "Invalid evidence" in str(exc_info.value)
        await client.close()

    async def test_unreachable_produces_503_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = self._client(handler)
        with pytest.raises(RazorpaySubmitError) as exc_info:
            await client.submit_contest("disp_1", {})
        assert exc_info.value.status_code == 503
        await client.close()

    async def test_fetch_merchant_evidence_returns_none_on_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        client = self._client(handler)
        assert await client.fetch_merchant_evidence("TXN_1", "disp_1") is None
        await client.close()
