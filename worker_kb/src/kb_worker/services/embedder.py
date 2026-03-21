from __future__ import annotations

import logging

import httpx

from kb_worker.config import Settings

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        if not self.settings.enable_embeddings or not texts:
            return [None for _ in texts]

        results: list[list[float] | None] = []
        with httpx.Client(base_url=self.settings.ollama_base_url, timeout=60.0) as client:
            for text in texts:
                try:
                    response = client.post(
                        "/api/embeddings",
                        json={"model": self.settings.text_embedding_model, "prompt": text},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    results.append(payload.get("embedding"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to embed text chunk: %s", exc)
                    results.append(None)
        return results
