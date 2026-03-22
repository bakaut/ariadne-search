from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Protocol

from kb_worker.config import Settings
from kb_worker.models import FileRecord
from kb_worker.pipeline import ETLPipeline
from kb_worker.services.scanner import FileScanner


class UploadedDocument(Protocol):
    filename: str | None
    file: BinaryIO


class DummyIngestService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ingest_upload(self, file: UploadedDocument, relative_path: str | None = None) -> dict[str, object]:
        target_path = self._target_path(relative_path=relative_path, filename=file.filename)
        payload = file.file.read()
        if not payload:
            raise ValueError("Uploaded file is empty")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)

        file_record = self._build_file_record(target_path)
        pipeline = ETLPipeline(self.settings)
        try:
            changed = pipeline.postgres.has_changed(file_record)
            indexed = pipeline.process_file(file_record)
        finally:
            pipeline.close()

        if not changed:
            status = "unchanged"
        elif indexed:
            status = "indexed"
        else:
            raise RuntimeError("Worker failed to index uploaded document")

        return {
            "status": status,
            "source_path": str(target_path),
            "checksum": file_record.checksum,
            "size_bytes": file_record.size_bytes,
        }

    def _target_path(self, relative_path: str | None, filename: str | None) -> Path:
        if not self.settings.source_roots:
            raise ValueError("KB_SOURCE_ROOTS is empty")

        raw_path = relative_path or filename
        if not raw_path:
            raise ValueError("relative_path or uploaded filename is required")

        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ValueError("Only relative paths are allowed")

        parts = [part for part in candidate.parts if part not in ("", ".")]
        if not parts:
            raise ValueError("relative_path cannot be empty")
        if ".." in parts:
            raise ValueError("relative_path cannot escape the knowledge root")

        root = self.settings.source_roots[0]
        root.mkdir(parents=True, exist_ok=True)
        target_path = (root / Path(*parts)).resolve()
        root_path = root.resolve()
        try:
            target_path.relative_to(root_path)
        except ValueError as exc:
            raise ValueError("relative_path cannot escape the knowledge root") from exc

        suffix = target_path.suffix.lower()
        if suffix not in self.settings.supported_extensions:
            raise ValueError(f"Unsupported file extension: {suffix or '<none>'}")

        return target_path

    @staticmethod
    def _build_file_record(path: Path) -> FileRecord:
        stat = path.stat()
        return FileRecord(
            path=path,
            checksum=FileScanner._checksum(path),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            mime_type=FileScanner._mime_type(path),
        )
