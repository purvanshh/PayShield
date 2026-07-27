import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_redis, verify_api_key
from api.rbac import require_permission
from api.schemas import InvestigationReportResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/investigation/{txn_id}", response_model=InvestigationReportResponse)
async def get_investigation(
    txn_id: str,
    redis=Depends(get_redis),
):
    key = f"investigation:{txn_id}"
    raw = redis.get(key)
    if raw is None:
        pending_key = f"investigation_pending:{txn_id}"
        if redis.get(pending_key):
            raise HTTPException(
                status_code=202,
                detail={"status": "pending", "retry_after": 5, "txn_id": txn_id},
            )
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Invalid investigation data")
    return InvestigationReportResponse(
        txn_id=data.get("txn_id", txn_id),
        narrative=data.get("narrative", ""),
        fraud_type=data.get("fraud_type", "OTHER"),
        confidence=data.get("confidence", "LOW"),
        recommended_action=data.get("recommended_action", "ALLOW"),
        key_evidence=data.get("key_evidence", []),
        reasoning=data.get("reasoning", ""),
        generated_at=datetime.fromisoformat(data["generated_at"]) if isinstance(data.get("generated_at"), str) else datetime.utcnow(),
    )


@router.get("/investigations")
async def list_investigations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    fraud_type: str | None = Query(None),
    confidence: str | None = Query(None),
    redis=Depends(get_redis),
    _=Depends(require_permission("investigation", "read")),
):
    pattern = "investigation:*"
    keys = []
    try:
        keys = redis.keys(pattern) or []
    except Exception:
        pass
    all_reports = []
    for k in keys:
        raw = redis.get(k)
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                all_reports.append(data)
            except Exception:
                continue
    if fraud_type:
        all_reports = [r for r in all_reports if r.get("fraud_type", "").upper() == fraud_type.upper()]
    if confidence:
        all_reports = [r for r in all_reports if r.get("confidence", "").upper() == confidence.upper()]
    all_reports.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    total = len(all_reports)
    offset = (page - 1) * page_size
    page_items = all_reports[offset:offset + page_size]
    return {"total": total, "page": page, "page_size": page_size, "results": page_items}
