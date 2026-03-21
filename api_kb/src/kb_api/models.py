from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    source_types: list[str] = Field(default_factory=list)
    path_prefixes: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_graph_context: bool = True
    include_exact: bool = True
    include_code: bool = True
    include_ocr: bool = True
    include_semantic: bool = True
    include_image: bool = False


class SearchPlan(BaseModel):
    exact: bool
    lexical: bool
    semantic: bool
    ocr: bool
    code: bool
    image: bool
    graph: bool
    reasons: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    hit_id: str
    channel: Literal["exact", "lexical", "semantic", "ocr", "code", "image", "graph"]
    hit_kind: str
    source_path: str
    title: str | None = None
    source_type: str | None = None
    snippet: str
    score: float
    page_number: int | None = None
    chunk_index: int | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    heading: str | None = None
    language: str | None = None
    related_entities: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    plan: SearchPlan
    total: int
    results: list[SearchHit]
