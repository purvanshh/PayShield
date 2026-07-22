import json
from datetime import datetime

from celery import Celery

from llm.investigator import LLMInvestigator
from llm.cache import LLMCache
from store.redis_client import RedisClient
from observability.metrics import llm_queue_depth

celery_app = Celery(
    "payshield",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/1",
)

redis_client = RedisClient(db=1)
llm = LLMInvestigator()
cache = LLMCache(redis_client)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def run_investigation(self, txn_id: str, evidence: dict):
    cached = cache.get(evidence)
    if cached:
        result = json.loads(cached)
        result["txn_id"] = txn_id
        redis_client.set(f"investigation:{txn_id}", json.dumps(result), ttl=86400)
        return result

    try:
        result = llm.investigate(evidence)
        result["txn_id"] = txn_id
        result["generated_at"] = datetime.utcnow().isoformat()

        cache.set(evidence, json.dumps(result))
        redis_client.set(f"investigation:{txn_id}", json.dumps(result), ttl=86400)

        queue_depth = celery_app.control.inspect().active() or {}
        llm_queue_depth.set(sum(len(tasks) for tasks in queue_depth.values()))

        return result
    except Exception as exc:
        raise self.retry(exc=exc)
