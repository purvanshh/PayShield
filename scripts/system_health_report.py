#!/usr/bin/env python3
"""
PayShield Weekly System Health Report Generator.
Pulls metrics and generates a Markdown health report.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SystemHealthReporter:
    def __init__(self):
        self.findings: list[dict] = []
        self.metrics: dict[str, Any] = {}

    def generate_report(self) -> dict[str, Any]:
        print("Generating system health report...")

        self._check_api_health()
        self._check_backup_status()
        self._check_disk_usage()
        self._check_model_age()
        self._check_queue_depth()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health_score": self._compute_health_score(),
            "metrics": self.metrics,
            "findings": self.findings,
            "top_risks": self._get_top_risks(),
            "recommended_actions": self._get_recommendations(),
        }

        report_dir = Path("health-reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"

        md = self._to_markdown(report)
        with open(report_path, "w") as f:
            f.write(md)

        print(f"Report saved to {report_path}")
        return report

    def _check_api_health(self):
        try:
            import requests
            resp = requests.get("http://localhost:8000/health", timeout=5)
            self.metrics["api_health"] = resp.status_code == 200
            if not self.metrics["api_health"]:
                self.findings.append({
                    "category": "api",
                    "severity": "critical",
                    "description": "API health check failed",
                })
        except Exception as e:
            self.metrics["api_health"] = False
            self.findings.append({
                "category": "api",
                "severity": "critical",
                "description": f"API unreachable: {e}",
            })

    def _check_backup_status(self):
        backup_dirs = [
            "compliance/reports/",
            "compliance/evidence/",
            "health-reports/",
        ]

        recent_backups = 0
        for d in backup_dirs:
            if os.path.isdir(d):
                files = os.listdir(d)
                recent = [f for f in files if self._is_recent(os.path.getctime(os.path.join(d, f)))]
                recent_backups += len(recent)

        self.metrics["recent_backups"] = recent_backups
        if recent_backups == 0:
            self.findings.append({
                "category": "backup",
                "severity": "warning",
                "description": "No recent backup artifacts found",
            })

    def _check_disk_usage(self):
        try:
            stat = os.statvfs(".")
            free_gb = (stat.f_frsize * stat.f_bavail) / (1024 ** 3)
            total_gb = (stat.f_frsize * stat.f_blocks) / (1024 ** 3)
            used_pct = (1 - stat.f_bavail / max(stat.f_blocks, 1)) * 100

            self.metrics["disk"] = {
                "total_gb": round(total_gb, 1),
                "free_gb": round(free_gb, 1),
                "used_pct": round(used_pct, 1),
            }

            if used_pct > 85:
                self.findings.append({
                    "category": "infrastructure",
                    "severity": "warning",
                    "description": f"Disk usage at {used_pct:.1f}% — above 85% threshold",
                })
        except Exception:
            pass

    def _check_model_age(self):
        from ml.registry import ModelRegistry
        try:
            registry = ModelRegistry()
            versions = registry.list_versions()
            if versions:
                latest = versions[0]
                created = latest.get("created_at", "")
                if created:
                    created_dt = datetime.fromisoformat(created)
                    age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
                    self.metrics["model_age_days"] = round(age_days, 1)
                    if age_days > 30:
                        self.findings.append({
                            "category": "ml",
                            "severity": "warning",
                            "description": f"Production model {latest.get('version', 'unknown')} is {age_days:.0f} days old — retraining recommended",
                        })
        except Exception:
            self.metrics["model_age_days"] = "unknown"

    def _check_queue_depth(self):
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, db=0)
            depth = r.llen("celery")
            self.metrics["celery_queue_depth"] = depth
            if depth > 1000:
                self.findings.append({
                    "category": "celery",
                    "severity": "warning",
                    "description": f"Celery queue depth at {depth} — above 1000 threshold",
                })
        except Exception:
            self.metrics["celery_queue_depth"] = "unknown"

    def _is_recent(self, timestamp: float, hours: int = 168) -> bool:
        return (datetime.now().timestamp() - timestamp) < (hours * 3600)

    def _compute_health_score(self) -> int:
        score = 100
        for f in self.findings:
            if f["severity"] == "critical":
                score -= 25
            elif f["severity"] == "warning":
                score -= 10
            elif f["severity"] == "info":
                score -= 5
        return max(0, score)

    def _get_top_risks(self) -> list[str]:
        critical = [f["description"] for f in self.findings if f["severity"] == "critical"]
        warnings = [f["description"] for f in self.findings if f["severity"] == "warning"]
        return (critical + warnings)[:3]

    def _get_recommendations(self) -> list[str]:
        recs = []
        for f in self.findings:
            if f["category"] == "ml" and "retraining" in f["description"]:
                recs.append("Trigger model retraining via `make trigger-retrain`")
            if f["category"] == "backup":
                recs.append("Enable Redis persistence (RDB/AOF) for backup")
            if f["category"] == "infrastructure" and "disk" in f["description"]:
                recs.append("Free up disk space or increase volume size")
            if f["category"] == "celery":
                recs.append("Investigate Celery queue — check for stuck tasks")
        return recs[:5]

    def _to_markdown(self, report: dict) -> str:
        lines = [
            f"# PayShield Health Report — {datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"**Generated:** {report['generated_at']}",
            f"**Health Score:** {report['health_score']}/100",
            "",
            "## Metrics",
            "",
        ]

        for k, v in report.get("metrics", {}).items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    lines.append(f"- **{k}.{sk}:** {sv}")
            else:
                lines.append(f"- **{k}:** {v}")

        lines.extend(["", "## Findings", ""])
        for f in report.get("findings", []):
            emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(f["severity"], "⚪")
            lines.append(f"- {emoji} **[{f['severity'].upper()}]** {f['category']}: {f['description']}")

        lines.extend(["", "## Top Risks", ""])
        for risk in report.get("top_risks", []):
            lines.append(f"- {risk}")

        lines.extend(["", "## Recommended Actions", ""])
        for rec in report.get("recommended_actions", []):
            lines.append(f"- [ ] {rec}")

        if not report.get("recommended_actions"):
            lines.append("- No action required at this time")

        lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    reporter = SystemHealthReporter()
    report = reporter.generate_report()

    print(f"\nHealth Score: {report['health_score']}/100")
    print(f"Findings: {len(report['findings'])}")
    print(f"Top Risks: {len(report['top_risks'])}")

    if report["health_score"] < 50:
        print("\nWARNING: Health score below 50 — immediate attention required")
        sys.exit(1)
    elif report["health_score"] < 80:
        print("\nCAUTION: Health score below 80 — review recommended")
        sys.exit(0)
    else:
        print("\nOK: System healthy")
        sys.exit(0)
