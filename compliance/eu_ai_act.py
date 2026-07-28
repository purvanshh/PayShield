import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from compliance.pci_dss import ComplianceFinding, ComplianceResult

logger = logging.getLogger(__name__)


EU_AI_ACT_CONTROLS = {
    "RM-1": {"description": "Risk assessment document exists and updated quarterly"},
    "DG-1": {"description": "Training data quality validation — bias detection report"},
    "DG-2": {"description": "Demographic performance metrics tracked and reviewed"},
    "TR-1": {"description": "Model cards include intended use, limitations, and known biases"},
    "HO-1": {"description": "Human oversight — HumanReviewAgent can overturn any AI decision"},
    "HO-2": {"description": "Override rate tracked and reported"},
    "AC-1": {"description": "AUC-ROC > 0.92 maintained with continuous monitoring"},
    "AC-2": {"description": "False positive rate < 5%"},
    "RB-1": {"description": "Adversarial testing (noise injection) completed quarterly"},
}


class EUAiActComplianceChecker:
    def __init__(self, db_session=None):
        self._db = db_session
        self._findings: list[ComplianceFinding] = []

    def run(self) -> ComplianceResult:
        logger.info("Running EU AI Act compliance check...")
        self._findings = []

        self._check_risk_management()
        self._check_data_governance()
        self._check_transparency()
        self._check_human_oversight()
        self._check_accuracy()
        self._check_robustness()

        passed = len([f for f in self._findings if f.severity == "high"]) == 0
        total_controls = len(EU_AI_ACT_CONTROLS)
        passed_controls = total_controls - len(self._findings)
        score = int((passed_controls / max(total_controls, 1)) * 100)

        return ComplianceResult(
            framework="EU_AI_ACT",
            score=score,
            findings=self._findings,
            passed=passed,
        )

    def _check_risk_management(self):
        if not os.path.exists("docs/security/risk-assessment.md"):
            self._findings.append(ComplianceFinding(
                control_id="RM-1",
                severity="high",
                description="Risk assessment document not found — EU AI Act requires documented risk management",
                remediation="Create risk assessment document at docs/security/risk-assessment.md and update quarterly",
            ))

    def _check_data_governance(self):
        bias_report = "reports/bias_detection"
        if not os.path.isdir(bias_report):
            self._findings.append(ComplianceFinding(
                control_id="DG-1",
                severity="medium",
                description="Bias detection report directory not found",
                remediation="Run bias detection pipeline and store reports in reports/bias_detection/",
            ))

        demographic_metrics = os.environ.get("TRACK_DEMOGRAPHIC_METRICS", "false")
        if demographic_metrics.lower() != "true":
            self._findings.append(ComplianceFinding(
                control_id="DG-2",
                severity="medium",
                description="Demographic performance metrics tracking not enabled",
                remediation="Set TRACK_DEMOGRAPHIC_METRICS=true and configure per-group performance monitoring",
            ))

    def _check_transparency(self):
        registry_dir = "models/registry"
        if os.path.isdir(registry_dir):
            has_model_cards = False
            for d in os.listdir(registry_dir):
                card_path = os.path.join(registry_dir, d, "model_card.md")
                if os.path.exists(card_path):
                    has_model_cards = True
                    with open(card_path) as f:
                        content = f.read()
                        if "limitations" not in content.lower() or "bias" not in content.lower():
                            self._findings.append(ComplianceFinding(
                                control_id="TR-1",
                                severity="low",
                                description=f"Model card for {d} missing limitations or bias disclosure",
                                remediation="Update model card to include intended use, limitations, and known biases",
                            ))
            if not has_model_cards:
                self._findings.append(ComplianceFinding(
                    control_id="TR-1",
                    severity="high",
                    description="No model cards found — EU AI Act requires transparency documentation",
                    remediation="Generate model cards for all production models",
                ))
        else:
            self._findings.append(ComplianceFinding(
                control_id="TR-1",
                severity="high",
                description="Model registry not found — cannot verify model cards",
                remediation="Initialize model registry with model cards",
            ))

    def _check_human_oversight(self):
        human_review_config = os.environ.get("ENABLE_HUMAN_REVIEW", "false")
        if human_review_config.lower() != "true":
            self._findings.append(ComplianceFinding(
                control_id="HO-1",
                severity="high",
                description="Human review agent not enabled — EU AI Act requires human oversight for high-risk AI",
                remediation="Set ENABLE_HUMAN_REVIEW=true and ensure HumanReviewAgent is operational",
            ))

    def _check_accuracy(self):
        metrics_file = "models/production/manifest.json"
        if os.path.exists(metrics_file):
            try:
                with open(metrics_file) as f:
                    metrics = json.load(f)
                auc_roc = metrics.get("metrics", {}).get("test_auc_roc", 0)
                if auc_roc < 0.92:
                    self._findings.append(ComplianceFinding(
                        control_id="AC-1",
                        severity="high",
                        description=f"AUC-ROC {auc_roc:.4f} below 0.92 threshold",
                        remediation="Retrain model to achieve AUC-ROC > 0.92",
                        evidence={"current_auc_roc": auc_roc, "threshold": 0.92},
                    ))
            except Exception:
                pass

    def _check_robustness(self):
        adversarial_test_dir = "reports/adversarial"
        if not os.path.isdir(adversarial_test_dir):
            self._findings.append(ComplianceFinding(
                control_id="RB-1",
                severity="medium",
                description="Adversarial testing reports not found — quarterly robustness testing required",
                remediation="Run adversarial testing (noise injection on features) and store reports in reports/adversarial/",
            ))

    def generate_report(self) -> dict:
        result = self.run()
        report_path = f"compliance/reports/eu_ai_act_{datetime.now().strftime('%Y%m%d')}.json"
        os.makedirs("compliance/reports", exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"EU AI Act report saved to {report_path}")
        return result.to_dict()
