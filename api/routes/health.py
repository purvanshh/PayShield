from fastapi import APIRouter, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from api.dependencies import get_redis
from store.redis_client import RedisClient

router = APIRouter()


@router.get("/health")
async def health(redis: RedisClient = Depends(get_redis)):
    redis_ok = redis.health_check()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": "up" if redis_ok else "down",
    }


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
