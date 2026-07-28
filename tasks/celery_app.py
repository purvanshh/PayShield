from celery import Celery

celery_app = Celery("payshield")

celery_app.config_from_object(
    {
        "broker_url": "redis://localhost:6379/0",
        "result_backend": "redis://localhost:6379/0",
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
