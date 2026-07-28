import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from compliance.pci_dss import ComplianceFinding, ComplianceResult

logger = logging.getLogger(__name__)


RBI_CONTROLS = {
    "DL-1": {"description": "Payment data stored in Indian region only"},
    "DL-2": {"description": "No cross-border replication of primary transaction data"},
    "AI-1": {"description": "Every BLOCK decision has associated explanation (GNNExplainer + SHAP + LLM)"},
    "AI-2": {"description": "Human oversight active — analyst feedback loop operational"},
    "AI-3": {"description": "Model risk management — model cards published, drift detection active"},
    "AI-4": {"description": "AI decision explainability: rationale provided for every automated decision"},
}


class RBILocalizationChecker:
    def __init__(self, db_session=None):
        self._db = db_session
        self._findings: list[ComplianceFinding] = []

    def run(self) -> ComplianceResult:
        logger.info("Running RBI compliance check...")
        self._findings = []

        self._check_data_localization()
        self._check_explainability()
        self._check_human_oversight()
        self._check_model_risk()

        passed = len([f for f in self._findings if f.severity == "high"]) == 0
        total_controls = len(RBI_CONTROLS)
        passed_controls = total_controls - len(self._findings)
        score = int((passed_controls / max(total_controls, 1)) * 100)

        return ComplianceResult(
            framework="RBI",
            score=score,
            findings=self._findings,
            passed=passed,
        )

    def _check_data_localization(self):
        region = os.environ.get("DATA_REGION", "unknown")
        if region.lower() not in ("in", "india", "ap-south-1"):
            self._findings.append(ComplianceFinding(
                control_id="DL-1",
                severity="high",
                description=f"Data region set to '{region}' — must be India (IN) for RBI compliance",
                remediation="Set DATA_REGION=IN and ensure all databases are in Indian region",
                evidence={"current_region": region, "required_region": "IN"},
            ))

        cross_border_replication = os.environ.get("CROSS_BORDER_REPLICATION", "false")
        if cross_border_replication.lower() == "true":
            self._findings.append(ComplianceFinding(
                control_id="DL-2",
                severity="high",
                description="Cross-border replication enabled — violates RBI data localization mandate",
                remediation="Disable cross-border replication for primary transaction data",
            ))

    def _check_explainability(self):
        models_dir = "models/production"
        explanation_dir = os.path.join(models_dir, "explanations")
        has_explanations = os.path.isdir(explanation_dir) and len(os.listdir(explanation_dir)) > 0

        if not has_explanations:
            self._findings.append(ComplianceFinding(
                control_id="AI-1",
                severity="medium",
                description="No explanation artifacts found for production decisions",
                remediation="Ensure GNNExplainer + SHAP explanations are generated and stored for every BLOCK decision",
            ))

        llm_narratives_enabled = os.environ.get("ENABLE_LLM_INVESTIGATOR", "false")
        if llm_narratives_enabled.lower() != "true":
            self._findings.append(ComplianceFinding(
                control_id="AI-1",
                severity="low",
                description="LLM narratives not enabled — consider enabling for enhanced explainability",
                remediation="Set ENABLE_LLM_INVESTIGATOR=true to generate natural language explanations",
            ))

    def _check_human_oversight(self):
        feedback_dir = "store/feedback"
        if not os.path.isdir(feedback_dir):
            self._findings.append(ComplianceFinding(
                control_id="AI-2",
                severity="high",
                description="Analyst feedback directory not found — human oversight loop may be inactive",
                remediation="Verify HumanReviewAgent is operational and feedback is being collected",
            ))
        else:
            feedback_count = len(os.listdir(feedback_dir))
            if feedback_count < 10:
                self._findings.append(ComplianceFinding(
                    control_id="AI-2",
                    severity="low",
                    description=f"Only {feedback_count} feedback entries — may indicate low analyst engagement",
                    remediation="Verify analyst feedback loop is active and being used regularly",
                ))

    def _check_model_risk(self):
        registry_dir = "models/registry"
        if not os.path.isdir(registry_dir):
            self._findings.append(ComplianceFinding(
                control_id="AI-3",
                severity="high",
                description="Model registry not found — model cards may not be published",
                remediation="Initialize model registry with model cards for all production models",
            ))
        else:
            versions = [d for d in os.listdir(registry_dir) if d.startswith("v")]
            if not versions:
                self._findings.append(ComplianceFinding(
                    control_id="AI-3",
                    severity="medium",
                    description="Model registry exists but contains no versioned models",
                    remediation="Register production models with complete model cards",
                ))

    def generate_report(self) -> dict:
        result = self.run()
        report_path = f"compliance/reports/rbi_{datetime.now().strftime('%Y%m%d')}.json"
        os.makedirs("compliance/reports", exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"RBI report saved to {report_path}")
        return result.to_dict()
