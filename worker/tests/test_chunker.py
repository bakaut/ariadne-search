from __future__ import annotations

from kb_worker.config import Settings
from kb_worker.services.chunker import Chunker


def test_chunker_returns_empty_for_blank_text() -> None:
    chunker = Chunker(Settings(app_env="test", chunk_size_chars=10, chunk_overlap_chars=3))

    assert chunker.chunk_text("   \n\t  ") == []


def test_chunker_splits_with_overlap_and_metadata() -> None:
    chunker = Chunker(Settings(app_env="test", chunk_size_chars=5, chunk_overlap_chars=2))

    chunks = chunker.chunk_text("abcdefghij", chunk_kind="code", page_number=7)

    assert [chunk.content for chunk in chunks] == ["abcde", "defgh", "ghij"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert [(chunk.start_offset, chunk.end_offset) for chunk in chunks] == [(0, 5), (3, 8), (6, 10)]
    assert all(chunk.chunk_kind == "code" for chunk in chunks)
    assert all(chunk.page_number == 7 for chunk in chunks)


def test_chunker_does_not_loop_forever_when_overlap_exceeds_size() -> None:
    chunker = Chunker(Settings(app_env="test", chunk_size_chars=3, chunk_overlap_chars=10))

    chunks = chunker.chunk_text("abcdef")

    assert [chunk.content for chunk in chunks] == ["abc", "bcd", "cde", "def"]
    assert chunks[-1].end_offset == 6
