import os

from fastapi import Header, HTTPException, Request

try:
    from api.auth import AuthManager
    from api.rbac import RBACEnforcer, require_permission
    _auth_available = True
except ImportError:
    _auth_available = False
    AuthManager = None
    RBACEnforcer = None
    require_permission = None

from store import RedisClient


async def verify_api_key(x_api_key: str = Header(...)):
    if _auth_available and AuthManager is not None:
        auth = AuthManager()
        principal = auth.verify_api_key(x_api_key)
        if principal is None:
            raise HTTPException(status_code=403, detail="Invalid API Key")
        return principal
    fallback_key = os.getenv("PAYSHIELD_DEV_API_KEY", "payshield-dev-key-2026")
    if x_api_key != fallback_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")


async def get_redis(request: Request) -> RedisClient:
    resources = getattr(request.app.state, "resources", {})
    redis = resources.get("redis")
    if redis is None:
        redis = RedisClient()
    return redis


async def get_statistical_filter(request: Request):
    resources = getattr(request.app.state, "resources", {})
    return resources.get("statistical_filter")


async def get_ensemble(request: Request):
    resources = getattr(request.app.state, "resources", {})
    return resources.get("ensemble")
