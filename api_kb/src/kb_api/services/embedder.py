from __future__ import annotations

import logging

import httpx

from kb_api.config import Settings

logger = logging.getLogger(__name__)


class QueryEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(base_url=settings.ollama_base_url, timeout=60.0)

    def close(self) -> None:
        self.client.close()

    def embed_query(self, text: str) -> list[float] | None:
        if not self.settings.enable_embeddings:
            return None
        response = self.client.post(
            "/api/embeddings",
            json={"model": self.settings.text_embedding_model, "prompt": text},
        )
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            logger.warning("Ollama returned no embedding for query")
            return None
        return [float(item) for item in embedding]
