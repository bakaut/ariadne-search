from __future__ import annotations

import subprocess

from kb_api.config import Settings
from kb_api.storage.neo4j_graph import GraphContextStore
from kb_api.storage.postgres import PostgresSearchStore


def test_document_filters_and_vector_literal() -> None:
    store = PostgresSearchStore(Settings(app_env="test"))

    where_sql, params = store._document_filters(
        {
            "source_types": ["text_native"],
            "path_prefixes": ["/tmp/docs", "/srv/code"],
            "languages": ["markdown"],
        }
    )

    assert "d.source_type = ANY(%(source_types)s)" in where_sql
    assert "d.source_path LIKE %(path_prefix_0)s" in where_sql
    assert "d.source_path LIKE %(path_prefix_1)s" in where_sql
    assert "coalesce(d.language, '') = ANY(%(languages)s)" in where_sql
    assert params == {
        "source_types": ["text_native"],
        "path_prefix_0": "/tmp/docs%",
        "path_prefix_1": "/srv/code%",
        "languages": ["markdown"],
    }
    assert store._vector_literal([0.1, 2]) == "[0.10000000,2.00000000]"


def test_parse_rg_line_handles_valid_and_invalid_line_numbers() -> None:
    assert PostgresSearchStore._parse_rg_line("/tmp/a.py:12: hit ") == ("/tmp/a.py", 12, "hit")
    assert PostgresSearchStore._parse_rg_line("/tmp/a.py:nope: hit ") == ("/tmp/a.py", None, "hit")
    assert PostgresSearchStore._parse_rg_line("bad line") == (None, None, "bad line")


def test_exact_search_respects_feature_flag_and_parses_rg_output(tmp_path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    settings = Settings(app_env="test", source_roots=[root], enable_exact_search=True)
    store = PostgresSearchStore(settings)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=["rg"],
            returncode=0,
            stdout=f"{root}/main.py:7:def hello()\n",
            stderr="",
        )

    monkeypatch.setattr("kb_api.storage.postgres.subprocess.run", fake_run)

    hits = store.exact_search("hello", 5)

    assert hits[0]["source_path"] == f"{root}/main.py"
    assert hits[0]["snippet"] == "def hello()"
    assert hits[0]["score"] == 1.0


def test_exact_search_returns_empty_when_rg_missing(tmp_path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    store = PostgresSearchStore(Settings(app_env="test", source_roots=[root], enable_exact_search=True))
    monkeypatch.setattr(
        "kb_api.storage.postgres.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )

    assert store.exact_search("hello", 5) == []


def test_graph_context_store_ping_and_related_entities(monkeypatch) -> None:
    import kb_api.storage.neo4j_graph as graph_module

    class FakeSession:
        def __init__(self, rows) -> None:
            self.rows = rows

        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def run(self, query, **kwargs):
            if "RETURN 1 AS ok" in query:
                return type("SingleResult", (), {"single": lambda self: {"ok": 1}})()
            return self.rows

    class FakeDriver:
        def __init__(self) -> None:
            self.closed = False

        def session(self, database=None):
            rows = [
                {"source_path": "/tmp/a.md", "entities": ["A", "B"]},
                {"source_path": "/tmp/b.md", "entities": []},
            ]
            return FakeSession(rows)

        def close(self) -> None:
            self.closed = True

    driver = FakeDriver()
    monkeypatch.setattr(graph_module.GraphDatabase, "driver", lambda *args, **kwargs: driver)
    store = GraphContextStore(Settings(app_env="test"))

    assert store.ping() is True
    assert store.related_entities_by_source_path([]) == {}
    assert store.related_entities_by_source_path(["/tmp/a.md", "/tmp/b.md"]) == {
        "/tmp/a.md": ["A", "B"],
        "/tmp/b.md": [],
    }
    store.close()
    assert driver.closed is True
