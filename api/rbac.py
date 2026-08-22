import logging
from typing import Any

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None

try:
    from api.auth import auth_manager as _auth_manager

    _auth_available = True
except ImportError:
    _auth_available = False
    _auth_manager = None

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None),
) -> Any:
    if credentials is None and x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing authentication credentials")
    if not _auth_available or _auth_manager is None:
        raise HTTPException(status_code=401, detail="Authentication not configured")
    principal = _auth_manager.verify_access_token(credentials.credentials) if credentials else None
    if principal is None:
        principal = _auth_manager.verify_api_key((credentials.credentials if credentials else x_api_key) or "")
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
                "analyst": ["score:read", "investigation:read", "feedback:write",
                            "chargeback:read", "return_risk:read"],
                "admin": ["score:read", "investigation:read", "feedback:write",
                          "rule:write", "model:promote", "agent:manage",
                          "chargeback:read", "chargeback:write", "chargeback:admin",
                          "return_risk:read"],
                "system": ["score:write", "metrics:read", "health:read",
                           "chargeback:read", "chargeback:write", "return_risk:read"],
            }
            return
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._matrix = data.get("roles", self._matrix)
        except FileNotFoundError:
            self._matrix = {
                "analyst": ["score:read", "investigation:read", "feedback:write",
                            "chargeback:read", "return_risk:read"],
                "admin": ["score:read", "investigation:read", "feedback:write",
                          "rule:write", "model:promote", "agent:manage",
                          "chargeback:read", "chargeback:write", "chargeback:admin",
                          "return_risk:read"],
                "system": ["score:write", "metrics:read", "health:read",
                           "chargeback:read", "chargeback:write", "return_risk:read"],
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
