import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.lifespan import lifespan_manager
from api.middleware import (
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
)
from api.security import rate_limiter

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="PayShield Fraud Detection API",
        description="Real-Time UPI Fraud Detection, Graph-Powered Investigation & Multi-Agent Orchestration",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan_manager,
    )

    allowed_origins = [
        origin.strip() for origin in os.getenv("FRONTEND_URL", "http://localhost:3000").split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    _register_exception_handlers(app)
    _include_routers(app)

    return app


def _register_exception_handlers(app: FastAPI):
    from api.exceptions import register_exception_handlers
    try:
        register_exception_handlers(app)
    except Exception as e:
        logger.warning(f"exception_handlers_skipped: {e}")

    @app.middleware("http")
    async def rate_limit_middleware(request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}"
        if not rate_limiter.is_allowed(key, limit=200, window_seconds=60):
            from starlette.responses import JSONResponse
            return JSONResponse(status_code=429, content={"error": "too_many_requests", "detail": "Rate limit exceeded"})
        return await call_next(request)


def _include_routers(app: FastAPI):
    try:
        from api.routes.health import router as health_router
        app.include_router(health_router, tags=["health"])
    except Exception as e:
        logger.warning(f"health_router_skipped: {e}")

    try:
        from api.routes.auth import router as auth_router
        app.include_router(auth_router, prefix="/v1", tags=["auth"])
    except Exception as e:
        logger.warning(f"auth_router_skipped: {e}")

    try:
        from api.routes.score import router as score_router
        app.include_router(score_router, prefix="/v1", tags=["score"])
    except Exception as e:
        logger.warning(f"score_router_skipped: {e}")

    try:
        from api.routes.metrics import router as metrics_router
        app.include_router(metrics_router, tags=["metrics"])
    except Exception as e:
        logger.warning(f"metrics_router_skipped: {e}")

    try:
        from api.routes.admin import router as admin_router
        app.include_router(admin_router, prefix="/admin", tags=["admin"])
    except Exception as e:
        logger.warning(f"admin_router_skipped: {e}")

    try:
        from api.routes.experiments import router as experiments_router
        app.include_router(experiments_router, tags=["experiments"])
    except Exception as e:
        logger.warning(f"experiments_router_skipped: {e}")

    try:
        from api.routes.chargeback_webhook import router as chargeback_webhook_router
        app.include_router(chargeback_webhook_router, tags=["webhooks"])
    except Exception as e:
        logger.warning(f"chargeback_webhook_router_skipped: {e}")

    try:
        from api.routes.chargeback import router as chargeback_router
        app.include_router(chargeback_router, prefix="/v1", tags=["chargeback"])
    except Exception as e:
        logger.warning(f"chargeback_router_skipped: {e}")

    try:
        from api.routes.return_risk import router as return_risk_router
        app.include_router(return_risk_router, prefix="/v1", tags=["return-risk"])
    except Exception as e:
        logger.warning(f"return_risk_router_skipped: {e}")

    try:
        from integrations.razorpay_webhook_handler import router as razorpay_webhook_router
        app.include_router(razorpay_webhook_router, tags=["webhooks"])
    except Exception as e:
        logger.warning(f"razorpay_webhook_router_skipped: {e}")

    try:
        from api.routes.meta import router as meta_router
        app.include_router(meta_router, tags=["meta"])
    except Exception as e:
        logger.warning(f"meta_router_skipped: {e}")


app = create_app()
