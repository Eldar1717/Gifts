"""GIFT MARKET — FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.security import AuthError
from app.db.base import Base
from app.db.session import engine
from app.services.maintenance import maintenance_loop

configure_logging()
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.is_production:
        # Local development and the test-suite create tables directly.
        # Production uses `alembic upgrade head` (see docker-compose / render.yaml).
        Base.metadata.create_all(bind=engine)
    logger.info(
        "app.startup", extra={"event": f"env={settings.env} db={engine.dialect.name}"}
    )
    stop_event = asyncio.Event()
    worker = asyncio.create_task(maintenance_loop(stop_event))
    app.state.stop_event = stop_event
    app.state.worker = worker
    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(worker, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            worker.cancel()
        logger.info("app.shutdown")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Маркетплейс цифровых коллекционных подарков в Telegram.\n\n"
        "Все финансовые расчёты выполняются на сервере. Покупка подтверждается только "
        "через webhook Telegram (`successful_payment`), право собственности передаётся "
        "в одной транзакции с записью в финансовый журнал."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Dev-Telegram-Id", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)

if settings.trusted_host_list and settings.trusted_host_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request.failed", extra={"path": request.url.path})
            request_id_ctx.reset(token)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        # The API only returns JSON: it is never framed. The Mini App itself is
        # served by the frontend host (no X-Frame-Options there, so Telegram Web
        # can embed it).
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api") and response.status_code >= 500:
            logger.error(
                "request.server_error",
                extra={
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        elif duration_ms > 2000:
            logger.warning(
                "request.slow",
                extra={"path": request.url.path, "duration_ms": duration_ms},
            )
        request_id_ctx.reset(token)
        return response


app.add_middleware(RequestContextMiddleware)


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "auth_required": True},
        headers={"WWW-Authenticate": "Telegram"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
    logger.exception("unhandled_error", extra={"path": request.url.path})
    message = "Внутренняя ошибка сервера" if settings.is_production else f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": message})


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
