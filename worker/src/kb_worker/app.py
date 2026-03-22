from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kb_worker.config import Settings
from kb_worker.logging import setup_logging
from kb_worker.routers.dummy import router as dummy_router
from kb_worker.routers.health import router as health_router
from kb_worker.services.ingest import DummyIngestService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    setup_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ingest_service = DummyIngestService(cfg)
        yield

    app = FastAPI(
        title="kb-worker dummy api",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(dummy_router)
    return app
