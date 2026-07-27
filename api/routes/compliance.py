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
