"""Razorpay → PayShield feature adapter (Track 02 - Phase 4).

Maps Razorpay's order / payment / refund payloads onto PayShield's
return-risk input schema (``api.schemas.return_risk.ReturnScoreRequest``)
and onto training labels for the return-risk model. This is the production
integration point: a merchant's ``order.paid`` webhook becomes a
checkout-time risk score, and every ``refund.processed`` becomes a
ground-truth label for the nightly retrain.

Units: Razorpay amounts are in **paise**; PayShield works in ₹.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.schemas.return_risk import normalize_return_reason

PaymentMethodLiteral = Literal["UPI", "CARD", "COD", "NETBANKING", "WALLET"]


class RazorpayOrder(BaseModel):
    """Subset of the Razorpay order object PayShield cares about."""

    id: str
    amount: int = Field(..., description="Order amount in paise")
    currency: str = "INR"
    receipt: str | None = None
    status: str = "created"
    attempts: int = 0
    notes: dict[str, str] | None = None
    created_at: int = Field(..., description="Unix timestamp (seconds)")


class RazorpayPayment(BaseModel):
    """Subset of the Razorpay payment object (captured payment)."""

    id: str
    order_id: str = ""
    amount: int = 0
    status: str = "captured"
    method: str = "upi"
    captured: bool = True
    international: bool = False
    description: str | None = None
    refund_status: str | None = None
    amount_refunded: int = 0
    notes: dict[str, str] | None = None
    created_at: int = 0


class RazorpayRefund(BaseModel):
    """Subset of the Razorpay refund object."""

    id: str
    payment_id: str = ""
    amount: int = 0
    status: str = "processed"
    speed_processed: str = "normal"
    receipt: str | None = None
    notes: dict[str, str] | None = None
    created_at: int = 0


class PayShieldScoringInput(BaseModel):
    """The exact fields the return-risk scorer needs, extracted from Razorpay.

    Mirrors ``api.schemas.return_risk.ReturnScoreRequest`` so a merchant's
    webhook payload can be handed straight to ``POST /v1/return/score``.
    """

    order_id: str
    user_id: str
    merchant_id: str
    amount: Decimal = Field(..., gt=0, description="Order amount in INR")
    currency: str = "INR"
    category: str = "fashion"
    payment_method: PaymentMethodLiteral = "UPI"
    cod_flag: bool = False
    device_fingerprint: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_method: str = "upi"
    source_event: str = "order.paid"


class RazorpayAdapter:
    """Transforms Razorpay entities into PayShield inputs and labels."""

    # Merchant category hints from ``order.notes`` / receipt prefixes.
    # In production the merchant registers their own mapping in the
    # PayShield dashboard; these are sensible dev defaults.
    CATEGORY_MAP = {
        "FASHION": "fashion",
        "MYNT": "fashion",
        "FOOT": "footwear",
        "ELEC": "electronics",
        "GROC": "groceries",
        "HOME": "home",
        "BEAUTY": "beauty",
        "SPORTS": "sports",
    }

    # Razorpay payment ``method`` field → PayShield enum surface.
    METHOD_MAP: dict[str, PaymentMethodLiteral] = {
        "card": "CARD",
        "upi": "UPI",
        "netbanking": "NETBANKING",
        "wallet": "WALLET",
        "emi": "CARD",
        "cod": "COD",
    }

    @classmethod
    def order_to_scoring_input(
        cls,
        order: RazorpayOrder | dict[str, Any],
        payment: RazorpayPayment | dict[str, Any] | None = None,
    ) -> PayShieldScoringInput:
        """Convert a Razorpay order (+ optional payment) to a scoring input.

        ``notes`` carry merchant hints the dashboard stores on the order at
        creation: ``merchant_id``, ``customer_id``, ``category``, ``cod``.
        Everything degrades to safe defaults rather than raising.
        """
        if not isinstance(order, RazorpayOrder):
            order = RazorpayOrder(**order)
        payment_obj = None
        if payment is not None:
            payment_obj = (
                payment if isinstance(payment, RazorpayPayment) else RazorpayPayment(**payment)
            )

        notes = order.notes or {}
        pay_notes = (payment_obj.notes or {}) if payment_obj else {}

        amount_inr = Decimal(order.amount) / Decimal(100)

        method_raw = (
            payment_obj.method
            if payment_obj and payment_obj.method
            else notes.get("payment_method", "upi")
        )
        method = cls.METHOD_MAP.get(str(method_raw).lower(), "UPI")

        cod_hint = notes.get("cod", "false").lower() in {"true", "1", "yes"}
        cod_flag = method == "COD" or cod_hint

        category = cls._category_from(notes.get("category", ""), order.receipt or "")

        user_id = pay_notes.get("customer_id") or notes.get("customer_id") or f"anon_{order.id}"

        return PayShieldScoringInput(
            order_id=order.id,
            user_id=user_id,
            merchant_id=notes.get("merchant_id", f"merchant_{order.receipt or 'default'}"),
            amount=amount_inr,
            currency=order.currency or "INR",
            category=category,
            payment_method=method,
            cod_flag=cod_flag,
            device_fingerprint=pay_notes.get("device_fingerprint", ""),
            timestamp=datetime.fromtimestamp(order.created_at),
            raw_method=str(method_raw),
            source_event="order.paid",
        )

    @classmethod
    def refund_to_label(
        cls,
        payment: RazorpayPayment | dict[str, Any],
        refund: RazorpayRefund | dict[str, Any],
        order: RazorpayOrder | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert a Razorpay refund into a return-risk ground-truth label.

        Every processed refund is a positive example. The label is stored
        (``return_risk:labels``) and consumed by the nightly reflection /
        retraining path.
        """
        payment_obj = (
            payment if isinstance(payment, RazorpayPayment) else RazorpayPayment(**payment)
        )
        refund_obj = refund if isinstance(refund, RazorpayRefund) else RazorpayRefund(**refund)

        user_id = None
        if order is not None:
            order_obj = order if isinstance(order, RazorpayOrder) else RazorpayOrder(**order)
            notes = order_obj.notes or {}
            user_id = notes.get("customer_id") or f"anon_{order_obj.id}"
        else:
            user_id = (payment_obj.notes or {}).get("customer_id", f"anon_{payment_obj.order_id}")

        reason_raw = (payment_obj.notes or {}).get("return_reason", "")
        return {
            "order_id": payment_obj.order_id or f"order_{refund_obj.payment_id}",
            "payment_id": payment_obj.id,
            "refund_id": refund_obj.id,
            "user_id": user_id,
            "returned": True,
            "refund_amount": Decimal(refund_obj.amount) / Decimal(100),
            "refund_speed": refund_obj.speed_processed,
            "return_reason": normalize_return_reason(reason_raw),
            "label": "high_risk_return",
            "timestamp": datetime.fromtimestamp(refund_obj.created_at or 0).isoformat(),
        }

    @classmethod
    def scoring_input_to_payload(cls, inp: PayShieldScoringInput) -> dict[str, Any]:
        """Serialize a scoring input for the wire (``POST /v1/return/score``)."""
        return {
            "order_id": inp.order_id,
            "user_id": inp.user_id,
            "merchant_id": inp.merchant_id,
            "amount": str(inp.amount),
            "currency": inp.currency,
            "category": inp.category,
            "payment_method": inp.payment_method,
            "cod_flag": inp.cod_flag,
            "device_fingerprint": inp.device_fingerprint,
            "timestamp": inp.timestamp.isoformat(),
        }

    @classmethod
    def _category_from(cls, category_hint: str, receipt: str) -> str:
        hint = (category_hint or "").strip().lower()
        if hint in {
            "fashion",
            "electronics",
            "groceries",
            "home",
            "beauty",
            "sports",
            "footwear",
            "furniture",
        }:
            return hint
        if hint == "grocery":
            return "groceries"
        prefix = (receipt or "").upper().split("-")[0][:8]
        return cls.CATEGORY_MAP.get(prefix, "fashion")
