"""Razorpay adapter tests: payload → feature schema and labels."""

import json
from pathlib import Path

from integrations.razorpay_adapter import (
    RazorpayAdapter,
    RazorpayOrder,
    RazorpayPayment,
    RazorpayRefund,
)

FIXTURES = Path(__file__).resolve().parents[2] / "integrations" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_order_to_scoring_input_maps_paise_to_inr():
    payload = _load("razorpay_order.json")["payload"]
    inp = RazorpayAdapter.order_to_scoring_input(
        order=payload["order"]["entity"], payment=payload["payment"]["entity"]
    )
    assert inp.order_id == "order_MYNT2026_001"
    assert inp.amount == 5500  # 550000 paise → ₹5500
    assert inp.category == "fashion"
    assert inp.merchant_id == "M_FASHION_001"
    assert inp.user_id == "cust_serialsam"
    assert inp.cod_flag is True  # method cod + notes.cod=true
    assert inp.payment_method == "COD"
    assert inp.device_fingerprint == "DEV_SERIAL_014"
    assert inp.timestamp.hour >= 0


def test_order_to_scoring_input_derives_category_from_receipt():
    order = RazorpayOrder(
        id="order_1",
        amount=250000,
        receipt="ELEC-ORD-0001",
        notes={},
        created_at=1784736000,
    )
    inp = RazorpayAdapter.order_to_scoring_input(order)
    assert inp.category == "electronics"
    assert inp.payment_method == "UPI"  # no method → default
    assert inp.cod_flag is False


def test_order_to_scoring_input_anon_user_default():
    order = RazorpayOrder(id="order_2", amount=50000, notes=None, created_at=1784736000)
    inp = RazorpayAdapter.order_to_scoring_input(order)
    assert inp.user_id.startswith("anon_")


def test_refund_to_label_normalises_reason():
    payload = _load("razorpay_refund.json")["payload"]
    label = RazorpayAdapter.refund_to_label(
        payment=payload["payment"]["entity"],
        refund=payload["refund"]["entity"],
        order=payload["order"]["entity"],
    )
    assert label["order_id"] == "order_MYNT2026_002"
    assert label["user_id"] == "cust_returnsal"
    assert label["returned"] is True
    assert label["refund_amount"] == 3500
    assert label["return_reason"] == "CHANGED_MIND"  # "changed my mind" → enum
    assert label["label"] == "high_risk_return"


def test_scoring_input_payload_roundtrip():
    payload = _load("razorpay_order.json")["payload"]
    inp = RazorpayAdapter.order_to_scoring_input(
        order=payload["order"]["entity"], payment=payload["payment"]["entity"]
    )
    wire = RazorpayAdapter.scoring_input_to_payload(inp)
    assert wire["amount"] == "5500"
    assert wire["payment_method"] == "COD"
    assert wire["cod_flag"] is True


def test_refund_label_without_order_falls_back_to_payment_notes():
    payment = RazorpayPayment(id="pay_1", order_id="order_1", notes={"customer_id": "cust_x"})
    refund = RazorpayRefund(id="ref_1", payment_id="pay_1", amount=10000)
    label = RazorpayAdapter.refund_to_label(payment, refund)
    assert label["user_id"] == "cust_x"
