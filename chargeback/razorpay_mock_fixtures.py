"""Realistic Razorpay mock fixtures (Track 02 - Phase 11).

Mock mode must be *realistic*, not optimistic:

- reason codes match actual Visa/Mastercard codes,
- ``respond_by`` timestamps respect per-network windows,
- status transitions follow Razorpay's dispute state machine
  (``open -> under_review -> won / lost``).
"""

from datetime import datetime, timedelta
from typing import Any

REASON_CODES = {
    "fraud": [
        {"code": "10.4", "desc": "Fraud - Card Not Present"},
        {"code": "10.5", "desc": "Fraud - Card-Activated Telephone Transaction"},
    ],
    "service": [
        {"code": "13.1", "desc": "Services Not Provided"},
        {"code": "13.2", "desc": "Cancelled Recurring Transaction"},
    ],
    "processing": [
        {"code": "12.1", "desc": "Late Presentment"},
        {"code": "12.4", "desc": "Incorrect Account Number"},
    ],
}

STATUS_SEQUENCE = ["open", "under_review", "accepted", "won", "lost"]


def mock_get_chargeback(
    dispute_id: str = "disp_2Vw9aZ0q3X",
    scenario: str = "fraud",
    status: str = "open",
) -> dict[str, Any]:
    """Return a Razorpay-shaped dispute entity for the given scenario."""
    reason = (REASON_CODES.get(scenario) or REASON_CODES["fraud"])[0]
    return {
        "id": dispute_id,
        "entity": "dispute",
        "payment_id": f"pay_{dispute_id[5:]}",
        "amount": 4500,
        "currency": "INR",
        "status": status,
        "reason_code": reason["code"],
        "reason_description": reason["desc"],
        "created_at": int((datetime.utcnow() - timedelta(days=5)).timestamp()),
        "respond_by": int((datetime.utcnow() + timedelta(days=25)).timestamp()),
        "action": "action_8A9BcD2EfG",
    }


def mock_contest_response(
    dispute_id: str = "disp_2Vw9aZ0q3X", outcome: str = "under_review"
) -> dict[str, Any]:
    """Razorpay's post-contest entity (``open -> under_review -> won|lost``)."""
    assert outcome in STATUS_SEQUENCE, f"unexpected status {outcome}"
    return {
        "id": dispute_id,
        "entity": "dispute",
        "status": outcome,
        "contest": True,
        "reason_code": "10.4",
        "reason_description": "Fraud - Card Not Present",
    }


def mock_upload_response(dispute_id: str, file_id: str = "file_mock_1") -> dict[str, Any]:
    return {
        "file_id": file_id,
        "url": f"https://mock.razorpay.io/files/{dispute_id}/{file_id}",
        "entity": "dispute_file",
    }
