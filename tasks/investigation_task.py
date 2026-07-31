import json
import logging
from datetime import datetime

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

try:
    from llm.client import OllamaClient
    from llm.config import OllamaConfig
    from llm.prompt_builder import PromptBuilder
    from llm.evidence import EvidenceCollector
    from llm.parser import NarrativeParser, FallbackGenerator
except ImportError:
    OllamaClient = None
    PromptBuilder = None
    EvidenceCollector = None
    NarrativeParser = None

try:
    from infrastructure.redis_bridge import create_sync_redis
except ImportError:
    from store.sync_redis import SyncRedisClient

    def create_sync_redis():
        import os
        return SyncRedisClient(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
        )


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="investigation")
def generate_investigation(self, txn_id: str, ensemble_result_json: str):
    try:
        from llm.client import OllamaClient
        from llm.prompt_builder import PromptBuilder
        from llm.evidence import EvidenceCollector
        from llm.parser import NarrativeParser, FallbackGenerator

        ensemble_data = json.loads(ensemble_result_json)
        collector = EvidenceCollector()
        builder = PromptBuilder()
        parser = NarrativeParser()
        config = OllamaConfig()
        client = OllamaClient(config)

        context = collector.collect(txn_id, ensemble_result=_dict_to_ensemble(ensemble_data))
        prompt = build_context_prompt(builder, context)
        healthy = client.health_sync()
        if healthy:
            raw_output = client.generate_sync(prompt, max_tokens=512, temperature=0.1)
            report = parser.parse(
                raw_output, txn_id=txn_id,
                expected_action=ensemble_data.get("decision", "ALLOW"),
            )
        else:
            logger.warning("Ollama not healthy; using fallback")
            fallback = FallbackGenerator()
            report = fallback.generate(context)
        report_dict = report.to_dict()

        try:
            result = {
                "status": "success",
                "txn_id": txn_id,
                "report": report_dict,
                "generated_at": datetime.utcnow().isoformat(),
            }
            redis = create_sync_redis()
            ok = redis.set(f"investigation:{txn_id}", json.dumps(result), ttl=86400)
            logger.info(f"Investigation stored for {txn_id}: {ok}")
        except Exception as e:
            logger.error(f"Investigation store failed for {txn_id}: {e}", exc_info=True)

        logger.info(f"Investigation complete for {txn_id}: {report_dict['fraud_type']}/{report_dict['confidence']}")
        return {"status": "success", "txn_id": txn_id, "report": report_dict}

    except Exception as exc:
        logger.error(f"Investigation task failed for {txn_id}: {exc}", exc_info=True)
        try:
            self.retry(exc=exc)
        except Exception:
            return {"status": "failed", "txn_id": txn_id, "error": str(exc)}


def build_context_prompt(builder, context):
    evidence_list = [
        {"type": e.type, "description": e.description, "severity": str(e.severity)}
        for e in context.evidence_items
    ]
    shap_list = [
        {"name": s.name, "value": s.value, "shap_value": s.shap_value}
        for s in context.shap_features
    ]
    graph_list = [
        {"type": n.type, "id": n.id, "importance": n.importance}
        for n in context.graph_nodes
    ]
    return builder.build_narrative_prompt(evidence_list, shap_list, graph_list)


def _dict_to_ensemble(d: dict):
    L1 = type("L1Result", (), {
        "decision": d.get("layer1_decision", "ALLOW"),
        "confidence": d.get("layer1_confidence", 0.0),
        "triggered_rules": d.get("triggered_rules", []),
    })()

    L2 = type("L2Result", (), {
        "fraud_probability": d.get("layer2_probability", 0.0),
        "source": d.get("layer2_source", "L2_GNN"),
        "graph_features": d.get("graph_features", {}),
    })()

    return type("EnsembleResult", (), {
        "decision": d.get("decision", "ALLOW"),
        "confidence": d.get("confidence", 0.0),
        "layer1_result": L1,
        "layer2_result": L2,
    })()
