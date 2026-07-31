import logging
from functools import wraps
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None

from api.auth import AuthManager, UserPrincipal

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None),
) -> Any:
    if credentials is None and x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing authentication credentials")
    auth = AuthManager()
    principal = auth.verify_access_token(credentials.credentials) if credentials else None
    if principal is None:
        principal = auth.verify_api_key((credentials.credentials if credentials else x_api_key) or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return principal


class RBACEnforcer:
    def __init__(self, config_path: str = "configs/rbac.yaml"):
        self._matrix: dict[str, list[str]] = {}
        self._load_config(config_path)

    def _load_config(self, path: str):
        if yaml is None:
            self._matrix = {
                "analyst": ["score:read", "investigation:read", "feedback:write"],
                "admin": ["score:read", "investigation:read", "feedback:write",
                          "rule:write", "model:promote", "agent:manage"],
                "system": ["score:write", "metrics:read", "health:read"],
            }
            return
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._matrix = data.get("roles", self._matrix)
        except FileNotFoundError:
            self._matrix = {
                "analyst": ["score:read", "investigation:read", "feedback:write"],
                "admin": ["score:read", "investigation:read", "feedback:write",
                          "rule:write", "model:promote", "agent:manage"],
                "system": ["score:write", "metrics:read", "health:read"],
            }

    def has_permission(self, principal: Any, resource: str, action: str) -> bool:
        permission = f"{resource}:{action}"
        allowed = self._matrix.get(principal.role, [])
        return permission in allowed

    def require_permission(self, resource: str, action: str):
        def dependency(principal: Any = Depends(get_current_user)):
            if not self.has_permission(principal, resource, action):
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {resource}:{action} requires role with access",
                )
            return principal
        return dependency


ENFORCER = RBACEnforcer()


def require_permission(resource: str, action: str):
    return ENFORCER.require_permission(resource, action)
