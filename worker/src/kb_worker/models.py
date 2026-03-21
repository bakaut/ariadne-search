from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class FileRecord:
    path: Path
    checksum: str
    size_bytes: int
    modified_at: datetime
    mime_type: str | None


@dataclass(slots=True)
class DocumentType:
    source_type: str
    is_code: bool = False
    is_paged: bool = False
    requires_ocr: bool = False
    is_image: bool = False
    is_diagram: bool = False


@dataclass(slots=True)
class PageArtifact:
    page_number: int
    page_text: str
    render_path: str | None = None
    width: int | None = None
    height: int | None = None
    page_embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AssetArtifact:
    asset_type: str
    asset_role: str
    storage_path: str
    page_number: int | None = None
    caption_text: str | None = None
    ocr_text: str | None = None
    image_embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCRBlockArtifact:
    text: str
    block_index: int
    confidence: float | None = None
    page_number: int | None = None
    asset_storage_path: str | None = None
    bbox_json: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkArtifact:
    chunk_index: int
    content: str
    chunk_kind: str = "text"
    heading: str | None = None
    page_number: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EntityMention:
    canonical_name: str
    entity_type: str
    mention_text: str
    confidence: float = 0.5
    chunk_index: int | None = None
    asset_storage_path: str | None = None


@dataclass(slots=True)
class SymbolArtifact:
    symbol_name: str
    symbol_kind: str
    fq_name: str
    language: str | None
    start_line: int
    end_line: int
    signature: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SymbolLinkArtifact:
    from_symbol_fq_name: str
    to_symbol_fq_name: str
    link_type: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ETLBundle:
    document_id: UUID = field(default_factory=uuid4)
    source_path: str = ""
    source_type: str = "unknown"
    title: str | None = None
    checksum: str = ""
    mime_type: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: list[PageArtifact] = field(default_factory=list)
    chunks: list[ChunkArtifact] = field(default_factory=list)
    assets: list[AssetArtifact] = field(default_factory=list)
    ocr_blocks: list[OCRBlockArtifact] = field(default_factory=list)
    entities: list[EntityMention] = field(default_factory=list)
    symbols: list[SymbolArtifact] = field(default_factory=list)
    symbol_links: list[SymbolLinkArtifact] = field(default_factory=list)

    @property
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
