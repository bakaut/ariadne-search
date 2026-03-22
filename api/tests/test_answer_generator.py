from __future__ import annotations

from typing import Any

import pytest

import kb_api.services.answer_generator as answer_module
from kb_api.config import Settings
from kb_api.models import SearchHit
from kb_api.services.answer_generator import AnswerGenerator


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


def make_hit(**overrides) -> SearchHit:
    data = {
        "hit_id": "1",
        "channel": "lexical",
        "hit_kind": "chunk",
        "source_path": "/tmp/doc.md",
        "title": "doc",
        "snippet": "first snippet",
        "score": 1.0,
        "chunk_index": 0,
    }
    data.update(overrides)
    return SearchHit(**data)


def test_answer_generator_returns_none_when_disabled(monkeypatch) -> None:
    settings = Settings(app_env="test", enable_answer_synthesis=False)
    fake_client = FakeClient(FakeResponse({"response": "ignored"}))
    monkeypatch.setattr(answer_module.httpx, "Client", lambda *args, **kwargs: fake_client)

    generator = AnswerGenerator(settings)

    assert generator.generate_answer("hello", [make_hit()]) is None
    assert fake_client.calls == []


def test_answer_generator_posts_prompt_and_returns_stripped_answer(monkeypatch) -> None:
    settings = Settings(app_env="test", answer_model="local-model", answer_temperature=0.2)
    fake_client = FakeClient(FakeResponse({"response": "  final answer [1]  "}))
    monkeypatch.setattr(answer_module.httpx, "Client", lambda *args, **kwargs: fake_client)

    generator = AnswerGenerator(settings)
    answer = generator.generate_answer(
        "hello world",
        [make_hit(), make_hit(hit_id="2", chunk_index=1)],
    )

    assert answer == "final answer [1]"
    assert fake_client.calls[0][0] == "/api/generate"
    assert fake_client.calls[0][1]["model"] == "local-model"
    assert fake_client.calls[0][1]["stream"] is False
    assert fake_client.calls[0][1]["options"] == {"temperature": 0.2}
    assert "hello world" in fake_client.calls[0][1]["prompt"]
    assert "first snippet" in fake_client.calls[0][1]["prompt"]


def test_answer_generator_returns_none_when_payload_has_no_response(monkeypatch) -> None:
    settings = Settings(app_env="test")
    fake_client = FakeClient(FakeResponse({"x": 1}))
    monkeypatch.setattr(answer_module.httpx, "Client", lambda *args, **kwargs: fake_client)

    generator = AnswerGenerator(settings)

    assert generator.generate_answer("hello", [make_hit()]) is None


def test_answer_generator_propagates_http_errors_and_closes(monkeypatch) -> None:
    settings = Settings(app_env="test")
    fake_client = FakeClient(FakeResponse({}, raise_error=RuntimeError("bad status")))
    monkeypatch.setattr(answer_module.httpx, "Client", lambda *args, **kwargs: fake_client)
    generator = AnswerGenerator(settings)

    with pytest.raises(RuntimeError, match="bad status"):
        generator.generate_answer("hello", [make_hit()])

    generator.close()
    assert fake_client.closed is True
