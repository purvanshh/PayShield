import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

FRAUD_TYPES = {"MULE_RING", "BURST_ATTACK", "MERCHANT_COLLUSION", "ACCOUNT_TAKEOVER", "OTHER"}
CONFIDENCE_LEVELS = {"HIGH", "MEDIUM", "LOW"}
ACTIONS = {"BLOCK", "REVIEW", "ALLOW"}


@dataclass
class InvestigationReport:
    txn_id: str = ""
    narrative: str = ""
    fraud_type: Literal["MULE_RING", "BURST_ATTACK", "MERCHANT_COLLUSION", "ACCOUNT_TAKEOVER", "OTHER"] = "OTHER"
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    recommended_action: Literal["BLOCK", "REVIEW", "ALLOW"] = "ALLOW"
    key_evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)
    model_version: str = "1.0.0"
    prompt_version: str = "1"
    quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "txn_id": self.txn_id,
            "narrative": self.narrative,
            "fraud_type": self.fraud_type,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "key_evidence": self.key_evidence,
            "reasoning": self.reasoning,
            "generated_at": self.generated_at.isoformat(),
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "quality_score": self.quality_score,
        }


class NarrativeParser:
    def __init__(self, prompt_version: str = "1", model_version: str = "1.0.0"):
        self.prompt_version = prompt_version
        self.model_version = model_version

    def parse(self, raw_output: str, txn_id: str = "",
              expected_action: str | None = None) -> InvestigationReport:
        data = self._extract_json(raw_output)
        report = self._to_report(data, txn_id)
        self._validate(report, expected_action)
        report.quality_score = self.score_quality(report)
        if report.quality_score < 0.5:
            logger.warning(f"Quality score {report.quality_score:.2f} < 0.5 for {txn_id}")
        return report

    def _extract_json(self, raw_output: str) -> dict[str, Any]:
        json_pattern = r'\{[^{}]*\}'
        match = re.search(json_pattern, raw_output, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        brace_pattern = r'(\{(?:[^{}]|(?:\{[^{}]*\}))*\})'
        matches = re.findall(brace_pattern, raw_output, re.DOTALL)
        for candidate in reversed(matches):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        logger.warning(f"No valid JSON found in LLM output: {raw_output[:200]}")
        return {}

    def _to_report(self, data: dict[str, Any], txn_id: str) -> InvestigationReport:
        narrative = data.get("narrative", "") or ""
        fraud_type_raw = str(data.get("fraud_type", "OTHER")).upper()
        confidence_raw = str(data.get("confidence", "LOW")).upper()
        action_raw = str(data.get("recommended_action", "ALLOW")).upper()
        key_evidence = data.get("key_evidence", [])
        if isinstance(key_evidence, list):
            key_evidence = [str(e) for e in key_evidence]
        else:
            key_evidence = [str(key_evidence)]
        reasoning = data.get("reasoning", "") or ""

        fraud_type = fraud_type_raw if fraud_type_raw in FRAUD_TYPES else "OTHER"
        confidence = confidence_raw if confidence_raw in CONFIDENCE_LEVELS else "LOW"
        action = action_raw if action_raw in ACTIONS else "ALLOW"

        return InvestigationReport(
            txn_id=txn_id,
            narrative=narrative,
            fraud_type=fraud_type,
            confidence=confidence,
            recommended_action=action,
            key_evidence=key_evidence,
            reasoning=reasoning,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )

    def _validate(self, report: InvestigationReport, expected_action: str | None = None):
        issues = []
        if not report.narrative or len(report.narrative) < 20:
            issues.append("narrative too short or missing")
        if report.fraud_type not in FRAUD_TYPES:
            issues.append(f"invalid fraud_type: {report.fraud_type}")
        if report.confidence not in CONFIDENCE_LEVELS:
            issues.append(f"invalid confidence: {report.confidence}")
        if report.recommended_action not in ACTIONS:
            issues.append(f"invalid action: {report.recommended_action}")
        if not report.key_evidence:
            issues.append("no key_evidence")
        if expected_action and expected_action in ("BLOCK", "REVIEW"):
            action_rank = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}
            expected_rank = action_rank.get(expected_action, 0)
            actual_rank = action_rank.get(report.recommended_action, 0)
            if actual_rank < expected_rank:
                issues.append(
                    f"recommended_action '{report.recommended_action}' is less "
                    f"conservative than expected '{expected_action}'"
                )
        if issues:
            logger.warning(f"Validation issues for {report.txn_id}: {'; '.join(issues)}")
        return len(issues) == 0

    def score_quality(self, report: InvestigationReport) -> float:
        score = 0.0
        if 100 <= len(report.narrative) <= 500:
            score += 0.3
        elif len(report.narrative) >= 50:
            score += 0.15
        if len(report.key_evidence) >= 2:
            score += 0.2
        elif len(report.key_evidence) >= 1:
            score += 0.1
        if report.fraud_type != "OTHER":
            score += 0.15
        if report.confidence != "LOW":
            score += 0.15
        if len(report.reasoning) >= 50:
            score += 0.2
        elif len(report.reasoning) >= 20:
            score += 0.1
        return round(min(1.0, score), 4)


class FallbackGenerator:
    def generate(self, context: Any) -> InvestigationReport:
        evidence_items = getattr(context, "evidence_items", [])
        stats = getattr(context, "summary_stats", {})

        narrative = self._build_narrative(evidence_items, stats)
        evidence_strs = [
            item.description[:100] for item in evidence_items[:5]
        ]
        reasoning = self._build_reasoning(evidence_items, stats)

        action = getattr(context, "ensemble_decision", "ALLOW")
        if action not in ACTIONS:
            action = "ALLOW"

        fraud_type = self._infer_fraud_type(evidence_items)
        confidence = "HIGH" if len([e for e in evidence_items if e.severity >= 4]) >= 2 else "MEDIUM"

        return InvestigationReport(
            txn_id=getattr(context, "txn_id", ""),
            narrative=narrative,
            fraud_type=fraud_type,
            confidence=confidence,
            recommended_action=action,
            key_evidence=evidence_strs,
            reasoning=reasoning,
            quality_score=0.7,
        )

    def _build_narrative(self, items: list, stats: dict) -> str:
        parts = []
        high_sev = [i for i in items if i.severity >= 4]
        if high_sev:
            top = high_sev[0]
            parts.append(f"{top.description} ({top.type})")
        txn_count = stats.get("txn_count_5min", 0)
        if txn_count > 5:
            parts.append(f"{txn_count} transactions in 5 minutes")
        prob = stats.get("layer2_probability", 0)
        if prob > 0.5:
            parts.append(f"GNN fraud probability {prob:.1%}")
        if parts:
            narrative = "Fraud investigation: " + "; ".join(parts) + "."
        else:
            narrative = "Transaction reviewed with no significant fraud signals detected."
        if len(narrative) > 500:
            narrative = narrative[:497] + "..."
        return narrative

    def _build_reasoning(self, items: list, stats: dict) -> str:
        reasons = []
        for item in items[:3]:
            reasons.append(f"{item.type}: {item.description[:60]}")
        if reasons:
            return "Based on: " + "; ".join(reasons) + "."
        return "No specific evidence available for automated reasoning."

    def _infer_fraud_type(self, items: list) -> str:
        types = [i.type for i in items]
        if "BENFORD" in types:
            return "BURST_ATTACK"
        if "RULE" in types:
            return "MULE_RING"
        return "OTHER"


FALLBACK_GENERATOR = FallbackGenerator()
