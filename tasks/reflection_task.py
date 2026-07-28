import logging

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
        return report.to_dict()
    except Exception as exc:
        logger.error(f"Nightly reflection failed: {exc}")
        raise self.retry(exc=exc)
