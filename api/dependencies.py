from fastapi import Header, HTTPException, Request
from store.redis_client import RedisClient
from store.feature_store import FeatureStore
from store.graph_db import GraphDB
from engine.ensemble import EnsembleScorer


_api_key = "payshield-dev-key-2026"


async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != _api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")


async def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


async def get_feature_store(request: Request) -> FeatureStore:
    return request.app.state.feature_store


async def get_ensemble(request: Request) -> EnsembleScorer:
    return request.app.state.ensemble


async def get_graph_db(request: Request) -> GraphDB:
    return request.app.state.graph_db
