import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest

from api.routes import score, investigation, health, feedback
from observability.logging_config import configure_logging
from store.redis_client import RedisClient
from store.feature_store import FeatureStore
from store.graph_db import GraphDB
from engine.ensemble import EnsembleScorer

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    redis = RedisClient()
    app.state.redis = redis
    app.state.feature_store = FeatureStore(redis)
    app.state.graph_db = GraphDB()
    app.state.ensemble = EnsembleScorer(app.state.graph_db)
    logger.info("payshield_started", redis_ok=redis.health_check())
    yield
    redis.close()
    logger.info("payshield_stopped")


app = FastAPI(
    title="PayShield",
    description="Real-Time UPI Fraud Detection & Graph-Powered Investigation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def latency_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    response.headers["X-Latency-Ms"] = f"{elapsed:.2f}"
    return response


app.include_router(health.router, tags=["health"])
app.include_router(score.router, prefix="/v1", tags=["score"])
app.include_router(investigation.router, prefix="/v1", tags=["investigation"])
app.include_router(feedback.router, prefix="/v1", tags=["feedback"])
