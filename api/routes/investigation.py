"""Return-risk investigation views (read-only, audit-backed).

The dashboard's anomaly ledger, notifications and transaction pages list scored
orders. Those scores live in the tamper-evident audit chain
(``RETURN_RISK_SCORED`` entries), so this route renders them directly from the
audit log instead of a second write path — no duplicated state to drift.

- ``GET /v1/investigations``            -> paginated list of scored orders
- ``GET /v1/investigation/{order_id}``  -> detail view for one scored order
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import verify_api_key
from api.rbac import require_permission
from api.schemas import InvestigationListResponse, InvestigationReportResponse
from store.audit_log import AuditLogReader

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

TIER_TO_ACTION = {"HIGH": "BLOCK", "MEDIUM": "REVIEW", "LOW": "ALLOW"}


def _to_report(entry: dict) -> dict:
    payload = entry.get("payload", {})
    score = payload.get("score", 0.0)
    tier = payload.get("tier", "LOW")
    order_id = payload.get("order_id", entry.get("actor", "unknown"))
    return {
        "txn_id": order_id,
        "narrative": (
            f"Return-risk score {score:.3f} ({tier} tier) for order "
            f"{order_id} — flagged for {TIER_TO_ACTION.get(tier, 'REVIEW')}."
        ),
        "fraud_type": "RETURN_RISK",
        "confidence": tier,
        "recommended_action": TIER_TO_ACTION.get(tier, "REVIEW"),
        "key_evidence": [
            f"return_risk_score={score:.3f}",
            f"risk_tier={tier}",
        ],
        "reasoning": "Derived from the return-risk scorer at checkout time.",
        "generated_at": entry.get("timestamp", ""),
    }


def _scored_entries() -> list[dict]:
    entries = AuditLogReader().get_entries(event_type="RETURN_RISK_SCORED")
    reports = []
    for entry in entries:
        try:
            reports.append(_to_report(entry))
        except Exception as e:  # nosec B110 - skip malformed entries
            logger.warning("investigation_skipped_malformed: %s", e)
    reports.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return reports


@router.get("/investigation/{order_id}", response_model=InvestigationReportResponse)
async def get_investigation(
    order_id: str,
    _=Depends(require_permission("return_risk", "read")),
):
    """Detail view for one scored order, from the audit chain."""
    for report in _scored_entries():
        if report["txn_id"] == order_id:
            return InvestigationReportResponse(**report)
    raise HTTPException(status_code=404, detail="Investigation not found")


@router.get("/investigations", response_model=InvestigationListResponse)
async def list_investigations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    confidence: str | None = Query(None),
    _=Depends(require_permission("return_risk", "read")),
):
    """Paginated ledger of scored orders (return-risk surface)."""
    reports = _scored_entries()
    if confidence:
        reports = [r for r in reports if r.get("confidence", "").upper() == confidence.upper()]
    total = len(reports)
    offset = (page - 1) * page_size
    return InvestigationListResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=[json.loads(json.dumps(r)) for r in reports[offset : offset + page_size]],
    )