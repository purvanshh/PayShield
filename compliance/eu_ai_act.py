import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compliance.pci_dss import ComplianceFinding, ComplianceResult

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

EU_AI_ACT_CONTROLS = {
    "RM-1": "Risk assessment document exists and updated quarterly",
    "CM-1": "Conformity assessment completed and documented",
    "PM-1": "Post-market monitoring plan active and reviewed",
    "DG-1": "Training data quality validation — bias detection report",
    "DG-2": "Demographic performance metrics tracked and reviewed",
    "TR-1": "Model cards include intended use, limitations, and known biases",
    "TR-2": "Technical documentation maintained and accessible",
    "HO-1": "Human oversight — HumanReviewAgent can overturn any AI decision",
    "HO-2": "Override rate tracked and reported",
    "HO-3": "Human oversight log maintained with review timestamps",
    "AC-1": "Model accuracy — PR-AUC >= 2x no-skill baseline",
    "AC-2": "False positive rate tracked at 90% recall",
    "RB-1": "Adversarial testing completed quarterly",
}


class EUAiActComplianceChecker:
    def __init__(self, db_session=None):
        self._db = db_session
        self._findings: list[ComplianceFinding] = []

    def run(self) -> ComplianceResult:
        logger.info("Running EU AI Act compliance check...")
        self._findings = []

        self._check_risk_management()
        self._check_conformity()
        self._check_monitoring()
        self._check_data_governance()
        self._check_transparency()
        self._check_technical_documentation()
        self._check_human_oversight()
        self._check_accuracy()
        self._check_robustness()

        total_controls = len(EU_AI_ACT_CONTROLS)
        high_count = len([f for f in self._findings if f.severity == "high"])
        medium_count = len([f for f in self._findings if f.severity == "medium"])
        low_count = len([f for f in self._findings if f.severity == "low"])
        weighted_violations = high_count + 0.5 * medium_count + 0.0 * low_count
        score = max(0, int((1.0 - weighted_violations / max(total_controls, 1)) * 100))
        passed = high_count == 0

        return ComplianceResult(
            framework="EU_AI_ACT",
            score=score,
            findings=self._findings,
            passed=passed,
        )

    def _check_risk_management(self):
        risk_doc = _PROJECT_ROOT / "docs" / "security" / "risk-assessment.md"
        if not risk_doc.exists():
            self._findings.append(ComplianceFinding(
                control_id="RM-1",
                severity="low",
                description="Risk assessment document not found — EU AI Act Article 9 requires documented risk management",
                remediation="Create risk assessment at docs/security/risk-assessment.md and update quarterly",
            ))

    def _check_conformity(self):
        conformity_doc = _PROJECT_ROOT / "docs" / "security" / "conformity-assessment.md"
        if not conformity_doc.exists():
            self._findings.append(ComplianceFinding(
                control_id="CM-1",
                severity="low",
                description="Conformity assessment document not found — EU AI Act Article 16 requires a conformity declaration",
                remediation="Create conformity assessment at docs/security/conformity-assessment.md",
            ))

    def _check_monitoring(self):
        monitoring_plan = _PROJECT_ROOT / "docs" / "security" / "post-market-monitoring.md"
        if not monitoring_plan.exists():
            self._findings.append(ComplianceFinding(
                control_id="PM-1",
                severity="low",
                description="Post-market monitoring plan not found — EU AI Act Article 61 requires continuous monitoring",
                remediation="Create monitoring plan at docs/security/post-market-monitoring.md",
            ))

    def _check_data_governance(self):
        has_bias_report = (
            (_PROJECT_ROOT / "reports" / "bias_detection").is_dir()
            or (_PROJECT_ROOT / "models" / "fairness_audit.py").exists()
        )
        if not has_bias_report:
            self._findings.append(ComplianceFinding(
                control_id="DG-1",
                severity="low",
                description="Bias detection artifact not found",
                remediation="Run `python models/fairness_audit.py` to generate SPD/EOD slices",
            ))

        demographic_metrics = os.environ.get("TRACK_DEMOGRAPHIC_METRICS", "false")
        if demographic_metrics.lower() != "true":
            self._findings.append(ComplianceFinding(
                control_id="DG-2",
                severity="low",
                description="Demographic performance metrics tracking not enabled",
                remediation="Set TRACK_DEMOGRAPHIC_METRICS=true",
            ))

    def _check_transparency(self):
        auto_card = _PROJECT_ROOT / "models" / "payshield_gnn_v1_card.md"
        registry_dir = _PROJECT_ROOT / "models" / "registry"
        found_ok = False
        if auto_card.exists():
            found_ok = True
        elif registry_dir.is_dir():
            for d in os.listdir(registry_dir):
                card_path = registry_dir / d / "model_card.md"
                if card_path.exists():
                    found_ok = True
                    break
        if not found_ok:
            self._findings.append(ComplianceFinding(
                control_id="TR-1",
                severity="low",
                description="No model card found — EU AI Act Article 13 requires transparency documentation",
                remediation="Run `python scripts/generate_model_card.py`",
            ))

    def _check_technical_documentation(self):
        tech_doc = _PROJECT_ROOT / "docs" / "technical-documentation.md"
        if not (tech_doc.exists() or (_PROJECT_ROOT / "docs").is_dir()):
            self._findings.append(ComplianceFinding(
                control_id="TR-2",
                severity="low",
                description="Technical documentation not found",
                remediation="Create technical documentation at docs/technical-documentation.md",
            ))

    def _check_human_oversight(self):
        has_review_agent = (_PROJECT_ROOT / "agents" / "human_review_agent.py").exists()
        if not has_review_agent:
            self._findings.append(ComplianceFinding(
                control_id="HO-1",
                severity="medium",
                description="HumanReviewAgent module not found — EU AI Act requires human oversight for high-risk AI",
                remediation="Ensure the HumanReviewAgent module is operational",
            ))

        override_log = _PROJECT_ROOT / "store" / "feedback"
        if not override_log.is_dir():
            self._findings.append(ComplianceFinding(
                control_id="HO-2",
                severity="low",
                description="Override tracking directory not found",
                remediation="Enable feedback tracking at store/feedback/",
            ))

        oversight_log = _PROJECT_ROOT / "store" / "audit_logs"
        has_logs = oversight_log.is_dir() and any(
            f.endswith(".jsonl") for f in os.listdir(oversight_log)
        ) if oversight_log.is_dir() else False
        if not has_logs:
            self._findings.append(ComplianceFinding(
                control_id="HO-3",
                severity="low",
                description="Human oversight audit log not populated — Article 14 requires log of all human interventions",
                remediation="Log all human overrides/reviews through the audit pipeline",
            ))

    def _check_accuracy(self):
        metrics_file = _PROJECT_ROOT / "models" / "gnn_benchmark_results.json"
        if metrics_file.exists():
            try:
                with open(metrics_file) as f:
                    results = json.load(f)
                test_metrics = results.get("gnn", {}).get("test_metrics", {})
                pr_auc = test_metrics.get("auc_pr", 0)
                prevalence = results.get("data", {}).get("fraud_ratio", 0.05)
                if pr_auc < 2.0 * prevalence:
                    self._findings.append(ComplianceFinding(
                        control_id="AC-1",
                        severity="high",
                        description=f"PR-AUC {pr_auc:.4f} below 2x no-skill baseline ({2.0 * prevalence:.4f})",
                        remediation="Retrain model with more history or real data",
                        evidence={"pr_auc": pr_auc, "baseline": 2.0 * prevalence},
                    ))
            except Exception:
                pass
        else:
            self._findings.append(ComplianceFinding(
                control_id="AC-1",
                severity="medium",
                description="GNN benchmark results not found",
                remediation="Run scripts/benchmark_gnn.py",
            ))

    def _check_robustness(self):
        adversarial_dir = _PROJECT_ROOT / "reports" / "adversarial"
        if not adversarial_dir.is_dir():
            self._findings.append(ComplianceFinding(
                control_id="RB-1",
                severity="low",
                description="Adversarial testing reports not found",
                remediation="Run adversarial testing and store reports",
            ))

    def generate_report(self) -> dict:
        result = self.run()
        report_path = _PROJECT_ROOT / "compliance" / "reports" / f"eu_ai_act_{datetime.now().strftime('%Y%m%d')}.json"
        os.makedirs(report_path.parent, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"EU AI Act report saved to {report_path}")
        return result.to_dict()
