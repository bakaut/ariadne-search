from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from kb_worker.dependencies import get_ingest_service
from kb_worker.services.ingest import DummyIngestService

router = APIRouter(prefix="/dummy", tags=["dummy"])

SUPPORTED_TYPES_DOC = (
    "Supported extensions include text/config (`.md`, `.txt`, `.json`, `.yaml`, `.toml`), "
    "documents (`.pdf`, `.docx`, `.pptx`, `.xlsx`), code (`.py`, `.js`, `.ts`, `.sql`, `.sh`), "
    "images (`.jpg`, `.png`, `.webp`, `.tif`) and diagrams (`.svg`, `.drawio`, `.puml`, `.mmd`)."
)


class UploadDocumentResponse(BaseModel):
    status: Literal["indexed", "unchanged"] = Field(
        description=(
            "`indexed` means ETL ran successfully, including forced reindex requests; "
            "`unchanged` means the same checksum was already indexed and force was not requested."
        )
    )
    source_path: str = Field(description="Absolute path inside the worker container knowledge root.")
    checksum: str = Field(description="SHA-256 checksum of the uploaded file.")
    size_bytes: int = Field(description="Uploaded file size in bytes.", ge=1)


class ErrorResponse(BaseModel):
    detail: str


@router.post(
    "/documents",
    response_model=UploadDocumentResponse,
    summary="Upload and index a document",
    description=(
        "Saves the multipart file into the first configured knowledge root and runs synchronous "
        "indexing. Set `force=true` to bypass unchanged-check skipping. "
        "`relative_path` must stay inside the knowledge root. "
        + SUPPORTED_TYPES_DOC
    ),
    responses={
        200: {
            "description": "The file was accepted and either indexed or detected as unchanged.",
            "content": {
                "application/json": {
                    "examples": {
                        "indexed": {
                            "summary": "Fresh upload",
                            "value": {
                                "status": "indexed",
                                "source_path": "/data/knowledge/uploads/README.md",
                                "checksum": "3b8f5c1b6d8b0c5d2f4f4f29f8ac7a6af6c65a6da0c6c0f1d0fcb2f1a6b2d3c4",
                                "size_bytes": 1532,
                            },
                        },
                        "forced": {
                            "summary": "Forced reindex",
                            "value": {
                                "status": "indexed",
                                "source_path": "/data/knowledge/uploads/README.md",
                                "checksum": "3b8f5c1b6d8b0c5d2f4f4f29f8ac7a6af6c65a6da0c6c0f1d0fcb2f1a6b2d3c4",
                                "size_bytes": 1532,
                            },
                        },
                        "unchanged": {
                            "summary": "Idempotent re-upload",
                            "value": {
                                "status": "unchanged",
                                "source_path": "/data/knowledge/uploads/README.md",
                                "checksum": "3b8f5c1b6d8b0c5d2f4f4f29f8ac7a6af6c65a6da0c6c0f1d0fcb2f1a6b2d3c4",
                                "size_bytes": 1532,
                            },
                        },
                    }
                }
            },
        },
        400: {
            "model": ErrorResponse,
            "description": "Validation error such as unsupported extension, absolute path, or path traversal.",
        },
        500: {
            "model": ErrorResponse,
            "description": "The file was saved but indexing failed.",
        },
    },
)
def upload_document(
    file: Annotated[
        UploadFile,
        File(
            ...,
            description=(
                "Multipart file to store and index. "
                + SUPPORTED_TYPES_DOC
            ),
        ),
    ],
    relative_path: Annotated[
        str | None,
        Form(
            description=(
                "Optional relative destination path under the knowledge root, for example "
                "`uploads/specs/readme.md`. Absolute paths and `..` segments are rejected."
            ),
            examples=["uploads/README.md", "arch/overview.puml"],
        ),
    ] = None,
    force: Annotated[
        bool,
        Form(
            description=(
                "When true, run ETL even if the same checksum is already indexed for the same path."
            )
        ),
    ] = False,
    ingest_service: DummyIngestService = Depends(get_ingest_service),
) -> UploadDocumentResponse:
    try:
        return ingest_service.ingest_upload(file=file, relative_path=relative_path, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
