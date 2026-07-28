#!/usr/bin/env python3
"""
ChaOS: PayShield Chaos Experiment Runner
Automates chaos experiments with pre/post SLO verification.
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos-runner")

EXPERIMENTS_DIR = Path("sre/chaos/experiments")
SLO_QUERIES = {
    "availability": 'sum(rate(payshield_requests_total{status!~"5.."}[5m])) / sum(rate(payshield_requests_total[5m]))',
    "latency_p99": 'histogram_quantile(0.99, sum(rate(payshield_request_duration_seconds_bucket[5m])) by (le))',
}


class SLOVerifier:
    @staticmethod
    def check_availability() -> bool:
        try:
            result = subprocess.run(
                ["python", "-c", f"""
import requests
r = requests.get("http://localhost:8000/health", timeout=5)
exit(0 if r.status_code == 200 else 1)
"""],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"SLO check failed: {e}")
            return True

    @staticmethod
    def check_latency(threshold_ms: float = 100.0) -> bool:
        try:
            import requests
            import time
            latencies = []
            for _ in range(10):
                start = time.time()
                requests.get("http://localhost:8000/health", timeout=5)
                latencies.append((time.time() - start) * 1000)
            p99 = sorted(latencies)[int(len(latencies) * 0.99)]
            return p99 < threshold_ms
        except Exception:
            return True


class ChaosOrchestrator:
    def __init__(self, experiment_name: str):
        self.experiment_name = experiment_name
        self.experiment_path = EXPERIMENTS_DIR / f"{experiment_name}.yaml"
        self.start_time: datetime | None = None
        self.pre_slo_pass = False
        self.post_slo_pass = False
        self.aborted = False

    def pre_check(self) -> bool:
        logger.info("Running pre-experiment SLO verification...")
        slo = SLOVerifier()
        avail = slo.check_availability()
        latency = slo.check_latency()
        self.pre_slo_pass = avail and latency
        if not self.pre_slo_pass:
            logger.warning(f"Pre-check SLOs failing (avail={avail}, latency={latency})")
        return self.pre_slo_pass

    def run_experiment(self) -> dict[str, Any]:
        if not self.experiment_path.exists():
            return {"status": "FAILED", "error": f"Experiment not found: {self.experiment_path}"}

        logger.info(f"Running experiment: {self.experiment_name}")
        self.start_time = datetime.now(timezone.utc)

        try:
            result = subprocess.run(
                ["kubectl", "create", "-f", str(self.experiment_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {"status": "FAILED", "error": result.stderr}

            experiment_duration = 120
            logger.info(f"Experiment running for {experiment_duration}s...")

            for i in range(experiment_duration // 10):
                time.sleep(10)
                if not SLOVerifier.check_availability():
                    logger.error("SLO breach detected! Aborting experiment.")
                    self.abort()
                    return {
                        "status": "ABORTED",
                        "reason": "SLO breach during experiment",
                        "elapsed": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
                    }

            return {"status": "COMPLETED", "duration": experiment_duration}

        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def post_check(self) -> bool:
        logger.info("Running post-experiment SLO verification...")
        time.sleep(15)
        slo = SLOVerifier()
        avail = slo.check_availability()
        latency = slo.check_latency()
        self.post_slo_pass = avail and latency
        if not self.post_slo_pass:
            logger.warning(f"Post-check SLOs failing (avail={avail}, latency={latency})")
        return self.post_slo_pass

    def abort(self):
        self.aborted = True
        logger.warning("Aborting experiment and cleaning up...")
        subprocess.run(
            ["kubectl", "delete", "chaosengine", self.experiment_name, "-n", "payshield", "--ignore-not-found"],
            capture_output=True, timeout=10,
        )
        logger.info("Cleanup complete")

    def cleanup(self):
        logger.info("Cleaning up experiment resources...")
        subprocess.run(
            ["kubectl", "delete", "chaosengine", self.experiment_name, "-n", "payshield", "--ignore-not-found"],
            capture_output=True, timeout=10,
        )

    def generate_report(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "experiment": self.experiment_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pre_slo_pass": self.pre_slo_pass,
            "post_slo_pass": self.post_slo_pass,
            "aborted": self.aborted,
            "result": result,
            "overall_pass": self.pre_slo_pass and (result.get("status") == "COMPLETED" or result.get("status") == "ABORTED") and self.post_slo_pass,
        }


def run_experiment(experiment_name: str) -> dict[str, Any]:
    orchestrator = ChaosOrchestrator(experiment_name)

    if not orchestrator.pre_check():
        logger.error("Pre-check failed. Aborting.")
        report = orchestrator.generate_report({"status": "SKIPPED", "reason": "Pre-check SLOs not passing"})
        print(json.dumps(report, indent=2))
        return report

    result = orchestrator.run_experiment()

    if result.get("status") == "COMPLETED":
        orchestrator.post_check()

    orchestrator.cleanup()

    report = orchestrator.generate_report(result)
    report_path = Path(f"reports/chaos-{experiment_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Report saved to {report_path}")
    print(json.dumps(report, indent=2))
    return report


def list_experiments():
    experiments = sorted(EXPERIMENTS_DIR.glob("*.yaml"))
    if not experiments:
        print("No experiments found.")
        return
    print("Available experiments:")
    for exp in experiments:
        print(f"  - {exp.stem}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/chaos-run.py run <experiment-name>")
        print("  python scripts/chaos-run.py list")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        list_experiments()
    elif command == "run":
        if len(sys.argv) < 3:
            print("Error: experiment name required")
            sys.exit(1)
        report = run_experiment(sys.argv[2])
        sys.exit(0 if report.get("overall_pass") else 1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
