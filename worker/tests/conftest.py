from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kb_worker.config import Settings
from kb_worker.models import FileRecord

try:
    import magic as _magic  # noqa: F401
except ImportError:
    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda *args, **kwargs: "application/octet-stream"
    sys.modules["magic"] = fake_magic


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        source_roots=[tmp_path],
        postgres_dsn="postgresql://kb:kb@localhost:5432/kb",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        ollama_base_url="http://localhost:11434",
        enable_embeddings=False,
        enable_neo4j_projection=True,
    )


@pytest.fixture
def make_file_record():
    def factory(path: Path, mime_type: str | None = "text/plain", checksum: str = "checksum") -> FileRecord:
        stat = path.stat()
        return FileRecord(
            path=path,
            checksum=checksum,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            mime_type=mime_type,
        )

    return factory
