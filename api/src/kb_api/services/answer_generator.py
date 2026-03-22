from __future__ import annotations

import logging

import httpx

from kb_api.config import Settings
from kb_api.models import SearchHit

logger = logging.getLogger(__name__)


class AnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(base_url=settings.ollama_base_url, timeout=120.0)

    def close(self) -> None:
        self.client.close()

    def generate_answer(self, query: str, hits: list[SearchHit]) -> str | None:
        if not self.settings.enable_answer_synthesis or not hits:
            return None

        prompt = self._build_prompt(query, hits)
        if not prompt:
            return None

        response = self.client.post(
            "/api/generate",
            json={
                "model": self.settings.answer_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": self.settings.answer_temperature},
            },
        )
        response.raise_for_status()
        payload = response.json()
        answer = payload.get("response")
        if not isinstance(answer, str):
            logger.warning("Ollama returned no text answer for query")
            return None
        answer = answer.strip()
        return answer or None

    def _build_prompt(self, query: str, hits: list[SearchHit]) -> str | None:
        context = self._build_context(hits)
        if not context:
            return None

        return (
            "You answer questions using only the provided search context.\n"
            "Rules:\n"
            "- Write a concise, human-readable answer in the same language as the user query.\n"
            "- Synthesize information across all relevant chunks.\n"
            "- Cite supporting sources inline as [1], [2], etc.\n"
            "- If the context is incomplete, say so explicitly.\n"
            "- Do not invent facts that are not present in the context.\n\n"
            f"User query:\n{query}\n\n"
            f"Search context:\n{context}\n\n"
            "Answer:"
        )

    def _build_context(self, hits: list[SearchHit]) -> str:
        parts: list[str] = []
        used_chars = 0

        for index, hit in enumerate(hits[: self.settings.answer_max_context_hits], start=1):
            details: list[str] = [f"[{index}] path: {hit.source_path or 'unknown'}"]
            if hit.title:
                details.append(f"title: {hit.title}")
            if hit.heading:
                details.append(f"heading: {hit.heading}")
            if hit.symbol_name:
                symbol_kind = f" ({hit.symbol_kind})" if hit.symbol_kind else ""
                details.append(f"symbol: {hit.symbol_name}{symbol_kind}")
            if hit.page_number is not None:
                details.append(f"page: {hit.page_number}")
            if hit.chunk_index is not None:
                details.append(f"chunk: {hit.chunk_index}")
            if hit.metadata.get("channels"):
                channels = ", ".join(str(item) for item in hit.metadata["channels"])
                details.append(f"channels: {channels}")
            if hit.related_entities:
                details.append("entities: " + ", ".join(hit.related_entities))
            details.append(f"snippet: {hit.snippet}")

            entry = "\n".join(details)
            if used_chars and used_chars + len(entry) > self.settings.answer_max_context_chars:
                break
            parts.append(entry)
            used_chars += len(entry)

        return "\n\n".join(parts)
