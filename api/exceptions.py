import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.middleware import get_current_request_id

logger = logging.getLogger(__name__)


class PayShieldException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: str = ""):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class RedisUnavailableError(PayShieldException):
    def __init__(self, detail: str = "Redis service unavailable"):
        super().__init__(status_code=503, detail=detail, error_code="REDIS_UNAVAILABLE")


class AuthenticationError(PayShieldException):
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status_code=401, detail=detail, error_code="AUTH_FAILED")


class AuthorizationError(PayShieldException):
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(status_code=403, detail=detail, error_code="FORBIDDEN")


class ModelUnavailableError(PayShieldException):
    def __init__(self, detail: str = "GNN model not loaded"):
        super().__init__(status_code=503, detail=detail, error_code="MODEL_UNAVAILABLE")


class BatchSizeExceededError(PayShieldException):
    def __init__(self, detail: str = "Batch size exceeds maximum of 100"):
        super().__init__(status_code=400, detail=detail, error_code="BATCH_SIZE_EXCEEDED")


def register_exception_handlers(app):
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "VALIDATION_ERROR",
                "detail": exc.errors(),
                "request_id": get_current_request_id(),
            },
        )

    @app.exception_handler(PayShieldException)
    async def payshield_exception_handler(request: Request, exc: PayShieldException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code or "PAYSHIELD_ERROR",
                "detail": exc.detail,
                "request_id": get_current_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "detail": "An internal error occurred",
                "request_id": get_current_request_id(),
            },
        )
