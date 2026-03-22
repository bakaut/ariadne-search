from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from kb_worker.dependencies import get_ingest_service
from kb_worker.services.ingest import DummyIngestService

router = APIRouter(prefix="/dummy", tags=["dummy"])


@router.post("/documents")
def upload_document(
    file: UploadFile = File(...),
    relative_path: str | None = Form(default=None),
    ingest_service: DummyIngestService = Depends(get_ingest_service),
) -> dict[str, object]:
    try:
        return ingest_service.ingest_upload(file=file, relative_path=relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
