import logging

from fastapi import APIRouter, Depends
from starlette.responses import Response

from api.dependencies import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(redis=Depends(get_redis)):
    checks: dict[str, str] = {}

    try:
        redis_alive = await redis.ping()
        checks["redis"] = "up" if redis_alive else "down"
    except Exception:
        checks["redis"] = "down"

    try:
        from store.neo4j_client import Neo4jGraphDB
        neo4j = Neo4jGraphDB()
        checks["neo4j"] = "up"
    except Exception:
        checks["neo4j"] = "down"

    try:
        from llm.client import OllamaClient
        from llm.config import OllamaConfig
        ollama = OllamaClient(OllamaConfig())
        healthy = await ollama.health()
        checks["ollama"] = "up" if healthy else "down"
    except Exception:
        checks["ollama"] = "down"

    try:
        from importlib.metadata import version
        checks["celery"] = "available"
    except Exception:
        checks["celery"] = "unknown"

    critical = all(v == "up" for k, v in checks.items() if k in ("redis",))
    overall = "healthy" if critical else "degraded" if any(v == "up" for v in checks.values()) else "unhealthy"
    status_code = 200 if critical else 503

    from starlette.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(redis=Depends(get_redis)):
    try:
        redis_alive = await redis.ping()
        return {"status": "ready" if redis_alive else "not_ready"}
    except Exception:
        from starlette.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "not_ready"})
