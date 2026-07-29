import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/compliance", tags=["compliance"])


class ComplianceStatusResponse(BaseModel):
    overall_score: int
    frameworks: dict[str, Any]
    open_findings: int
    last_audit_date: str


class ReportJobResponse(BaseModel):
    report_id: str
    status: str
    message: str


class ComplianceReportResponse(BaseModel):
    report_id: str
    framework: str
    report_type: str
    score: int
    findings: list[dict]
    generated_at: str


def _safe_compliance_check(module_path: str, class_name: str) -> dict:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        result = cls().run()
        return {"score": getattr(result, "score", 0), "passed": getattr(result, "passed", False),
                "findings": getattr(result, "findings", []), "generated_at": getattr(result, "generated_at", "")}
    except Exception as e:
        logger.warning(f"Compliance check {module_path}.{class_name} unavailable: {e}")
        return {"score": 0, "passed": False, "findings": [f"Checker not available: {e}"], "generated_at": ""}


@router.get("/status")
async def get_compliance_status():
    pci = _safe_compliance_check("compliance.pci_dss", "PCIDSSComplianceChecker")
    rbi = _safe_compliance_check("compliance.rbi_localization", "RBILocalizationChecker")
    eu = _safe_compliance_check("compliance.eu_ai_act", "EUAiActComplianceChecker")

    return ComplianceStatusResponse(
        overall_score=int((pci["score"] + rbi["score"] + eu["score"]) / 3),
        frameworks={
            "PCI-DSS": {"score": pci["score"], "passed": pci["passed"], "findings": len(pci["findings"])},
            "RBI": {"score": rbi["score"], "passed": rbi["passed"], "findings": len(rbi["findings"])},
            "EU_AI_ACT": {"score": eu["score"], "passed": eu["passed"], "findings": len(eu["findings"])},
        },
        open_findings=len(pci["findings"]) + len(rbi["findings"]) + len(eu["findings"]),
        last_audit_date=pci["generated_at"] or rbi["generated_at"] or eu["generated_at"],
    )


@router.post("/report", response_model=ReportJobResponse)
async def generate_compliance_report():
    from compliance.audit_generator import ComplianceAuditGenerator

    try:
        generator = ComplianceAuditGenerator()
        report = generator.generate_quarterly_report(generated_by="api")
        return ReportJobResponse(
            report_id=report.report_id,
            status="completed",
            message=f"Quarterly compliance report generated: {report.report_id}",
        )
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.post("/report/{framework}", response_model=ReportJobResponse)
async def generate_framework_report(framework: str):
    from compliance.audit_generator import ComplianceAuditGenerator

    valid_frameworks = {"PCI-DSS", "RBI", "EU_AI_ACT"}
    if framework.upper() not in {f.upper() for f in valid_frameworks}:
        raise HTTPException(status_code=400, detail=f"Unknown framework: {framework}. Use: {valid_frameworks}")

    try:
        generator = ComplianceAuditGenerator()
        report = generator.generate_framework_report(framework.upper())
        return ReportJobResponse(
            report_id=report.report_id,
            status="completed",
            message=f"{framework} compliance report generated",
        )
    except Exception as e:
        logger.error(f"Framework report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{report_id}", response_model=ComplianceReportResponse)
