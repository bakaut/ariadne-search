from __future__ import annotations

import re

from kb_worker.models import ChunkArtifact, EntityMention

CAPITALIZED_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9_\-]{2,})\b")


class EntityExtractor:
    def extract(self, chunks: list[ChunkArtifact]) -> list[EntityMention]:
        mentions: list[EntityMention] = []
        for chunk in chunks:
            for match in CAPITALIZED_TOKEN.finditer(chunk.content):
                token = match.group(1)
                mentions.append(
                    EntityMention(
                        canonical_name=token,
                        entity_type="keyword",
                        mention_text=token,
                        confidence=0.35,
                        chunk_index=chunk.chunk_index,
                    )
                )
        return mentions
