from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kb_api.config import Settings
from kb_api.logging import setup_logging
from kb_api.routers.health import router as health_router
from kb_api.routers.search import router as search_router
from kb_api.services.search_service import SearchService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    setup_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = SearchService(cfg)
        app.state.search_service = service
        try:
            yield
        finally:
            service.close()

    app = FastAPI(
        title=cfg.api_title,
        version=cfg.api_version,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(search_router)
    return app
