from __future__ import annotations

from kb_worker.config import Settings
from kb_worker.models import ChunkArtifact


class Chunker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def chunk_text(self, text: str, chunk_kind: str = "text", page_number: int | None = None) -> list[ChunkArtifact]:
        if not text.strip():
            return []

        size = self.settings.chunk_size_chars
        overlap = self.settings.chunk_overlap_chars
        chunks: list[ChunkArtifact] = []
        start = 0
        index = 0
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    ChunkArtifact(
                        chunk_index=index,
                        content=piece,
                        chunk_kind=chunk_kind,
                        page_number=page_number,
                        start_offset=start,
                        end_offset=end,
                    )
                )
                index += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return chunks
