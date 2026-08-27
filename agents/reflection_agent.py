import logging
from datetime import UTC, datetime, timedelta

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage
from store.audit_log import AuditLogReader

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
            "generated_at": datetime.now(UTC).isoformat(),
        }


class ReflectionAgent(BaseAgent):
    """Reflects over recent return-risk scoring to find drift and bias.

    ``TRIGGER_REFLECTION`` messages pull the audit chain's recent
    ``RETURN_RISK_SCORED`` entries, measure tier distribution and score
    drift, and produce a report with actionable recommendations routed to the
    human-review agent. Uses the deterministic risk-suite analysis for the
    return-risk + chargeback surfaces.
    """

    def __init__(self, config: AgentConfig | None = None, redis_client=None):
        if config is None:
            config = AgentConfig(agent_id="reflection_agent", agent_type="REFLECTION", timeout_seconds=120)
        super().__init__(config)
        self.redis = redis_client

    async def process(self, message: AgentMessage) -> AgentMessage:
        content = message.content
        if message.message_type == "TRIGGER_REFLECTION":
            period_hours = int(content.get("period_hours", 24))
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
        end = datetime.now(UTC)
        start = end - timedelta(hours=period_hours)

        report = ReflectionReport(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
        )

        records = self._get_scored_records(start, end)
        if not records:
            report.add_finding(
                category="no_data",
                description=f"No return-risk scores recorded in the last {period_hours}h",
                severity="info",
            )
            return report

        self._analyze_tier_mix(report, records)
        self._analyze_score_drift(report, records)
        self._analyze_cod_concentration(report, records)
        self._analyze_new_user_concentration(report, records)

        # Chargeback surface, from the audit chain (webhook-driven).
        chargeback_records = self._get_chargeback_records(start, end)
        if chargeback_records:
            suite = self.analyze_risk_suite(
                return_records=records,
                chargeback_records=chargeback_records,
                drift_detected=bool(report.findings),
            )
            for rec in suite.get("recommendations", []):
                report.add_recommendation(
                    target=rec.get("target", "return_risk"),
                    change=rec,
                    rationale=rec.get("reason", ""),
                    requires_approval=True,
                )

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

    def analyze_risk_suite(
        self,
        return_records: list[dict] | None = None,
        chargeback_records: list[dict] | None = None,
        drift_detected: bool = False,
    ) -> dict:
        """Deterministic reflection over the return-risk + chargeback surfaces."""
        from agents.risk_suite_reflection import build_risk_suite_reflection

        return build_risk_suite_reflection(
            return_records=return_records or [],
            chargeback_records=chargeback_records or [],
            drift_detected=drift_detected,
        )

    # ------------------------------------------------------------------ #
    # analysis                                                            #
    # ------------------------------------------------------------------ #

    def _get_scored_records(self, start: datetime, end: datetime) -> list[dict]:
        records = []
        for entry in AuditLogReader().get_entries(event_type="RETURN_RISK_SCORED"):
            ts = entry.get("timestamp", "")
            if not ts or not (start <= datetime.fromisoformat(ts) <= end):
                continue
            payload = entry.get("payload", {})
            records.append({
                "order_id": payload.get("order_id", ""),
                "user_id": entry.get("actor", ""),
                "score": float(payload.get("score", 0.0) or 0.0),
                "risk_tier": payload.get("tier", "LOW"),
                "merchant_id": payload.get("merchant_id", ""),
            })
        return records

    def _get_chargeback_records(self, start: datetime, end: datetime) -> list[dict]:
        records = []
        for entry in AuditLogReader().get_entries():
            if entry.get("event_type") not in ("CHARGEBACK_RESPONDED", "CHARGEBACK_SUBMITTED"):
                continue
            ts = entry.get("timestamp", "")
            if not ts or not (start <= datetime.fromisoformat(ts) <= end):
                continue
            payload = entry.get("payload", {})
            records.append({
                "response_type": payload.get("response_type", ""),
                "outcome": payload.get("outcome", ""),
                "count": 1,
            })
        return records

    def _analyze_tier_mix(self, report: ReflectionReport, records: list[dict]) -> None:
        total = len(records)
        high = sum(1 for r in records if r.get("risk_tier") == "HIGH")
        medium = sum(1 for r in records if r.get("risk_tier") == "MEDIUM")
        high_share = high / total if total else 0.0
        if high_share > 0.40:
            report.add_finding(
                category="tier_skew",
                description=f"HIGH tier share {high_share:.0%} over {total} scored orders — review gate may be too wide",
                severity="medium",
                evidence={"high": high, "medium": medium, "total": total, "high_share": round(high_share, 4)},
            )
            report.add_recommendation(
                target="return_risk.risk_tiers.HIGH.max_score",
                change={"max_score": 0.75},
                rationale=f"HIGH-tier share {high_share:.0%} exceeds the 40% ceiling",
                requires_approval=True,
            )

    def _analyze_score_drift(self, report: ReflectionReport, records: list[dict]) -> None:
        if len(records) < 20:
            return
        first_half = [r["score"] for r in records[: len(records) // 2]]
        second_half = [r["score"] for r in records[len(records) // 2 :]]
        recent_avg = sum(second_half) / len(second_half)
        older_avg = sum(first_half) / len(first_half)
        if older_avg == 0:
            return
        drift = abs(recent_avg - older_avg) / older_avg
        if drift > 0.3:
            report.add_finding(
                category="score_drift",
                description=f"Mean return-risk score drifted {(recent_avg - older_avg):+.3f} across the period",
                severity="low",
                evidence={"older_avg": round(older_avg, 4), "recent_avg": round(recent_avg, 4), "drift": round(drift, 4)},
            )

    def _analyze_cod_concentration(self, report: ReflectionReport, records: list[dict]) -> None:
        merchant_totals: dict[str, list[float]] = {}
        for r in records:
            m = r.get("merchant_id") or "unknown"
            merchant_totals.setdefault(m, []).append(r["score"])
        for merchant, scores in merchant_totals.items():
            if len(scores) < 5:
                continue
            avg = sum(scores) / len(scores)
            if avg > 0.6:
                report.add_finding(
                    category="merchant_concentration",
                    description=f"Merchant {merchant} averages {avg:.2f} return-risk over {len(scores)} orders",
                    severity="low",
                    evidence={"merchant_id": merchant, "avg_score": round(avg, 4), "orders": len(scores)},
                )

    def _analyze_new_user_concentration(self, report: ReflectionReport, records: list[dict]) -> None:
        """Scored orders whose user shows no stored history dominate risk."""
        new_user_scores = [
            r["score"] for r in records
            if (r.get("user_id") or "").lower().startswith(("cust_fresh", "fresh", "u_new", "new_"))
        ]
        if len(new_user_scores) < 5:
            return
        avg = sum(new_user_scores) / len(new_user_scores)
        if avg > 0.5:
            report.add_finding(
                category="new_user_bias",
                description=f"Fresh users average {avg:.2f} return-risk — priors may over-flag new buyers",
                severity="low",
                evidence={"new_user_avg": round(avg, 4), "orders": len(new_user_scores)},
            )
            report.add_recommendation(
                target="return_risk.risk_tiers.LOW.max_score",
                change={"max_score": 0.30},
                rationale="Re-anchor new-user baseline before gating more aggressively",
                requires_approval=True,
            )