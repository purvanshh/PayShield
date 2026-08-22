"""Razorpay disputes client (Track 02 - Phase 11).

Handles communication with Razorpay's dispute/contest endpoints, supporting
both real API calls and a deterministic mock mode for development and tests
(no production keys needed, no rate-limit exposure, fully replayable).

Payload construction is centralised in the rebuttal builder
(``ChargebackRebuttalBuilder._build_razorpay_payload``); unit tests inject an
``httpx`` transport and/or enable ``mock_mode``.

Env overrides: RAZORPAY_API_KEY, RAZORPAY_API_SECRET, RAZORPAY_API_BASE,
RAZORPAY_WEBHOOK_SECRET.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from chargeback.exceptions import RazorpayAPIError
from chargeback.razorpay_mock_fixtures import (
    mock_contest_response,
    mock_get_chargeback,
    mock_upload_response,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Async Razorpay disputes API client (real or mock mode).

    Args:
        api_key: Razorpay key id (env ``RAZORPAY_API_KEY``).
        api_secret: Razorpay key secret (env ``RAZORPAY_API_SECRET``).
        base_url: API base (env ``RAZORPAY_API_BASE``, defaults to the V1
            endpoint for the disputes resource).
        mock_mode: when True, no HTTP is performed; fixtures are returned so
            the whole flow is testable without credentials.
        mock_responses: optional override dict of responses per endpoint.
        transport: optional ``httpx`` transport for unit tests.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "",
        mock_mode: bool = False,
        mock_responses: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("RAZORPAY_API_KEY", "rzp_test_mock")
        self.api_secret = api_secret or os.getenv("RAZORPAY_API_SECRET", "mock_secret")
        self.base_url = (base_url or os.getenv("RAZORPAY_API_BASE", DEFAULT_BASE_URL)).rstrip("/")
        self.mock_mode = mock_mode
        self.mock_responses = mock_responses or {}
        self.timeout = timeout
        self._transport_arg = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=(httpx.BasicAuth(self.api_key, self.api_secret) if not self.mock_mode else None),
                timeout=self.timeout,
                transport=self._transport_arg,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ #
    # disputes resource                                                   #
    # ------------------------------------------------------------------ #

    async def get_chargeback(self, dispute_id: str) -> dict[str, Any]:
        """Fetch the dispute entity from Razorpay."""
        if self.mock_mode:
            if dispute_id in self.mock_responses:
                return dict(self.mock_responses[dispute_id])
            return mock_get_chargeback(dispute_id)
        resp = await self._request("GET", f"{self.base_url}/disputes/{dispute_id}")
        return self._handle(resp, f"disputes/{dispute_id}")

    async def contest_chargeback(self, dispute_id: str, rebuttal: Any) -> dict[str, Any]:
        """Submit an assembled rebuttal document to Razorpay.

        This is the critical submission method: it takes the
        :class:`ChargebackRebuttalDocument` assembled by the builder and posts
        its ``razorpay_payload`` (contest flag + evidence slots) to the
        disputes contest endpoint.

        Returns a submission envelope with the Razorpay entity echoed back.
        """
        if self.mock_mode:
            if dispute_id in self.mock_responses:
                return dict(self.mock_responses[dispute_id])
            return self._mock_contest_chargeback(dispute_id, rebuttal)

        payload = getattr(rebuttal, "razorpay_payload", None) or {"contest": True}
        resp = await self._request(
            "POST", f"{self.base_url}/disputes/{dispute_id}/contest", json=payload
        )
        data = self._handle(resp, f"disputes/{dispute_id}/contest")
        return {
            "status": "SUCCESS",
            "razorpay_response": data,
            "submitted_at": datetime.utcnow().isoformat(),
            "rebuttal_id": getattr(rebuttal, "dispute_id", dispute_id),
        }

    async def submit_contest(self, dispute_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Low-level raw contest submission (used by the submit endpoint).

        ``contest_chargeback`` is preferred - it works at the document level
        and is the only path the API routes use.
        """
        if self.mock_mode:
            return self._mock_contest_response(dispute_id, payload)
        resp = await self._request(
            "POST", f"{self.base_url}/disputes/{dispute_id}/contest", json=payload
        )
        return self._handle(resp, f"disputes/{dispute_id}/contest")

    async def upload_evidence_file(
        self, dispute_id: str, file_path: str | Path, evidence_type: str
    ) -> dict[str, Any]:
        """Upload a file attachment (documents slot) for a dispute."""
        if self.mock_mode:
            return mock_upload_response(dispute_id)
        path = Path(file_path)
        import asyncio

        content = await asyncio.to_thread(path.read_bytes)
        files = {"file": (path.name, content, "application/pdf")}
        data = {"evidence_type": evidence_type}
        resp = await self._request(
            "POST",
            f"{self.base_url}/disputes/{dispute_id}/evidence",
            files=files,
            data=data,
        )
        return self._handle(resp, f"disputes/{dispute_id}/evidence")

    async def fetch_merchant_evidence(
        self, transaction_id: str, dispute_id: str = ""  # noqa: ARG002 - Phase 11 wiring
    ) -> dict[str, Any] | None:
        """Enrichment hook for merchant-provided evidence (Phase 11).

        Returns a mapping compatible with
        ``api.schemas.chargeback.MerchantEvidence`` when the merchant's own
        systems expose delivery/comms records; otherwise ``None`` and the
        evidence bundle falls back to audit-chain data.
        """
        try:
            if self.mock_mode:
                return None
            resp = await self.client.get(f"{self.base_url}/disputes/{dispute_id}")
            if resp.status_code != 200:
                return None
            data = self._safe_json(resp.text)
            return {"dispute": data}
        except httpx.HTTPError as e:
            logger.debug("merchant evidence fetch skipped: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # mocks                                                               #
    # ------------------------------------------------------------------ #

    def _mock_contest_chargeback(self, dispute_id: str, rebuttal: Any) -> dict[str, Any]:
        payload = getattr(rebuttal, "razorpay_payload", {})
        outcome = payload.get("contest", True) and "under_review" or "accepted"
        return {
            "status": "SUCCESS",
            "razorpay_response": mock_contest_response(dispute_id, outcome=outcome),
            "submitted_at": datetime.utcnow().isoformat(),
            "rebuttal_id": getattr(rebuttal, "dispute_id", dispute_id),
            "mock": True,
        }

    def _mock_contest_response(self, dispute_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        outcome = "under_review" if payload.get("contest", True) else "accepted"
        return mock_contest_response(dispute_id, outcome=outcome)

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a request, converting transport failures to a 503 error."""
        try:
            return await self.client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            logger.warning("razorpay %s request failed: %s", method, e)
            raise RazorpayAPIError(f"Razorpay unreachable: {e}", status_code=503) from e

    def _handle(self, resp: httpx.Response, context: str) -> dict[str, Any]:
        if resp.status_code >= 400:
            body = self._safe_json(resp.text)
            logger.warning(
                "razorpay %s rejected status=%s body=%s", context, resp.status_code, resp.text[:300]
            )
            raise RazorpayAPIError(
                body.get("error", {}).get("description", "Razorpay rejected the request"),
                status_code=resp.status_code,
                razorpay_error=body,
            )
        return self._safe_json(resp.text)

    @staticmethod
    def _safe_json(text: str) -> dict[str, Any]:
        try:
            import json

            return json.loads(text) if text else {}
        except Exception:
            return {}
