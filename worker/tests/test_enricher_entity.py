from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kb_worker.models import ChunkArtifact, ETLBundle, FileRecord
from kb_worker.services.enricher import MetadataEnricher
from kb_worker.services.entity_extractor import EntityExtractor


def test_metadata_enricher_populates_title_language_and_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    file_path = repo_root / "src" / "main.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hi')", encoding="utf-8")
    file_record = FileRecord(
        path=file_path,
        checksum="abc",
        size_bytes=11,
        modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        mime_type="text/x-python",
    )
    bundle = ETLBundle(source_path=str(file_path))

    enriched = MetadataEnricher().enrich(bundle, file_record)

    assert enriched is bundle
    assert bundle.title == "main"
    assert bundle.language == "python"
    assert bundle.metadata["filename"] == "main.py"
    assert bundle.metadata["extension"] == ".py"
    assert bundle.metadata["size_bytes"] == 11
    assert bundle.metadata["modified_at"] == "2026-01-02T00:00:00+00:00"
    assert bundle.metadata["repo_hint"] == str(repo_root)
    assert bundle.metadata["path_parts"][-3:] == ["repo", "src", "main.py"]


def test_entity_extractor_extracts_capitalized_tokens() -> None:
    extractor = EntityExtractor()
    chunks = [
        ChunkArtifact(chunk_index=0, content="OpenAI builds ChatGPT in Python"),
        ChunkArtifact(chunk_index=1, content="lowercase words only"),
    ]

    mentions = extractor.extract(chunks)

    assert [(m.canonical_name, m.chunk_index) for m in mentions] == [
        ("OpenAI", 0),
        ("ChatGPT", 0),
        ("Python", 0),
    ]
    assert all(m.entity_type == "keyword" for m in mentions)
    assert all(m.confidence == 0.35 for m in mentions)


def test_repo_hint_returns_none_without_git_root(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello", encoding="utf-8")

    assert MetadataEnricher._repo_hint(file_path) is None
