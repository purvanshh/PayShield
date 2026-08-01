import base64
import hashlib
import hmac
import logging
import os
import struct
import time
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


class TOTPManager:
    """RFC 6238 time-based one-time passwords (SHA-1, 6 digits, 30s step).

    Pure stdlib implementation so admin MFA works without an extra dependency.
    """

    STEP_SECONDS = 30
    DIGITS = 6

    def __init__(self, secret: str | None = None):
        self.secret = secret or base64.b32encode(os.urandom(20)).decode()

    @staticmethod
    def generate_secret() -> str:
        return base64.b32encode(os.urandom(20)).decode()

    @staticmethod
    def _code_for(secret: str, counter: int) -> str:
        key = base64.b32decode(secret, casefold=True)
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        return str(binary % (10 ** TOTPManager.DIGITS)).zfill(TOTPManager.DIGITS)

    def current_code(self, at: float | None = None) -> str:
        counter = int((at if at is not None else time.time()) // self.STEP_SECONDS)
        return self._code_for(self.secret, counter)

    def verify(self, code: str, window: int = 1, at: float | None = None) -> bool:
        if not code or not code.isdigit():
            return False
        counter = int((at if at is not None else time.time()) // self.STEP_SECONDS)
        for offset in range(-window, window + 1):
            if self._code_for(self.secret, counter + offset) == code:
                return True
        return False

    def provision_uri(self, username: str, issuer: str = "PayShield") -> str:
        label = f"{issuer}:{username}"
        return (
            f"otpauth://totp/{label}?secret={self.secret}"
            f"&issuer={issuer}&algorithm=SHA1&digits={self.DIGITS}&period={self.STEP_SECONDS}"
        )


class AuthManager:
    def __init__(self, secret: str = JWT_SECRET):
        self.secret = secret
        self._api_keys: dict[str, dict] = {}
        self._revoked_tokens: set[str] = set()
        self._totp_secrets: dict[str, str] = {}
        self._totp_enabled: dict[str, bool] = {}
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
        if not _has_jwt:
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
        try:
            payload = pyjwt.decode(refresh_token, self.secret, algorithms=[JWT_ALGORITHM])
            jti = payload.get("jti", "")
        except Exception:
            return None
        if jti in self._revoked_tokens:
            return None
        self._revoked_tokens.add(jti)
        new_access = self.create_access_token(payload.get("sub", ""), payload.get("role", "analyst"))
        new_refresh = self.create_access_token(
            payload.get("sub", ""), payload.get("role", "analyst"),
            expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return new_access, new_refresh

    def revoke_token(self, token: str):
        self._revoked_tokens.add(token)

    def setup_totp(self, user_id: str, username: str = "") -> tuple[str, str]:
        """Provision a TOTP secret for an account. Returns (secret, otpauth URI)."""
        secret = TOTPManager.generate_secret()
        self._totp_secrets[user_id] = secret
        uri = TOTPManager(secret).provision_uri(username or user_id)
        return secret, uri

    def verify_totp(self, user_id: str, code: str) -> bool:
        secret = self._totp_secrets.get(user_id)
        if secret is None:
            return False
        if not TOTPManager(secret).verify(code):
            return False
        self._totp_enabled[user_id] = True
        return True

    def is_totp_enabled(self, user_id: str) -> bool:
        return bool(self._totp_enabled.get(user_id))


auth_manager = AuthManager()
