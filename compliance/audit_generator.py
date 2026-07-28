import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ComplianceReport:
    report_id: str
    framework: str
    report_type: str
    findings: list[dict]
    score: int
    generated_at: str = ""
    generated_by: str = "system"

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class ComplianceAuditGenerator:
    def __init__(self, db_session=None):
        self._db = db_session

    def generate_quarterly_report(self, generated_by: str = "system") -> ComplianceReport:
        from compliance.pci_dss import PCIDSSComplianceChecker
        from compliance.rbi_localization import RBILocalizationChecker
        from compliance.eu_ai_act import EUAiActComplianceChecker

        logger.info("Generating quarterly compliance report...")

        pci_result = PCIDSSComplianceChecker().run()
        rbi_result = RBILocalizationChecker().run()
        eu_result = EUAiActComplianceChecker().run()

        all_findings = (
            pci_result.findings + rbi_result.findings + eu_result.findings
        )

        overall_score = int((pci_result.score + rbi_result.score + eu_result.score) / 3)
        report_id = f"Q{((datetime.now().month - 1) // 3) + 1}-{datetime.now().year}"

        report = ComplianceReport(
            report_id=report_id,
            framework="ALL",
            report_type="QUARTERLY",
            findings=[f.to_dict() for f in all_findings],
            score=overall_score,
            generated_by=generated_by,
        )

        self._save_report(report)

        return report

    def _save_report(self, report: ComplianceReport):
        quarter = report.report_id
        dir_path = f"compliance/reports/{quarter}"
        os.makedirs(dir_path, exist_ok=True)

        json_path = f"{dir_path}/compliance_report.json"
        with open(json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        md_lines = [
            f"# Compliance Report — {report.report_id}",
            "",
            f"**Generated:** {report.generated_at}",
            f"**Overall Score:** {report.score}/100",
            f"**Total Findings:** {len(report.findings)}",
            "",
            "## Summary",
            "",
            f"| Framework | Score | Findings |",
            f"|-----------|-------|----------|",
        ]

        for framework in ["PCI-DSS", "RBI", "EU_AI_ACT"]:
            fw_findings = [f for f in report.findings if f.get("control_id", "").startswith(
                {"PCI-DSS": "3", "RBI": "D", "EU_AI_ACT": "R"}.get(framework, "")
            )]
            md_lines.append(f"| {framework} | TBD | {len(fw_findings)} |")

        md_lines.extend([
            "",
            "## Detailed Findings",
            "",
        ])

        for f in report.findings:
            md_lines.extend([
                f"### {f.get('control_id', 'N/A')}: {f.get('description', 'N/A')}",
                f"- **Severity:** {f.get('severity', 'N/A')}",
                f"- **Remediation:** {f.get('remediation', 'N/A')}",
                f"- **Status:** {f.get('status', 'open')}",
                "",
            ])

        md_path = f"{dir_path}/compliance_report.md"
        with open(md_path, "w") as f:
            f.write("\n".join(md_lines))

        logger.info(f"Quarterly report saved to {dir_path}/")

    def generate_framework_report(self, framework: str) -> ComplianceReport:
        from compliance.pci_dss import PCIDSSComplianceChecker
        from compliance.rbi_localization import RBILocalizationChecker
        from compliance.eu_ai_act import EUAiActComplianceChecker

        checkers = {
            "PCI-DSS": PCIDSSComplianceChecker,
            "RBI": RBILocalizationChecker,
            "EU_AI_ACT": EUAiActComplianceChecker,
        }

        checker_cls = checkers.get(framework)
        if not checker_cls:
            raise ValueError(f"Unknown framework: {framework}")

        result = checker_cls().run()
        report_id = f"{framework.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        report = ComplianceReport(
            report_id=report_id,
            framework=framework,
            report_type="ON_DEMAND",
            findings=[f.to_dict() for f in result.findings],
            score=result.score,
            generated_by="system",
        )

        self._save_report(report)
        return report
