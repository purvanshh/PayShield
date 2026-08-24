"""Razorpay test-mode orders/payments/refunds client (Track 02 - Phase 4).

Thin ``httpx`` client for Razorpay's **orders, payments and refunds**
resources — the objects the return-risk scoring flow actually consumes.
Uses the shared key/secret pair via HTTP Basic auth (the standard Razorpay
auth), with an offline ``mock_mode`` for development and tests (no network,
no credentials, deterministic fixtures).

Env overrides: ``RAZORPAY_KEY_ID``, ``RAZORPAY_KEY_SECRET``,
``RAZORPAY_API_BASE``.

In production a merchant enables PayShield by registering the webhook URL
in the Razorpay Dashboard; PayShield then reads orders/refunds from this
client *and* receives them as signed webhooks. The webhook path is primary;
this client is the reconciliation/backfill path.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayOrdersClient:
    """Async test-mode client for orders, payments and refunds."""

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str = "",
        mock_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID", "rzp_test_mock")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "mock_secret")
        self.base_url = (base_url or os.getenv("RAZORPAY_API_BASE", DEFAULT_BASE_URL)).rstrip("/")
        self.mock_mode = mock_mode
        self.timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=httpx.BasicAuth(self.key_id, self.key_secret),
                timeout=self.timeout,
                transport=self._transport,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ #
    # orders                                                              #
    # ------------------------------------------------------------------ #

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create an order (`POST /orders`) — checkout-time integration."""
        if self.mock_mode:
            return _mock_order(payload)
        return await self._request("POST", "/orders", json=payload)

    async def get_order(self, order_id: str) -> dict[str, Any]:
        """Fetch an order (`GET /orders/{id}`) — used to backfill scoring."""
        if self.mock_mode:
            return _mock_order({"id": order_id, "amount": 250000, "currency": "INR"})
        return await self._request("GET", f"/orders/{order_id}")

    # ------------------------------------------------------------------ #
    # payments                                                            #
    # ------------------------------------------------------------------ #

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """Fetch a payment (`GET /payments/{id}`) to learn method + status."""
        if self.mock_mode:
            return _mock_payment(payment_id)
        return await self._request("GET", f"/payments/{payment_id}")

    # ------------------------------------------------------------------ #
    # refunds                                                             #
    # ------------------------------------------------------------------ #

    async def create_refund(self, payment_id: str, amount_paise: int = 0) -> dict[str, Any]:
        """Issue a refund (`POST /payments/{id}/refund`) — return path."""
        payload = {} if amount_paise <= 0 else {"amount": amount_paise}
        if self.mock_mode:
            return _mock_refund(payment_id)
        return await self._request("POST", f"/payments/{payment_id}/refund", json=payload)

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self.client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.HTTPError as e:
            logger.warning("razorpay %s %s failed: %s", method, path, e)
            raise
        if resp.status_code >= 400:
            logger.warning(
                "razorpay %s %s rejected status=%s body=%s",
                method,
                path,
                resp.status_code,
                resp.text[:300],
            )
            resp.raise_for_status()
        return _safe_json(resp.text)


def _safe_json(text: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(text) if text else {}
    except Exception:
        return {}


def _mock_order(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id", "order_mock_1"),
        "entity": "order",
        "amount": payload.get("amount", 250000),
        "amount_paid": 0,
        "amount_due": payload.get("amount", 250000),
        "currency": payload.get("currency", "INR"),
        "receipt": payload.get("receipt", "rcpt_mock"),
        "status": "attempted",
        "attempts": 0,
        "notes": payload.get("notes", {}),
        "created_at": 1720000000,
    }


def _mock_payment(payment_id: str) -> dict[str, Any]:
    return {
        "id": payment_id,
        "entity": "payment",
        "amount": 250000,
        "currency": "INR",
        "status": "captured",
        "order_id": "order_mock_1",
        "method": "upi",
        "captured": True,
        "international": False,
        "amount_refunded": 0,
        "refund_status": None,
        "description": "mock payment",
        "notes": {},
        "created_at": 1720000000,
    }


def _mock_refund(payment_id: str) -> dict[str, Any]:
    return {
        "id": "refund_mock_1",
        "entity": "refund",
        "amount": 250000,
        "currency": "INR",
        "payment_id": payment_id,
        "status": "processed",
        "speed_processed": "normal",
        "created_at": 1720000100,
    }
