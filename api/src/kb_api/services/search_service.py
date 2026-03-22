from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from kb_api.config import Settings
from kb_api.models import SearchHit, SearchRequest, SearchResponse
from kb_api.services.answer_generator import AnswerGenerator
from kb_api.services.embedder import QueryEmbedder
from kb_api.services.query_classifier import QueryClassifier
from kb_api.storage.neo4j_graph import GraphContextStore
from kb_api.storage.postgres import PostgresSearchStore

logger = logging.getLogger(__name__)


class SearchService:
    CHANNEL_BOOSTS = {
        "exact": 1.00,
        "lexical": 0.95,
        "semantic": 0.90,
        "ocr": 0.85,
        "code": 0.92,
        "image": 0.80,
        "graph": 0.75,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = PostgresSearchStore(settings)
        self.graph = GraphContextStore(settings)
        self.embedder = QueryEmbedder(settings)
        self.answer_generator = AnswerGenerator(settings)
        self.classifier = QueryClassifier(settings)

    def close(self) -> None:
        self.graph.close()
        self.embedder.close()
        self.answer_generator.close()

    def readiness(self) -> dict[str, object]:
        return {
            "status": "ok",
            "checks": {
                "postgres": self.store.ping(),
                "neo4j": self.graph.ping() if self.settings.enable_graph_context else True,
            },
        }

    def search(self, request: SearchRequest) -> SearchResponse:
        top_k = min(request.top_k, self.settings.max_top_k)
        plan = self.classifier.classify(request)
        filters = request.filters.model_dump()
        collected: list[SearchHit] = []

        if plan.exact:
            collected.extend(
                self._adapt_hits("exact", self.store.exact_search(request.query, top_k))
            )
        if plan.lexical:
            collected.extend(
                self._adapt_hits(
                    "lexical",
                    self.store.fts_search(request.query, top_k, filters),
                )
            )
        if plan.code:
            collected.extend(
                self._adapt_hits(
                    "code",
                    self.store.code_search(request.query, top_k, filters),
                )
            )
        if plan.ocr:
            collected.extend(
                self._adapt_hits(
                    "ocr",
                    self.store.ocr_search(request.query, top_k, filters),
                )
            )
        if plan.semantic:
            embedding = self.embedder.embed_query(request.query)
            if embedding:
                collected.extend(
                    self._adapt_hits(
                        "semantic",
                        self.store.semantic_search(embedding, top_k, filters),
                    )
                )

        merged = self._merge_hits(collected, top_k=top_k * 2)
        if plan.graph and merged:
            self._apply_graph_context(merged)
        ranked = self._rerank(merged, top_k=top_k)
        answer = self._generate_answer(request, ranked)

        return SearchResponse(
            query=request.query,
            plan=plan,
            total=len(ranked),
            answer=answer,
            results=ranked,
        )

    def _generate_answer(self, request: SearchRequest, hits: list[SearchHit]) -> str | None:
        if not request.include_answer or not hits:
            return None
        try:
            return self.answer_generator.generate_answer(request.query, hits)
        except Exception:  # noqa: BLE001
            logger.exception("Answer synthesis failed")
            return None

    def _adapt_hits(self, channel: str, rows: list[dict[str, Any]]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for row in rows:
            base_score = float(row.get("score") or 0.0)
            score = base_score * self.CHANNEL_BOOSTS[channel]
            snippet = (row.get("snippet") or "").strip()
            if len(snippet) > 900:
                snippet = snippet[:900] + "…"
            hits.append(
                SearchHit(
                    hit_id=str(row.get("hit_id")),
                    channel=channel,
                    hit_kind=str(row.get("hit_kind") or "unknown"),
                    source_path=str(row.get("source_path") or ""),
                    title=row.get("title"),
                    source_type=row.get("source_type"),
                    snippet=snippet,
                    score=score,
                    page_number=row.get("page_number"),
                    chunk_index=row.get("chunk_index"),
                    symbol_name=row.get("symbol_name"),
                    symbol_kind=row.get("symbol_kind"),
                    heading=row.get("heading"),
                    language=row.get("language"),
                    metadata={},
                )
            )
        return hits

    def _merge_hits(self, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        merged: OrderedDict[str, SearchHit] = OrderedDict()
        for hit in sorted(hits, key=lambda item: item.score, reverse=True):
            key = self._dedupe_key(hit)
            existing = merged.get(key)
            if not existing:
                merged[key] = hit
                continue
            if hit.score > existing.score:
                existing.score = hit.score
                existing.channel = hit.channel
            if hit.channel not in existing.metadata.get("channels", []):
                existing.metadata.setdefault("channels", []).append(hit.channel)
            if len(hit.snippet) > len(existing.snippet):
                existing.snippet = hit.snippet
        return list(merged.values())[:top_k]

    def _apply_graph_context(self, hits: list[SearchHit]) -> None:
        paths = list({hit.source_path for hit in hits[:20] if hit.source_path})
        try:
            related = self.graph.related_entities_by_source_path(paths)
        except Exception:  # noqa: BLE001
            logger.exception("Graph context expansion failed")
            return
        for hit in hits:
            hit.related_entities = related.get(hit.source_path, [])
            if hit.related_entities:
                hit.score += min(0.05 * len(hit.related_entities), 0.15)

    def _rerank(self, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        ranked = sorted(
            hits,
            key=lambda item: (
                item.score,
                1 if item.channel == "exact" else 0,
                1 if item.symbol_name else 0,
                len(item.related_entities),
            ),
            reverse=True,
        )
        return ranked[:top_k]

    @staticmethod
    def _dedupe_key(hit: SearchHit) -> str:
        if hit.hit_kind == "symbol" and hit.symbol_name:
            return f"symbol::{hit.source_path}::{hit.symbol_name}::{hit.symbol_kind}"
        if hit.chunk_index is not None:
            return f"chunk::{hit.source_path}::{hit.chunk_index}"
        if hit.page_number is not None:
            return f"page::{hit.source_path}::{hit.page_number}::{hit.hit_kind}"
        return f"generic::{hit.source_path}::{hit.hit_kind}::{hit.snippet[:120]}"
