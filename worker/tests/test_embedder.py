from __future__ import annotations

from typing import Any

from kb_worker.config import Settings
from kb_worker.services import embedder as embedder_module
from kb_worker.services.embedder import OllamaEmbedder


class FakeResponse:
    def __init__(self, payload: dict[str, Any], raise_error: Exception | None = None) -> None:
        self.payload = payload
        self.raise_error = raise_error

    def raise_for_status(self) -> None:
        if self.raise_error:
            raise self.raise_error

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeClient:
    def __init__(self, responses: list[Any], calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._responses = list(responses)
        self.calls = calls

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict[str, Any]) -> Any:
        self.calls.append((url, json))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_embedder_returns_none_for_each_text_when_disabled(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=False)
    monkeypatch.setattr(embedder_module.httpx, "Client", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError))

    result = OllamaEmbedder(settings).embed_texts(["a", "b"])

    assert result == [None, None]


def test_embedder_returns_empty_list_for_empty_input() -> None:
    settings = Settings(app_env="test", enable_embeddings=True)

    assert OllamaEmbedder(settings).embed_texts([]) == []


def test_embedder_posts_each_text_and_continues_on_failures(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=True, text_embedding_model="embed-model")
    calls: list[tuple[str, dict[str, Any]]] = []
    responses = [
        FakeResponse({"embedding": [0.1, 0.2]}),
        RuntimeError("network"),
        FakeResponse({"embedding": [0.3]}),
    ]
    monkeypatch.setattr(
        embedder_module.httpx,
        "Client",
        lambda *args, **kwargs: FakeClient(responses, calls),
    )

    result = OllamaEmbedder(settings).embed_texts(["first", "second", "third"])

    assert result == [[0.1, 0.2], None, [0.3]]
    assert calls == [
        ("/api/embeddings", {"model": "embed-model", "prompt": "first"}),
        ("/api/embeddings", {"model": "embed-model", "prompt": "second"}),
        ("/api/embeddings", {"model": "embed-model", "prompt": "third"}),
    ]
