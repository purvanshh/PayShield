"""Razorpay disputes client (Track 02 - Phase 11 stub, wired in Phase 10).

Speaks the Razorpay disputes API:
- ``POST /v1/disputes/{id}/contest`` -- submit a contest (reject) with evidence
- ``GET/POST`` helpers to refresh merchant-provided evidence

Contract note: Razorpay's own docs moved from */chargebacks* to
*/disputes* (see docs/reference/chargeback_protocols.md verification note);
payload construction is centralized in the rebuttal builder so a field
rename touches one function.

Env overrides: RAZORPAY_API_KEY, RAZORPAY_API_SECRET, RAZORPAY_API_BASE.
"""

import logging
import os
from typing import Any

import httpx

from chargeback.exceptions import RazorpaySubmitError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Minimal async Razorpay disputes API client (mockable transport)."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or os.getenv("RAZORPAY_API_KEY", "")
        self.api_secret = api_secret or os.getenv("RAZORPAY_API_SECRET", "")
        self.base_url = (base_url or os.getenv("RAZORPAY_API_BASE", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._transport_arg = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=httpx.BasicAuth(self.api_key, self.api_secret),
                timeout=self.timeout,
                transport=self._transport_arg,
            )
        return self._client

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def submit_contest(self, dispute_id: str, payload: dict[str, Any]) -> dict:
        """POST the assembled contest payload; mirror Razorpay's response.

        Raises:
            RazorpaySubmitError: on HTTP/4xx/5xx with the body mirrored.
        """
        url = f"{self.base_url}/disputes/{dispute_id}/contest"
        try:
            resp = await self.client.post(url, json=payload)
        except httpx.HTTPError as e:
            logger.warning("razorpay contest request failed: %s", e)
            raise RazorpaySubmitError(f"Razorpay unreachable: {e}", status_code=503) from e
        if resp.status_code >= 400:
            body = self._safe_json(resp.text)
            logger.warning(
                "razorpay contest rejected status=%s body=%s", resp.status_code, resp.text[:300]
            )
            raise RazorpaySubmitError(
                body.get("error", {}).get("description", "Razorpay rejected the submission"),
                status_code=resp.status_code,
                response=body,
            )
        data = self._safe_json(resp.text)
        logger.info("razorpay contest accepted for dispute %s: %s", dispute_id, data.get("status"))
        return data

    async def fetch_merchant_evidence(
        self, transaction_id: str, dispute_id: str = ""  # noqa: ARG002 - Phase 11 wiring
    ) -> dict | None:
        """Placeholder for the Phase 11 merchant evidence wiring.

        Intended to return a mapping compatible with
        ``api.schemas.chargeback.MerchantEvidence`` (delivery_proof,
        customer_communication, refund_policy, terms_of_service). The audit
        evidence chain is the primary evidence source; this enriches it from
        the merchant's own systems via the Razorpay orders API.
        """
        try:
            resp = await self.client.get(f"{self.base_url}/disputes/{dispute_id}")
            if resp.status_code != 200:
                return None
            data = self._safe_json(resp.text)
            return {
                "dispute": data,
                "plain_note": "merchant evidence enrichment lands in Phase 11 "
                "(Razorpay orders endpoint + secure attachment bucket)",
            }
        except httpx.HTTPError as e:
            logger.debug("merchant evidence fetch skipped: %s", e)
            return None

    @staticmethod
    def _safe_json(text: str) -> dict:
        try:
            import json

            return json.loads(text) if text else {}
        except Exception:
            return {}
