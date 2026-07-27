"""Production readiness checklist for PayShield."""

import json
import logging
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHECKS: list[dict] = []


def check(name: str, fn, critical: bool = False):
    try:
        result = fn()
        status = "PASS" if result else "FAIL"
        CHECKS.append({"check": name, "status": status, "critical": critical})
        if status == "FAIL" and critical:
            logger.error(f"CRITICAL FAIL: {name}")
        else:
            logger.info(f"{status}: {name}")
    except Exception as e:
        CHECKS.append({"check": name, "status": "ERROR", "detail": str(e), "critical": critical})
        logger.error(f"ERROR: {name}: {e}")


def _redis_healthy():
    from store.redis_client import RedisClient
    r = RedisClient()
    return r.health_check()


def _model_exists():
    from ml.registry import ModelRegistry
    reg = ModelRegistry()
    path = reg.get_production_path()
    return path is not None and path.exists()


def _celery_worker_active():
    from tasks.celery_app import celery_app
    inspect = celery_app.control.inspect()
    workers = inspect.active()
    return bool(workers)


def _ollama_healthy():
    import asyncio
    from llm.client import OllamaClient
    from llm.config import OllamaConfig
    client = OllamaClient(OllamaConfig())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(client.health())
        return result
    finally:
        loop.close()


def _migrations_applied():
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True, text=True, timeout=10,
    )
    return "head" in result.stdout


def main():
    logger.info("=" * 50)
    logger.info("PayShield Production Checklist")
    logger.info(f"Time: {datetime.utcnow().isoformat()}")
    logger.info("=" * 50)

    check("Redis health", _redis_healthy, critical=True)
    check("Production model exists", _model_exists, critical=True)
    check("PostgreSQL migrations applied", _migrations_applied, critical=True)
    check("Celery workers active", _celery_worker_active, critical=False)
    check("Ollama endpoint healthy", _ollama_healthy, critical=False)

    logger.info("=" * 50)
    passed = sum(1 for c in CHECKS if c["status"] == "PASS")
    failed = sum(1 for c in CHECKS if c["status"] == "FAIL")
    errors = sum(1 for c in CHECKS if c["status"] == "ERROR")
    logger.info(f"Results: {passed} passed, {failed} failed, {errors} errors")

    report_path = "checklist_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "checks": CHECKS,
            "summary": {"passed": passed, "failed": failed, "errors": errors},
        }, f, indent=2)
    logger.info(f"Report written to {report_path}")

    critical_failures = [c for c in CHECKS if c["status"] == "FAIL" and c.get("critical")]
    if critical_failures:
        logger.error("Critical checks failed!")
        sys.exit(1)
    logger.info("All critical checks passed.")


if __name__ == "__main__":
    main()
