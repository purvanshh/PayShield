import logging
import os
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.auth import AuthManager

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[], tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str
    token_type: str = "bearer"
    expires_in: int = 1800


def _validate_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "admin")
    return username == expected_user and password == expected_pass


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not _validate_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    auth = AuthManager()
    access_token = auth.create_access_token(body.username, role="admin")
    refresh_token = auth.create_access_token(
        body.username, role="admin",
        expires_delta=timedelta(days=30),
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role="admin",
        expires_in=1800,
    )


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest):
    auth = AuthManager()
    try:
        new_access, new_refresh = auth.refresh_access_token(body.refresh_token)
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
