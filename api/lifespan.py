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
        from store.redis_client import RedisClient
        redis = RedisClient()
        if redis.health_check():
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
        model_path = registry.get_production_path()
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
        resources["neo4j"] = neo4j
        logger.info("neo4j_connected")
    except Exception as e:
        logger.warning(f"neo4j_connection_skipped: {e}")

    from engine.ensemble import EnsembleFusionEngine
    from engine.statistical_filter import StatisticalFilter
    resources["ensemble"] = EnsembleFusionEngine()
    resources["statistical_filter"] = StatisticalFilter()

    app.state.resources = resources
    logger.info("payshield_startup_complete")
    yield

    logger.info("payshield_shutdown_begin")
    if resources.get("redis"):
        resources["redis"].close()
    if resources.get("neo4j"):
        try:
            resources["neo4j"].close()
        except Exception:
            pass
    logger.info("payshield_shutdown_complete")
