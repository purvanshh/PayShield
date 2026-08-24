"""Razorpay platform integrations (Track 02).

PayShield is built on Razorpay's infrastructure: the return-risk scorer is
meant to sit inside a Razorpay merchant flow as a pre-shipping risk layer.
This package maps Razorpay's order/payment/refund payloads onto PayShield's
feature schema, verifies their webhook signatures, and calls Razorpay's
test-mode orders/payments/refunds APIs.

- ``razorpay_adapter.py``          payload → feature schema / labels
- ``razorpay_orders_client.py``    orders/payments/refunds test-mode client
- ``razorpay_webhook_handler.py``  FastAPI webhook routes (signed)
- ``fixtures/``                    realistic sample payloads
"""

from integrations.razorpay_adapter import (
    PaymentMethodLiteral,
    PayShieldScoringInput,
    RazorpayAdapter,
    RazorpayOrder,
    RazorpayRefund,
)

__all__ = [
    "PaymentMethodLiteral",
    "RazorpayOrder",
    "RazorpayRefund",
    "PayShieldScoringInput",
    "RazorpayAdapter",
]
