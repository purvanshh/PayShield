import hashlib
import os

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from api.auth import AuthManager, auth_manager
    from api.rbac import RBACEnforcer, require_permission
    _auth_available = True
except ImportError:
    _auth_available = False
    AuthManager = None
    auth_manager = None
    RBACEnforcer = None
    require_permission = None

from store import RedisClient

bearer_scheme = HTTPBearer(auto_error=False)

API_KEY_RATE_LIMIT = int(os.getenv("RATE_LIMIT_API_KEY_PER_HOUR", "1000"))
USER_RATE_LIMIT = int(os.getenv("RATE_LIMIT_USER_PER_HOUR", "1000"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "3600"))


async def get_redis(request: Request) -> RedisClient:
    resources = getattr(request.app.state, "resources", {})
    redis = resources.get("redis")
    if redis is None:
        redis = RedisClient()
    return redis


async def _enforce_rate_limit(redis, identity: str, limit: int) -> None:
    if redis is None:
        return
    key = f"ratelimit:fixed:{identity}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, RATE_LIMIT_WINDOW_SECONDS)
    except Exception:
        return
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )


async def verify_api_key(
    x_api_key: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    redis: RedisClient = Depends(get_redis),
):
    if _auth_available and auth_manager is not None:
        auth = auth_manager
        principal = None
        if x_api_key:
            principal = auth.verify_api_key(x_api_key)
        if principal is None and credentials is not None:
            principal = auth.verify_access_token(credentials.credentials)
        if principal is None:
            raise HTTPException(status_code=403, detail="Invalid API Key or token")
        if x_api_key:
            identity = hashlib.sha256(x_api_key.encode()).hexdigest()[:32]
            await _enforce_rate_limit(redis, f"apikey:{identity}", API_KEY_RATE_LIMIT)
        elif credentials is not None:
            await _enforce_rate_limit(redis, f"user:{principal.user_id}", USER_RATE_LIMIT)
        return principal
    fallback_key = os.getenv("PAYSHIELD_DEV_API_KEY", "payshield-dev-key-2026")
    if x_api_key != fallback_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    if x_api_key:
        identity = hashlib.sha256(x_api_key.encode()).hexdigest()[:32]
        await _enforce_rate_limit(redis, f"apikey:{identity}", API_KEY_RATE_LIMIT)


async def get_statistical_filter(request: Request):
    resources = getattr(request.app.state, "resources", {})
    return resources.get("statistical_filter")


async def get_ensemble(request: Request):
    resources = getattr(request.app.state, "resources", {})
    return resources.get("ensemble")
