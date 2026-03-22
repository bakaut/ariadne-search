from __future__ import annotations

from pathlib import Path

from kb_api.config import Settings


def test_source_roots_env_supports_plain_string(monkeypatch) -> None:
    monkeypatch.setenv("KB_SOURCE_ROOTS", "/data/knowledge")

    settings = Settings()

    assert settings.source_roots == [Path("/data/knowledge")]


def test_source_roots_env_supports_csv(monkeypatch) -> None:
    monkeypatch.setenv("KB_SOURCE_ROOTS", "/data/one, /data/two")

    settings = Settings()

    assert settings.source_roots == [Path("/data/one"), Path("/data/two")]
