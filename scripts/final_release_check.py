#!/usr/bin/env python3
"""
PayShield Final Release Check
Verifies all components are healthy before production release.
Runs autonomously and produces a pass/fail report.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from typing import List, Tuple


class ReleaseCheck:
    def __init__(self):
        self.checks: List[Tuple[str, bool, str]] = []
        self.start_time = datetime.now()

    def run_check(self, name: str, fn, *args, **kwargs) -> None:
        try:
            result = fn(*args, **kwargs)
            status = bool(result)
            msg = str(result) if not status else "OK"
        except Exception as e:
            status = False
            msg = str(e)
        self.checks.append((name, status, msg))
        symbol = "PASS" if status else "FAIL"
        print(f"  [{symbol}] {name}: {msg}")

    def check_docker_build(self) -> bool:
        result = subprocess.run(
            ["docker", "build", "-q", "-t", "payshield/api:check", "."],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0

    def check_python_imports(self) -> bool:
        imports = [
            "fastapi", "pydantic", "sqlalchemy", "celery",
            "xgboost", "lightgbm", "catboost", "sklearn",
            "prometheus_client", "websockets", "alembic",
        ]
        for mod in imports:
            __import__(mod)
        return True

    def check_linting(self) -> bool:
        result = subprocess.run(
            ["ruff", "check", "."],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0

    def check_tests(self) -> Tuple[bool, str]:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            passed = result.stdout.count("passed")
            return True, f"{passed} tests passed"
        return False, result.stdout[-500:] if result.stdout else result.stderr[-500:]

    def check_api_startup(self) -> bool:
        import uvicorn
        from api.main import app
        return app is not None

    def check_configs_exist(self) -> bool:
        required = [
            "requirements.txt",
            "pyproject.toml",
            "Dockerfile",
            ".dockerignore",
            "Makefile",
            "alembic.ini",
        ]
        for f in required:
            if not os.path.exists(f):
                return False
        return True

    def check_docs_exist(self) -> bool:
        required_dirs = [
            "docs/",
            "docs/guides/",
            "docs/architecture/",
            "docs/api/",
            "docs/operations/",
            "docs/training/",
            "docs/reference/",
        ]
        for d in required_dirs:
            if not os.path.isdir(d):
                return False
        return True

    def check_k8s_manifests(self) -> bool:
        required = [
            "k8s/base/kustomization.yaml",
            "k8s/base/payshield-deployment.yaml",
            "k8s/base/payshield-service.yaml",
        ]
        for f in required:
            if not os.path.exists(f):
                return False
        return True

    def check_dr_scripts(self) -> bool:
        required = [
            "dr/backup-postgres.sh",
            "dr/restore-postgres.sh",
            "dr/DR_RUNBOOK.md",
        ]
        for f in required:
            if not os.path.exists(f):
                return False
        return True

    def check_scripts_executable(self) -> bool:
        check_scripts = [
            "dr/backup-postgres.sh",
            "dr/backup-redis.sh",
            "dr/backup-config.sh",
            "dr/restore-postgres.sh",
            "dr/restore-redis.sh",
            "dr/test-restore.sh",
            "scripts/deploy_k8s.sh",
        ]
        for f in check_scripts:
            if os.path.exists(f) and not os.access(f, os.X_OK):
                return False
        return True

    def check_release_artifacts(self) -> bool:
        required = [
            "RELEASE_CHECKLIST.md",
            "HANDOFF_DOCUMENT.md",
            "docs/reference/changelog.md",
        ]
        for f in required:
            if not os.path.exists(f):
                return False
        return True

    def generate_report(self) -> dict:
        duration = (datetime.now() - self.start_time).total_seconds()
        total = len(self.checks)
        passed = sum(1 for _, s, _ in self.checks if s)
        failed = total - passed

        return {
            "version": "1.0.0",
            "timestamp": self.start_time.isoformat(),
            "duration_seconds": duration,
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed / total * 100):.1f}%",
            "status": "PASSED" if failed == 0 else "FAILED",
            "details": [
                {"name": name, "status": "PASSED" if s else "FAILED", "message": msg}
                for name, s, msg in self.checks
            ],
        }

    def run_all(self):
        print("=" * 60)
        print(f"  PayShield v1.0.0 Release Check")
        print(f"  Started: {self.start_time}")
        print("=" * 60)
        print()

        print("Build Checks:")
        self.run_check("Docker build", self.check_docker_build)
        self.run_check("Python imports", self.check_python_imports)

        print("\nCode Quality:")
        self.run_check("Linting (ruff)", self.check_linting)
        self.run_check("Tests", self.check_tests)

        print("\nApplication:")
        self.run_check("API startup", self.check_api_startup)
        self.run_check("Config files exist", self.check_configs_exist)

        print("\nDocumentation:")
        self.run_check("Documentation structure", self.check_docs_exist)
        self.run_check("Release artifacts", self.check_release_artifacts)

        print("\nInfrastructure:")
        self.run_check("K8s manifests", self.check_k8s_manifests)
        self.run_check("DR scripts", self.check_dr_scripts)
        self.run_check("Scripts executable", self.check_scripts_executable)

        print()
        report = self.generate_report()
        print("-" * 60)
        print(f"  Result: {report['status']}")
        print(f"  {report['passed']}/{report['total_checks']} checks passed ({report['pass_rate']})")
        print(f"  Duration: {report['duration_seconds']:.1f}s")
        print("=" * 60)

        # Write report
        report_path = "releases/v1.0.0/release-check-report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {report_path}")

        return report["failed"] == 0


if __name__ == "__main__":
    checker = ReleaseCheck()
    success = checker.run_all()
    sys.exit(0 if success else 1)
