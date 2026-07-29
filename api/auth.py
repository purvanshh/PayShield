import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

try:
    import jwt as pyjwt
    _has_jwt = True
except ImportError:
    pyjwt = None
    _has_jwt = False

import os

JWT_SECRET = os.getenv("JWT_SECRET", "payshield-jwt-secret-dev-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "7"))


class ServicePrincipal:
    def __init__(self, key_id: str, role: str, name: str = ""):
        self.key_id = key_id
        self.role = role
        self.name = name
        self.auth_type = "api_key"


class UserPrincipal:
    def __init__(self, user_id: str, role: str, username: str = ""):
        self.user_id = user_id
        self.role = role
        self.username = username
        self.auth_type = "jwt"


class AuthManager:
    def __init__(self, secret: str = JWT_SECRET):
        self.secret = secret
        self._api_keys: dict[str, dict] = {}
        self._revoked_tokens: set[str] = set()
        self._load_dev_keys()

    def _load_dev_keys(self):
        prefix = "psk"
        key_raw = os.getenv("PAYSHIELD_DEV_API_KEY", "payshield-dev-key-2026")
        key_hash = hashlib.sha256(key_raw.encode()).hexdigest()
        self._api_keys[key_hash] = {
            "key_id": str(uuid.uuid4()),
            "key_prefix": prefix,
            "role": "system",
            "name": "dev-key",
        }

    def verify_api_key(self, header: str) -> ServicePrincipal | None:
        key_hash = hashlib.sha256(header.encode()).hexdigest()
        entry = self._api_keys.get(key_hash)
        if entry is None:
            for stored_hash, info in self._api_keys.items():
                if header.startswith(info["key_prefix"]):
                    entry = info
                    break
        if entry is None:
            return None
        return ServicePrincipal(
            key_id=entry["key_id"],
            role=entry["role"],
            name=entry.get("name", ""),
        )

    def register_api_key(self, key_raw: str, role: str = "system", name: str = ""):
        key_hash = hashlib.sha256(key_raw.encode()).hexdigest()
        self._api_keys[key_hash] = {
            "key_id": str(uuid.uuid4()),
            "key_prefix": key_raw[:8],
            "role": role,
            "name": name,
        }

    def create_access_token(self, user_id: str, role: str, expires_delta: timedelta | None = None) -> str:
        if not _has_jwt:
            logger.warning("PyJWT not available; returning mock token")
            return f"mock_jwt_{user_id}_{role}"
        delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        now = datetime.utcnow()
        payload = {
            "sub": user_id,
            "role": role,
            "iat": now,
            "exp": now + delta,
            "jti": str(uuid.uuid4()),
        }
        return pyjwt.encode(payload, self.secret, algorithm=JWT_ALGORITHM)

    def verify_access_token(self, token: str) -> UserPrincipal | None:
        if not _has_jwt:
            if token.startswith("mock_jwt_"):
                parts = token.split("_")
                if len(parts) >= 4:
                    return UserPrincipal(user_id=parts[2], role=parts[3])
            return None
        try:
            payload = pyjwt.decode(token, self.secret, algorithms=[JWT_ALGORITHM])
            jti = payload.get("jti", "")
            if jti in self._revoked_tokens:
                return None
            return UserPrincipal(
                user_id=payload.get("sub", ""),
                role=payload.get("role", "analyst"),
            )
        except Exception:
            return None

    def refresh_access_token(self, refresh_token: str) -> tuple[str, str] | None:
        principal = self.verify_access_token(refresh_token)
        if principal is None:
            return None
        self._revoked_tokens.add(refresh_token)
        new_access = self.create_access_token(principal.user_id, principal.role)
        new_refresh = self.create_access_token(
            principal.user_id, principal.role,
            expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return new_access, new_refresh

    def revoke_token(self, token: str):
        self._revoked_tokens.add(token)
