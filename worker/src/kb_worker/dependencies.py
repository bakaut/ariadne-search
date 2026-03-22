from __future__ import annotations

from fastapi import Request

from kb_worker.services.ingest import DummyIngestService


def get_ingest_service(request: Request) -> DummyIngestService:
    return request.app.state.ingest_service
