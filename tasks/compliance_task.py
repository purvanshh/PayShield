import logging

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_pci_dss_check(self):
    logger.info("Running scheduled PCI-DSS compliance check...")
    try:
        from compliance.pci_dss import PCIDSSComplianceChecker
        result = PCIDSSComplianceChecker().generate_report()
        logger.info(f"PCI-DSS check complete: score={result['score']}, passed={result['passed']}")
        return result
    except Exception as exc:
        logger.error(f"PCI-DSS check failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_rbi_check(self):
    logger.info("Running scheduled RBI compliance check...")
    try:
        from compliance.rbi_localization import RBILocalizationChecker
        result = RBILocalizationChecker().generate_report()
        logger.info(f"RBI check complete: score={result['score']}, passed={result['passed']}")
        return result
    except Exception as exc:
        logger.error(f"RBI check failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_eu_ai_act_check(self):
    logger.info("Running scheduled EU AI Act compliance check...")
    try:
        from compliance.eu_ai_act import EUAiActComplianceChecker
        result = EUAiActComplianceChecker().generate_report()
        logger.info(f"EU AI Act check complete: score={result['score']}, passed={result['passed']}")
        return result
    except Exception as exc:
        logger.error(f"EU AI Act check failed: {exc}")
        raise self.retry(exc=exc)
