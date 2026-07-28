import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ComplianceFinding:
    control_id: str
    severity: str
    description: str
    remediation: str
    status: str = "open"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplianceResult:
    framework: str
    score: int
    findings: list[ComplianceFinding]
    passed: bool
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "score": self.score,
            "findings": [f.to_dict() for f in self.findings],
            "passed": self.passed,
            "generated_at": self.generated_at,
        }


PCI_CONTROLS = {
    "3.1": {"description": "Protect stored payment identifiers — no plaintext PAN/payment data"},
    "3.4": {"description": "Render PAN unreadable anywhere stored (AES-256 encryption)"},
    "3.5": {"description": "Document and implement key management procedures"},
    "8.1": {"description": "RBAC enforced on all admin endpoints"},
    "8.3": {"description": "MFA enabled for all admin accounts"},
    "8.5": {"description": "Password policy: 12+ chars, complexity, 90-day rotation"},
    "10.1": {"description": "Immutable audit logs for all access and decisions"},
    "10.2": {"description": "Audit log retention >= 1 year"},
    "10.3": {"description": "Log contains user ID, event type, timestamp, success/failure"},
    "10.7": {"description": "Audit log review process in place"},
}


class PCIDSSComplianceChecker:
    def __init__(self, db_session=None):
        self._db = db_session
        self._findings: list[ComplianceFinding] = []

    def run(self) -> ComplianceResult:
        logger.info("Running PCI-DSS compliance check...")
        self._findings = []

        self._check_requirement_3()
        self._check_requirement_8()
        self._check_requirement_10()

        passed = len([f for f in self._findings if f.severity == "high"]) == 0
        total_controls = len(PCI_CONTROLS)
        passed_controls = total_controls - len(self._findings)
        score = int((passed_controls / max(total_controls, 1)) * 100)

        return ComplianceResult(
            framework="PCI-DSS",
            score=score,
            findings=self._findings,
            passed=passed,
        )

    def _check_requirement_3(self):
        log_dir = "logs"
        plaintext_patterns = [
            re.compile(r"\b\d{16}\b"),
            re.compile(r"pan[\"']?\s*[:=]\s*[\"']?\d{10,19}"),
        ]

        if os.path.isdir(log_dir):
            for fname in os.listdir(log_dir):
                if fname.endswith(".log"):
                    fpath = os.path.join(log_dir, fname)
                    try:
                        with open(fpath) as f:
                            content = f.read()
                            for pattern in plaintext_patterns:
                                if pattern.search(content):
                                    self._findings.append(ComplianceFinding(
                                        control_id="3.1",
                                        severity="high",
                                        description=f"Potential plaintext payment data in {fname}",
                                        remediation="Ensure all payment identifiers are hashed (SHA-256 + salt) before logging",
                                        evidence={"file": fname, "pattern": pattern.pattern},
                                    ))
                                    break
                    except Exception:
                        pass

        env_encryption_key = os.environ.get("ENCRYPTION_KEY", "")
        if not env_encryption_key:
            self._findings.append(ComplianceFinding(
                control_id="3.4",
                severity="high",
                description="ENCRYPTION_KEY not set — data at risk of unencrypted storage",
                remediation="Set AES-256 ENCRYPTION_KEY environment variable",
            ))

    def _check_requirement_8(self):
        rbac_config = os.environ.get("ENFORCE_RBAC", "false")
        if rbac_config.lower() != "true":
            self._findings.append(ComplianceFinding(
                control_id="8.1",
                severity="high",
                description="RBAC not enforced — admin endpoints may be accessible without proper authorization",
                remediation="Enable RBAC enforcement via ENFORCE_RBAC=true",
            ))

        if not os.environ.get("MFA_ENABLED"):
            self._findings.append(ComplianceFinding(
                control_id="8.3",
                severity="medium",
                description="MFA not detected for admin accounts",
                remediation="Enable MFA (TOTP) for all admin accounts",
            ))

    def _check_requirement_10(self):
        audit_log_path = "store/audit_logs"
        if not os.path.isdir(audit_log_path):
            self._findings.append(ComplianceFinding(
                control_id="10.1",
                severity="high",
                description="Immutable audit log directory not found",
                remediation="Ensure decision audit logs are written to immutable storage",
            ))
        else:
            log_count = len(os.listdir(audit_log_path))
            if log_count == 0:
                self._findings.append(ComplianceFinding(
                    control_id="10.2",
                    severity="medium",
                    description="Audit log directory exists but contains no logs",
                    remediation="Verify audit logging is operational",
                ))

    def generate_report(self) -> dict:
        result = self.run()
        report_path = f"compliance/reports/pci_dss_{datetime.now().strftime('%Y%m%d')}.json"
        os.makedirs("compliance/reports", exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"PCI-DSS report saved to {report_path}")
        return result.to_dict()
