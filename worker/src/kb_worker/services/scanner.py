from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import magic

from kb_worker.config import Settings
from kb_worker.models import FileRecord

logger = logging.getLogger(__name__)


class FileScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def scan(self) -> list[FileRecord]:
        discovered: list[FileRecord] = []
        for root in self.settings.source_roots:
            if not root.exists():
                logger.warning("Source root does not exist: %s", root)
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if not self.settings.include_hidden and any(part.startswith(".") for part in path.parts):
                    continue
                if path.suffix.lower() not in self.settings.supported_extensions:
                    continue
                stat = path.stat()
                discovered.append(
                    FileRecord(
                        path=path,
                        checksum=self._checksum(path),
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        mime_type=self._mime_type(path),
                    )
                )
        logger.info("Discovered %s supported files", len(discovered))
        return discovered

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _mime_type(path: Path) -> str | None:
        try:
            return magic.from_file(str(path), mime=True)
        except Exception:  # noqa: BLE001
            return None
