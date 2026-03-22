from __future__ import annotations

from typing import Any

import pytest

from kb_api.config import Settings
from kb_api.services import embedder as embedder_module
from kb_api.services.embedder import QueryEmbedder


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
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.calls.append((url, json))
        return self.response

    def close(self) -> None:
        self.closed = True


def test_query_embedder_returns_none_when_embeddings_disabled(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=False)
    fake_client = FakeClient(FakeResponse({"embedding": [0.1]}))
    monkeypatch.setattr(embedder_module.httpx, "Client", lambda *args, **kwargs: fake_client)

    embedder = QueryEmbedder(settings)

    assert embedder.embed_query("hello") is None
    assert fake_client.calls == []


def test_query_embedder_posts_query_and_returns_floats(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=True, text_embedding_model="embed-model")
    fake_client = FakeClient(FakeResponse({"embedding": [1, 2.5]}))
    monkeypatch.setattr(embedder_module.httpx, "Client", lambda *args, **kwargs: fake_client)

    embedder = QueryEmbedder(settings)
    result = embedder.embed_query("hello world")

    assert result == [1.0, 2.5]
    assert fake_client.calls == [("/api/embeddings", {"model": "embed-model", "prompt": "hello world"})]


def test_query_embedder_returns_none_when_payload_has_no_embedding(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=True)
    monkeypatch.setattr(embedder_module.httpx, "Client", lambda *args, **kwargs: FakeClient(FakeResponse({"x": 1})))

    embedder = QueryEmbedder(settings)

    assert embedder.embed_query("hello") is None


def test_query_embedder_propagates_http_errors_and_closes(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_embeddings=True)
    fake_client = FakeClient(FakeResponse({}, raise_error=RuntimeError("bad status")))
    monkeypatch.setattr(embedder_module.httpx, "Client", lambda *args, **kwargs: fake_client)
    embedder = QueryEmbedder(settings)

    with pytest.raises(RuntimeError, match="bad status"):
        embedder.embed_query("hello")

    embedder.close()
    assert fake_client.closed is True
