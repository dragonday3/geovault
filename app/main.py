"""GeoVault application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import migrate
from app.config import Settings, get_settings
from app.database import create_pool
from app.routers import admin, auth, favourites, places, sharing, users
from app.schemas.places import Health
from app.security.rate_limit import LoginLimiter, RateLimiter
from app.security.upload_guard import UploadGuard
from app.services.photos import LocalPhotoStore, PhotoLimits

log = logging.getLogger("geovault")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    dsn = settings.database_url.get_secret_value()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        migrate.apply(dsn, settings.migrations_dir)
        app.state.pool = create_pool(dsn)
        app.state.pool.open(wait=True, timeout=30)
        try:
            yield
        finally:
            app.state.pool.close()

    app = FastAPI(
        title="GeoVault API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health(request: Request, response: Response):
        try:
            with request.app.state.pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return Health(status="ok", db="ok")
        except Exception:
            log.warning("health check: database unavailable")
            response.status_code = 503  # lets Docker/load balancers mark us unhealthy
            return Health(status="degraded", db="unavailable")

    app.state.settings = settings
    app.state.login_limiter = LoginLimiter()
    app.state.register_limiter = RateLimiter(limit=10, window_seconds=3600)
    app.state.share_limiter = RateLimiter(limit=30, window_seconds=3600)
    app.state.photo_limits = PhotoLimits()
    app.state.photo_store = LocalPhotoStore(settings.photo_dir)
    app.add_middleware(UploadGuard, max_bytes_getter=lambda: app.state.photo_limits.max_bytes)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 body echoes the submitted value ("input") back. For a
        # rejected password that would put the password in the response and any logs
        # that capture it. Return only where and why validation failed.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

    app.include_router(places.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(favourites.router)
    app.include_router(sharing.router)

    # Mounted last so /api/* and /docs take precedence over static files.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app
