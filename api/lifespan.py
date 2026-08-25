import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    logger.info("payshield_startup_begin")
    resources = {}

    try:
        from store import RedisClient
        redis = RedisClient()
        if await redis.ping():
            resources["redis"] = redis
            logger.info("redis_connected")
        else:
            logger.warning("redis_unavailable")
    except Exception as e:
        logger.warning(f"redis_connection_failed: {e}")
        resources["redis"] = None

    try:
        from ml.registry import ModelRegistry
        registry = ModelRegistry()
        model_path = registry.get_production_model()
        if model_path and model_path.exists():
            resources["model_path"] = model_path
            logger.info(f"gnn_model_loaded from {model_path}")
        else:
            logger.warning("no_production_model_found")
    except Exception as e:
        logger.warning(f"model_load_skipped: {e}")

    try:
        from llm.client import OllamaClient
        from llm.config import OllamaConfig
        ollama = OllamaClient(OllamaConfig())
        healthy = await ollama.health()
        if healthy:
            resources["ollama"] = ollama
            logger.info("ollama_healthy")
        else:
            logger.warning("ollama_unhealthy")
    except Exception as e:
        logger.warning(f"ollama_check_skipped: {e}")

    try:
        from store.neo4j_client import Neo4jGraphDB
        neo4j = Neo4jGraphDB()
        await neo4j.connect()
        await neo4j.initialize_schema()
        resources["neo4j"] = neo4j
        logger.info("neo4j_connected")
    except Exception as e:
        logger.warning(f"neo4j_connection_skipped: {e}")
        resources["neo4j"] = None

    try:
        from ml.inference import L2InferenceService
        model_path = resources.get("model_path")
        l2_service = L2InferenceService(model_path=model_path)
        l2_service.load_model()
        resources["l2_inference"] = l2_service
        logger.info(f"l2_inference_ready: {l2_service.is_ready} ({l2_service.load_error})")
    except Exception as e:
        logger.warning(f"l2_inference_skipped: {e}")

    try:
        from store.graph_db import NetworkXGraphDB
        resources["graph_db"] = NetworkXGraphDB()
        from store.graph_writer import GraphDBWriter
        resources["graph_writer"] = GraphDBWriter(
            neo4j=resources.get("neo4j"),
            networkx_db=resources.get("graph_db"),
            redis=resources.get("redis"),
        )
        logger.info("graph_writer_ready")
    except Exception as e:
        logger.warning(f"graph_writer_skipped: {e}")

    from engine.ensemble import EnsembleFusionEngine
    from engine.statistical_filter import StatisticalFilter
    resources["ensemble"] = EnsembleFusionEngine()
    resources["statistical_filter"] = StatisticalFilter()

    try:
        from api.websocket import AlertBroadcaster
        broadcaster = AlertBroadcaster(resources.get("redis"))
        resources["alert_broadcaster"] = broadcaster
        task = asyncio.create_task(broadcaster.listen_and_broadcast())
        resources["_broadcast_task"] = task
        logger.info("alert_broadcaster_started")
    except Exception as e:
        logger.warning(f"alert_broadcaster_skipped: {e}")

    try:
        from store.audit_log import async_audit_logger
        async_audit_logger.start()
        resources["audit_logger"] = async_audit_logger
        logger.info("audit_logger_started")
    except Exception as e:
        logger.warning(f"audit_logger_skipped: {e}")

    app.state.resources = resources

    # Live-agent heartbeats: instantiate the four production agents, attach the
    # Redis client and renew `agent:heartbeat:{id}` every 20s (TTL 60s) so
    # `GET /admin/agents/health` reports them RUNNING (<30s staleness rule).
    try:
        from agents.base import AgentConfig, BaseAgent  # noqa: F401 - imported for type clarity
        from agents.human_review_agent import HumanReviewAgent
        from agents.profile_agent import ProfileAgent
        from agents.reflection_agent import ReflectionAgent
        from agents.transaction_agent import TransactionAnalysisAgent

        live_agents = [
            TransactionAnalysisAgent(),
            ProfileAgent(),
            ReflectionAgent(),
            HumanReviewAgent(),
        ]
        for agent in live_agents:
            agent._heartbeat_redis = resources.get("redis")

        async def _heartbeat_loop():
            while True:
                for agent in live_agents:
                    await agent.touch_heartbeat()
                await asyncio.sleep(20)

        resources["_heartbeat_task"] = asyncio.create_task(_heartbeat_loop())
        logger.info("agent_heartbeats_started")
    except Exception as e:
        logger.warning(f"agent_heartbeats_skipped: {e}")

    logger.info("payshield_startup_complete")
    yield

    logger.info("payshield_shutdown_begin")
    task = resources.get("_heartbeat_task")
    if task:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # nosec B110 - shutdown best-effort
            pass
    if resources.get("audit_logger"):
        try:
            await resources["audit_logger"].stop()
        except Exception:
            pass
    if resources.get("redis"):
        await resources["redis"].close()
    if resources.get("neo4j"):
        try:
            resources["neo4j"].close()
        except Exception:
            pass
    logger.info("payshield_shutdown_complete")
