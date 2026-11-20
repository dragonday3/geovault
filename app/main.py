"""GeoVault application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app import migrate
from app.config import Settings, get_settings
from app.database import create_pool
from app.routers import places
from app.schemas.places import Health

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

    app.include_router(places.router)

    # Mounted last so /api/* and /docs take precedence over static files.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app
