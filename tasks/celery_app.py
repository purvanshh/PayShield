import os

from celery import Celery

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/1")

celery_app = Celery("payshield", include=[
    "tasks.investigation_task",
    "tasks.reflection_task",
    "tasks.compliance_task",
])

celery_app.config_from_object(
    {
        "broker_url": CELERY_BROKER_URL,
        "result_backend": os.getenv("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/2"),
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "task_track_started": True,
        "task_time_limit": 120,
        "task_soft_time_limit": 90,
        "worker_prefetch_multiplier": 1,
        "task_queues": {
            "investigation": {"exchange": "investigation", "routing_key": "investigation"},
            "default": {},
        },
        "task_default_queue": "default",
        "task_routes": {
            "tasks.investigation_task.generate_investigation": {"queue": "investigation"},
        },
        "beat_schedule": {
            "nightly-reflection-analysis": {
                "task": "tasks.reflection_task.run_nightly_reflection",
                "schedule": 86400.0,
                "args": (24,),
            },
            "nightly-risk-suite-reflection": {
                "task": "tasks.reflection_task.run_risk_suite_reflection",
                "schedule": 86400.0,
            },
            "daily-pci-dss-check": {
                "task": "tasks.compliance_task.run_pci_dss_check",
                "schedule": 86400.0,
            },
            "weekly-rbi-check": {
                "task": "tasks.compliance_task.run_rbi_check",
                "schedule": 604800.0,
            },
            "monthly-eu-ai-act-check": {
                "task": "tasks.compliance_task.run_eu_ai_act_check",
                "schedule": 2592000.0,
            },
        },
    }
)

__all__ = ["celery_app"]
