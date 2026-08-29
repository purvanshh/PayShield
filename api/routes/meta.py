"""Read-only meta endpoints serving committed measured artifacts.

The dashboard never re-derives its own numbers — it renders what the backend
actually measured and committed under ``models/``:

- ``/v1/meta/return-risk/benchmark`` -> ``models/return_risk_benchmark_results.json``
- ``/v1/meta/return-risk/cost``       -> ``models/cost_model_results.json``
  (regenerated on demand from ``docs/cost_model/calculator.py`` if missing)
- ``/v1/meta/experiments``            -> ``models/ab_test_result.json``
- ``/v1/meta/track2-compliance``      -> Track 2 requirement -> implementation
  -> evidence map (mirrors ``docs/TRACK2_COMPLIANCE.md``)

Authentication follows the standard API-key/Bearer path; these are read-only
introspection endpoints with no side effects besides cache generation.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

ROOT = Path(__file__).resolve().parents[2]
_BENCHMARK = ROOT / "models" / "return_risk_benchmark_results.json"
_COST = ROOT / "models" / "cost_model_results.json"
_AB = ROOT / "models" / "ab_test_result.json"

# Track 2 compliance map — single source for the dashboard page. Kept in
# lockstep with docs/TRACK2_COMPLIANCE.md. ``status`` is "done" (implemented +
# verified) or "planned" (a later phase in the execution plan, not yet built).
TRACK2_REQUIREMENTS = [
    {
        "name": "Return-Risk Scorer (pre-ship tier)",
        "status": "done",
        "implementation": "return_risk/scorer.py (XGBoost primary + hand-weighted fallback)",
        "evidence": "tests/unit/return_risk/test_scorer.py · verify_live_stack.py",
    },
    {
        "name": "Redis Feature Engine (user history, not placeholders)",
        "status": "done",
        "implementation": "return_risk/feature_engine.py",
        "evidence": "tests/unit/return_risk/test_feature_engine.py",
    },
    {
        "name": "Config-Driven Rules Engine",
        "status": "done",
        "implementation": "return_risk/rules_engine.py · configs/return_risk_rules.yaml",
        "evidence": "tests/unit/return_risk/test_rules_engine.py",
    },
    {
        "name": "Fraud-Spike Detector (velocity / geo / device)",
        "status": "done",
        "implementation": "engine/statistical_filter.py over Redis velocity:*",
        "evidence": "tests/unit/test_statistical_filter.py · verify_live_stack.py (burst→BLOCK)",
    },
    {
        "name": "Graph / Network Intelligence (L2)",
        "status": "done",
        "implementation": "engine/graph_loader.py · engine/graph_feature_engine.py · engine/ensemble.py",
        "evidence": "tests/integration/test_graph_integration.py · tests/unit/test_ensemble.py",
    },
    {
        "name": "Chargeback Evidence Responder",
        "status": "done",
        "implementation": "chargeback/evidence_collector.py · chargeback/rebuttal_builder.py",
        "evidence": "tests/unit/chargeback/test_rebuttal_builder.py · test_evidence_collector.py",
    },
    {
        "name": "Signed Razorpay Webhooks (HMAC, 400 on bad signature)",
        "status": "done",
        "implementation": "integrations/razorpay_webhook_handler.py · chargeback/signatures.py",
        "evidence": "tests/integration/test_razorpay_webhooks.py · verify_live_stack.py",
    },
    {
        "name": "Honest Metrics incl. FP/FN cost (₹200 / ₹3,180)",
        "status": "done",
        "implementation": "docs/cost_model/calculator.py (no hardcoded fallback)",
        "evidence": "tests/unit/test_cost_model.py · docs/COST_MODEL.md",
    },
    {
        "name": "Defense-Only Posture (FLAG_FOR_REVIEW / REQUIRE_PREPAID)",
        "status": "done",
        "implementation": "return_risk/scorer.py tiers + recommendations",
        "evidence": "verify_live_stack.py (honest LOW · serial HIGH) · docs/DESIGN_DECISIONS.md",
    },
    {
        "name": "Tamper-Evident, PII-Masked Audit Chain",
        "status": "done",
        "implementation": "store/audit_log.py (hash-chained JSONL)",
        "evidence": "tests/unit/chargeback/test_audit_log_reader.py · test_security_hardening.py",
    },
    {
        "name": "Human-in-the-Loop Chargeback Submit (chargeback:admin)",
        "status": "done",
        "implementation": "api/routes/chargeback.py · configs/rbac.yaml",
        "evidence": "tests/integration/test_chargeback_api.py (RBAC)",
    },
    {
        "name": "Drift Monitoring (PSI 43.4 → 3.86)",
        "status": "done",
        "implementation": "api/routes/admin.py (/admin/drift/return-risk)",
        "evidence": "tests/unit/test_drift.py · test_drift_report.py",
    },
    {
        "name": "Reproducible Evidence (10/10 hermetic)",
        "status": "done",
        "implementation": "scripts/run_all_scenarios.py --full-verify",
        "evidence": "reports/full_verify_output.txt",
    },
    {
        "name": "Live-Stack Verification (11/11)",
        "status": "done",
        "implementation": "scripts/seed_demo_data.py · scripts/verify_live_stack.py",
        "evidence": "live Docker run · docs/CALIBRATION_GAP.md",
    },
    {
        "name": "Feature-Waterfall Explainability (XAI)",
        "status": "done",
        "implementation": "POST /v1/return/explain (per-feature gain importance x value)",
        "evidence": "tests/integration/test_return_risk_api.py::TestReturnRiskExplain",
    },
    {
        "name": "Abuse-Ring Sentinel (shared address-hash velocity)",
        "status": "done",
        "implementation": "return_risk/feature_engine.py address tracking + configs/return_risk_rules.yaml R-RULE-09",
        "evidence": "tests/unit/return_risk/test_scorer.py::test_abuse_ring_sentinel_overrides_score_to_high",
    },
    {
        "name": "Temporal-Integrity Check (no look-ahead bias)",
        "status": "done",
        "implementation": "scripts/verify_temporal_integrity.py (wired as --full-verify check 11)",
        "evidence": "scripts/verify_temporal_integrity.py · reports/full_verify_output.txt",
    },
    {
        "name": "Guided Demo Mode (10-minute tour)",
        "status": "planned",
        "implementation": "dashboard DemoTour page · /v1/meta/demo/guide",
        "evidence": "execution plan Phase 4",
    },
    {
        "name": "Human-Review Queue UI",
        "status": "planned",
        "implementation": "dashboard /review-queue · /v1/meta/review-queue",
        "evidence": "execution plan Phase 5 (optional)",
    },
    {
        "name": "Calibration Simulator (drift sliders)",
        "status": "planned",
        "implementation": "POST /v1/return/simulate · dashboard /simulator",
        "evidence": "execution plan Phase 6 (optional)",
    },
]

TRACK2_OVERALL = (
    "Core Track 2 surfaces implemented and verified — return-risk scoring, "
    "fraud-spike detection, graph intelligence, chargeback response, Razorpay "
    "webhooks, honest FP/FN cost metrics, defense-only posture, audit chain, "
    "drift monitoring, reproducible evidence (10/10 hermetic, 11/11 live), "
    "feature-waterfall explainability, abuse-ring sentinel, and a temporal-"
    "integrity check. Three planned enhancements remain: guided demo, review "
    "queue, calibration simulator."
)


def _load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/v1/meta/track2-compliance")
async def track2_compliance(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """Track 2 requirement -> implementation -> evidence map.

    Mirrors docs/TRACK2_COMPLIANCE.md so the dashboard and the docs never
    drift apart. ``status`` distinguishes verified ("done") from later-plan
    ("planned") items — nothing is marked complete before it exists.
    """
    return {"requirements": TRACK2_REQUIREMENTS, "overall": TRACK2_OVERALL}


@router.get("/v1/meta/return-risk/benchmark")
async def return_risk_benchmark(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The committed calibrated benchmark (PR-AUC / ROC / gate metrics)."""
    data = _load(_BENCHMARK)
    if data is None:
        raise HTTPException(status_code=404, detail="benchmark results not found")
    return data


@router.get("/v1/meta/return-risk/cost")
async def return_risk_cost(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The cost model (scenarios + sensitivity + operating point).

    Serves the committed ``cost_model_results.json``; if absent, regenerates it
    from the authoritative calculator and caches it under ``models/``.
    """
    data = _load(_COST)
    if data is None:
        try:
            import asyncio

            await asyncio.to_thread(
                subprocess.check_call,
                [sys.executable, "docs/cost_model/calculator.py", "--json"],
                cwd=ROOT,
            )
            logger.info("regenerated %s", _COST.name)
        except Exception as exc:  # nosec B110 - cache regeneration is best-effort
            logger.warning("cost model regeneration failed: %s", exc)
        data = _load(_COST)
    if data is None:
        raise HTTPException(status_code=503, detail="cost model results unavailable")
    return data


@router.get("/v1/meta/experiments")
async def experiments(
    _=Depends(verify_api_key),  # noqa: B008 - FastAPI dependency-injection idiom
):
    """The committed champion/challenger A/B verdict (real simulation output)."""
    data = _load(_AB)
    if data is None:
        raise HTTPException(status_code=404, detail="a/b test result not found")
    return data
