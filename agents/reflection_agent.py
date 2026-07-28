import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from agents.base import BaseAgent, AgentConfig
from agents.message import AgentMessage

logger = logging.getLogger(__name__)


class ReflectionReport:
    def __init__(self, period_start: str, period_end: str):
        self.period_start = period_start
        self.period_end = period_end
        self.findings: list[dict] = []
        self.recommendations: list[dict] = []
        self.weaknesses: dict[str, list[str]] = {}

    def add_finding(self, category: str, description: str, severity: str, evidence: dict | None = None):
        self.findings.append({
            "category": category,
            "description": description,
            "severity": severity,
            "evidence": evidence or {},
        })

    def add_recommendation(self, target: str, change: dict, rationale: str, requires_approval: bool = True):
        self.recommendations.append({
            "target": target,
            "change": change,
            "rationale": rationale,
            "requires_approval": requires_approval,
        })

    def to_dict(self) -> dict:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "weaknesses": self.weaknesses,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


class ReflectionAgent(BaseAgent):
    def __init__(self, config: AgentConfig | None = None):
        if config is None:
            config = AgentConfig(agent_id="reflection_agent", agent_type="REFLECTION", timeout_seconds=120)
        super().__init__(config)

    async def process(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        if message.message_type == "TRIGGER_REFLECTION":
            period_hours = content.get("period_hours", 24)
            report = await self.analyze_period(period_hours)
            recommendations = self.generate_recommendations(report)

            return AgentMessage(
                sender=self.config.agent_id,
                recipient="human_review_agent",
                message_type="REFLECTION_REPORT",
                content={"report": report.to_dict(), "recommendations": recommendations},
                correlation_id=message.correlation_id,
                priority=3,
            )

        return AgentMessage(
            sender=self.config.agent_id,
            recipient=message.sender,
            message_type="ERROR",
            content={"error": f"Unexpected message type: {message.message_type}"},
            correlation_id=message.correlation_id,
        )

    async def analyze_period(self, period_hours: int = 24) -> ReflectionReport:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=period_hours)

        report = ReflectionReport(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
        )

        feedback_data = self._get_feedback_data(start, end)

        fp_by_merchant = self._cluster_false_positives(feedback_data)
        for merchant, count in fp_by_merchant.items():
            if count > 10:
                report.add_finding(
                    category="false_positive_cluster",
                    description=f"False positives clustered around merchant category: {merchant} ({count} occurrences)",
                    severity="high",
                    evidence={"merchant_category": merchant, "count": count},
                )
                report.add_recommendation(
                    target=f"rules.{merchant}_threshold",
                    change={"threshold_adjustment": 0.15},
                    rationale=f"FP rate for {merchant} exceeds acceptable threshold",
                    requires_approval=True,
                )

        new_user_fp = self._analyze_new_user_fp(feedback_data)
        if new_user_fp > 0.15:
            report.add_finding(
                category="new_user_bias",
                description=f"GNN over-predicts fraud for new users (< 7 days): FP rate {new_user_fp:.1%}",
                severity="medium",
                evidence={"new_user_fp_rate": new_user_fp, "threshold": 0.15},
            )
            report.add_recommendation(
                target="ml.ensemble.confidence_threshold",
                change={"new_user_confidence_boost": 0.05},
                rationale="Reduce false positives for new users by increasing confidence threshold",
                requires_approval=True,
            )

        salary_day_fp = self._analyze_salary_day_fp(feedback_data)
        if salary_day_fp > 0.10:
            report.add_finding(
                category="salary_day_pattern",
                description=f"Statistical filter triggers too aggressively on salary-day transactions: FP rate {salary_day_fp:.1%}",
                severity="low",
                evidence={"salary_day_fp_rate": salary_day_fp},
            )
            report.add_recommendation(
                target="rules.salary_day_sensitivity",
                change={"sensitivity_reduction": 0.20},
                rationale="Reduce statistical filter sensitivity on expected salary days",
                requires_approval=True,
            )

        agent_weaknesses = self._analyze_agent_performance(feedback_data)
        report.weaknesses = agent_weaknesses

        return report

    def generate_recommendations(self, report: ReflectionReport) -> list[dict]:
        config_changes = []
        for rec in report.recommendations:
            config_changes.append({
                "target": rec["target"],
                "change": rec["change"],
                "rationale": rec["rationale"],
                "requires_approval": rec["requires_approval"],
                "agent_id": self.config.agent_id,
            })
        return config_changes

    def _get_feedback_data(self, start: datetime, end: datetime) -> list[dict]:
        return []

    def _cluster_false_positives(self, feedback: list[dict]) -> dict[str, int]:
        clusters: dict[str, int] = {}
        for item in feedback:
            merchant = item.get("merchant_category", "unknown")
            if item.get("label") == "FALSE_POSITIVE":
                clusters[merchant] = clusters.get(merchant, 0) + 1
        return dict(sorted(clusters.items(), key=lambda x: x[1], reverse=True)[:5])

    def _analyze_new_user_fp(self, feedback: list[dict]) -> float:
        new_user_count = 0
        fp_count = 0
        for item in feedback:
            if item.get("user_age_days", 999) < 7:
                new_user_count += 1
                if item.get("label") == "FALSE_POSITIVE":
                    fp_count += 1
        return fp_count / max(new_user_count, 1)

    def _analyze_salary_day_fp(self, feedback: list[dict]) -> float:
        salary_count = 0
        fp_count = 0
        for item in feedback:
            if item.get("is_salary_day", False):
                salary_count += 1
                if item.get("label") == "FALSE_POSITIVE":
                    fp_count += 1
        return fp_count / max(salary_count, 1)

    def _analyze_agent_performance(self, feedback: list[dict]) -> dict[str, list[str]]:
        weaknesses: dict[str, list[str]] = {}
        agent_errors: dict[str, list[dict]] = {}
        for item in feedback:
            agent = item.get("agent_id", "unknown")
            if agent not in agent_errors:
                agent_errors[agent] = []
            if item.get("label") in ("FALSE_POSITIVE", "FALSE_NEGATIVE"):
                agent_errors[agent].append(item)

        for agent, errors in agent_errors.items():
            if len(errors) > 5:
                weaknesses[agent] = [
                    f"{len(errors)} incorrect decisions in analysis period",
                    f"Most common error: {max(set(e.get('error_type', 'unknown') for e in errors), key=errors.count)}",
                ]

        return weaknesses
