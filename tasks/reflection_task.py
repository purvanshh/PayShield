import json
import logging

from store.redis_client import create_redis
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_nightly_reflection(self, period_hours: int = 24):
    logger.info(f"Starting nightly reflection analysis for last {period_hours}h")
    try:
        from agents.base import AgentConfig
        from agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent(
            AgentConfig(agent_id="reflection_agent", agent_type="REFLECTION")
        )
        report = agent.analyze_period(period_hours)
        logger.info(f"Nightly reflection complete: {len(report.findings)} findings, "
                    f"{len(report.recommendations)} recommendations")

        result = report.to_dict()
        try:
            redis = create_redis(mode="sync")
            redis.set("reflection:latest", json.dumps(result), ttl=86400 * 7)
        except Exception as e:
            logger.warning(f"reflection_store_failed: {e}")

        return result
    except Exception as exc:
        logger.error(f"Nightly reflection failed: {exc}")
        raise self.retry(exc=exc) from exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=600)
def sync_reflection_weights(self):
    logger.info("Syncing reflection weights from analyst feedback...")
    try:
        from agents.base import AgentConfig
        from agents.reflection_agent import ReflectionAgent

        agent = ReflectionAgent(
            AgentConfig(agent_id="reflection_agent", agent_type="REFLECTION")
        )
        report = agent.analyze_period(period_hours=24)

        weight_adjustments = {}
        for rec in report.recommendations:
            target = rec.get("target", "")
            change = rec.get("change", {})
            weight_adjustments[target] = change

        try:
            redis = create_redis(mode="sync")
            redis.set("reflection:weights", json.dumps(weight_adjustments), ttl=86400)
            redis.set("reflection:weights_timestamp", str(1449462227), ttl=86400)
            logger.info(f"Weight adjustments saved: {len(weight_adjustments)} targets")
        except Exception as e:
            logger.warning(f"reflection_store_failed: {e}")

        return {"status": "synced", "adjustments": weight_adjustments}
    except Exception as exc:
        logger.error(f"Weight sync failed: {exc}")
        raise self.retry(exc=exc) from exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=600)
def run_risk_suite_reflection(self):
    """Nightly reflection over the Track 2 risk suite.

    Reads outcome records (scoring tiers vs actual returns; chargeback
    response vs outcome) from Redis when present and produces the
    recommendation payload (threshold adjustments, response strategy,
    retraining trigger) stored under ``reflection:risk_suite``.
    """
    log = logging.getLogger(__name__)
    try:
        from agents.risk_suite_reflection import build_risk_suite_reflection

        redis = create_redis(mode="sync")

        return_records = _scan_records(redis, "return_risk:outcome:", ["risk_tier", "returned", "user_type"])
        chargeback_records = _scan_records(
            redis, "chargeback:outcome:", ["response_type", "outcome", "count"]
        )

        payload = build_risk_suite_reflection(
            return_records=return_records,
            chargeback_records=chargeback_records,
            drift_detected=bool(redis.get("config:reflection:drift_detected")),
        )
        redis.set("reflection:risk_suite", json.dumps(payload), ttl=86400 * 7)
        log.info(
            "risk suite reflection: %d recommendations from %d return records / %d chargeback records",
            len(payload["recommendations"]),
            len(return_records),
            len(chargeback_records),
        )
        return payload
    except Exception as exc:
        log.error(f"risk suite reflection failed: {exc}")
        raise self.retry(exc=exc) from exc


def _scan_records(redis, prefix: str, fields: list[str]) -> list[dict]:
    """Best-effort scan of ``prefix*`` JSON records with the given fields."""
    records = []
    try:
        for key in redis.keys(f"{prefix}*"):
            raw = redis.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            if isinstance(data, dict):
                records.append({f: data.get(f) for f in fields})
    except Exception:
        return records
    return records
