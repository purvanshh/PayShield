import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import REFRESH_TOKEN_EXPIRE_DAYS, auth_manager
from api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[], tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TotpSetupRequest(BaseModel):
    username: str


class TotpVerifyRequest(BaseModel):
    username: str
    code: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str
    token_type: str = "bearer"
    expires_in: int = 1800


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpVerifyResponse(BaseModel):
    verified: bool
    enabled: bool


def _validate_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "admin")
    return username == expected_user and password == expected_pass


def _require_admin(principal):
    if principal is None or principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return principal


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not _validate_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = auth_manager.create_access_token(body.username, role="admin")
    refresh_token = auth_manager.create_access_token(
        body.username, role="admin",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role="admin",
        expires_in=1800,
    )


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest):
    try:
        new_access, new_refresh = auth_manager.refresh_access_token(body.refresh_token)
    except Exception as e:
        logger.warning(f"Token refresh failed: {e}")
        new_access, new_refresh = None, None
    if new_access is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return LoginResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        role="admin",
        expires_in=1800,
    )


@router.post("/auth/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(body: TotpSetupRequest, principal=Depends(verify_api_key)):
    _require_admin(principal)
    secret, uri = auth_manager.setup_totp(body.username, username=body.username)
    logger.info(f"totp_setup_complete user={body.username}")
    return TotpSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/auth/totp/verify", response_model=TotpVerifyResponse)
async def totp_verify(body: TotpVerifyRequest, principal=Depends(verify_api_key)):
    _require_admin(principal)
    verified = auth_manager.verify_totp(body.username, body.code)
    return TotpVerifyResponse(verified=verified, enabled=auth_manager.is_totp_enabled(body.username))
