from tasks.celery_app import celery_app
from tasks.investigation_task import generate_investigation

__all__ = ["celery_app", "generate_investigation"]
