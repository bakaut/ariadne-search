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
        summary="Worker-side upload and indexing API for local knowledge files.",
        description=(
            "Use this API to upload a single file into the first configured knowledge root and "
            "run synchronous ETL/indexing for quick manual testing. Swagger UI is intended for "
            "basic validation of accepted file types, relative paths, and indexing responses."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "health",
                "description": "Basic liveness probes for the worker dummy API.",
            },
            {
                "name": "dummy",
                "description": (
                    "Manual upload endpoint for ad hoc ETL/indexing tests. The request is multipart "
                    "form data with a required file, an optional relative_path, and an optional force flag."
                ),
            },
        ],
    )
    app.include_router(health_router)
    app.include_router(dummy_router)
    return app