async def get_compliance_report(report_id: str):
    import glob

    patterns = [
        f"compliance/reports/{report_id}/compliance_report.json",
        f"compliance/reports/*{report_id}*.json",
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            import json
            with open(matches[0]) as f:
                data = json.load(f)
            return ComplianceReportResponse(
                report_id=data.get("report_id", report_id),
                framework=data.get("framework", "ALL"),
                report_type=data.get("report_type", "ON_DEMAND"),
                score=data.get("score", 0),
                findings=data.get("findings", []),
                generated_at=data.get("generated_at", ""),
            )

    raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")


@router.get("/evidence")
async def list_evidence():
    from compliance.evidence_collector import EvidenceCollector

    collector = EvidenceCollector()
    return {"archives": collector.list_archives()}


@router.post("/evidence/collect")
async def collect_evidence():
    from compliance.evidence_collector import EvidenceCollector

    try:
        collector = EvidenceCollector()
        archive_path = collector.collect_evidence()
        return {"status": "completed", "archive": archive_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SanctionsCheckRequest(BaseModel):
    user_id: str
    user_name: str = ""


class SanctionsCheckResponse(BaseModel):
    status: str
    matched: bool
    sanctions_list: str
    risk_level: str
    checked_at: str


class KYCStatusResponse(BaseModel):
    status: str
    kyc_tier: str
    tier_description: str
    documents_verified: list[str]
    checked_at: str


class AMLCheckRequest(BaseModel):
    user_id: str
    user_country: str = "IN"
    txn_country: str = "IN"
    amount: float = 0.0


class AMLCheckResponse(BaseModel):
    velocity_status: dict[str, Any]
    structuring_status: dict[str, Any]
    cross_border_status: dict[str, Any]
    overall_risk_score: float
    checked_at: str


@router.get("/check/{user_id}")
async def compliance_check_user(user_id: str):
    try:
        from compliance.sanctions import SanctionsChecker, KYCVerifier

        checker = SanctionsChecker()
        sanctions = checker.check_entity(user_id)

        kyc = KYCVerifier()
        kyc_status = kyc.verify_user(user_id)

        return {
            "user_id": user_id,
            "sanctions": sanctions,
            "kyc": kyc_status,
            "checked_at": sanctions["checked_at"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compliance check failed for {user_id}: {e}")
        return {
            "user_id": user_id,
            "status": "unavailable",
            "error": str(e),
            "checked_at": "",
        }


@router.post("/sanctions/check", response_model=SanctionsCheckResponse)
async def check_sanctions(req: SanctionsCheckRequest):
    try:
        from compliance.sanctions import SanctionsChecker

        checker = SanctionsChecker()
        result = checker.check_entity(req.user_id)

        if not result["matched"] and req.user_name:
            name_result = checker.check_entity_name(req.user_name)
            if name_result["matched"]:
                result = name_result

        return SanctionsCheckResponse(**result)
    except Exception as e:
        return SanctionsCheckResponse(
            status="unavailable",
            matched=False,
            sanctions_list="NONE",
            risk_level="none",
            checked_at="",
        )


@router.get("/kyc/{user_id}", response_model=KYCStatusResponse)
async def get_kyc_status(user_id: str):
    try:
        from compliance.sanctions import KYCVerifier

        kyc = KYCVerifier()
        result = kyc.verify_user(user_id)
        return KYCStatusResponse(**result)
    except Exception as e:
        return KYCStatusResponse(
            status="unavailable",
            kyc_tier="KYC0",
            tier_description="KYC service unavailable",
            documents_verified=[],
            checked_at="",
        )


@router.post("/aml/check", response_model=AMLCheckResponse)
async def check_aml(req: AMLCheckRequest):
    try:
        from compliance.sanctions import AMLComplianceEngine

        engine = AMLComplianceEngine()
        velocity = engine.check_velocity({"txn_count_24h": 0, "amount_sum_24h": 0, "txn_count_1h": 0})
        structuring = engine.check_structuring([])
        cross_border = engine.check_cross_border(req.user_country, req.txn_country, req.amount)

        overall = velocity.get("risk_score", 0.0) * 0.4 + structuring.get("risk_score", 0.0) * 0.3 + cross_border.get("risk_score", 0.0) * 0.3

        return AMLCheckResponse(
            velocity_status=velocity,
            structuring_status=structuring,
            cross_border_status=cross_border,
            overall_risk_score=round(min(1.0, overall), 4),
            checked_at=velocity["checked_at"],
        )
    except Exception as e:
        logger.error(f"AML check failed: {e}")
        return AMLCheckResponse(
            velocity_status={"status": "unavailable", "flags": [], "risk_score": 0.0, "checked_at": ""},
            structuring_status={"status": "unavailable", "detected": False, "suspicious_count": 0, "threshold": 0, "rule": "", "checked_at": ""},
            cross_border_status={"status": "unavailable", "cross_border": False, "high_risk_country": False, "flags": [], "risk_score": 0.0, "checked_at": ""},
            overall_risk_score=0.0,
            checked_at="",
        )
