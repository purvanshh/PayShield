import json
import logging

from store.redis_client import create_redis
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_nightly_reflection(self, period_hours: int = 24):
    logger.info(f"Starting nightly reflection analysis for last {period_hours}h")
    try:
        from agents.reflection_agent import ReflectionAgent
        from agents.base import AgentConfig

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
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=600)
def sync_reflection_weights(self):
    logger.info("Syncing reflection weights from analyst feedback...")
    try:
        from agents.reflection_agent import ReflectionAgent
        from agents.base import AgentConfig

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
        raise self.retry(exc=exc)
