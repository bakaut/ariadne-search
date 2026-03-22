from __future__ import annotations

from uuid import uuid4

from kb_worker.config import Settings
from kb_worker.models import ChunkArtifact, ETLBundle, EntityMention, SymbolArtifact, SymbolLinkArtifact
from kb_worker.storage.neo4j_projection import Neo4jProjectionStore
from kb_worker.storage.postgres import PostgresStore


class FakeCursor:
    def __init__(self, fetchone_values=None) -> None:
        self.fetchone_values = list(fetchone_values or [])
        self.executed = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_values.pop(0)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


def test_postgres_has_changed_returns_expected_values(monkeypatch) -> None:
    import kb_worker.storage.postgres as postgres_module

    settings = Settings(app_env="test")
    store = PostgresStore(settings)
    file_record = type("Record", (), {"path": "/tmp/doc.md", "checksum": "abc"})()

    cursor = FakeCursor(fetchone_values=[None, {"checksum": "other"}, {"checksum": "abc"}])
    monkeypatch.setattr(postgres_module.psycopg, "connect", lambda *args, **kwargs: FakeConnection(cursor))

    assert store.has_changed(file_record) is True
    assert store.has_changed(file_record) is True
    assert store.has_changed(file_record) is False


def test_postgres_upsert_bundle_runs_helpers_in_order(monkeypatch) -> None:
    import kb_worker.storage.postgres as postgres_module

    settings = Settings(app_env="test")
    store = PostgresStore(settings)
    bundle = ETLBundle(source_path="/tmp/doc.md")
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    steps = []
    monkeypatch.setattr(postgres_module.psycopg, "connect", lambda *args, **kwargs: connection)
    monkeypatch.setattr(postgres_module, "uuid4", lambda: uuid4())
    monkeypatch.setattr(store, "_upsert_document", lambda cur, b: steps.append("_upsert_document"))
    monkeypatch.setattr(store, "_replace_pages", lambda cur, b: steps.append("_replace_pages"))
    monkeypatch.setattr(store, "_replace_assets", lambda cur, b: steps.append("_replace_assets"))
    monkeypatch.setattr(store, "_replace_ocr_blocks", lambda cur, b: steps.append("_replace_ocr_blocks"))
    monkeypatch.setattr(store, "_replace_chunks", lambda cur, b: steps.append("_replace_chunks"))
    monkeypatch.setattr(store, "_replace_entities", lambda cur, b: steps.append("_replace_entities"))
    monkeypatch.setattr(store, "_replace_symbols", lambda cur, b: steps.append("_replace_symbols"))

    store.upsert_bundle(bundle)

    assert steps == [
        "_upsert_document",
        "_replace_pages",
        "_replace_assets",
        "_replace_ocr_blocks",
        "_replace_chunks",
        "_replace_entities",
        "_replace_symbols",
    ]
    assert connection.committed is True
    assert len(cursor.executed) == 2


def test_postgres_mark_failed_truncates_error_text(monkeypatch) -> None:
    import kb_worker.storage.postgres as postgres_module

    settings = Settings(app_env="test")
    store = PostgresStore(settings)
    cursor = FakeCursor(fetchone_values=[["doc-id"]])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(postgres_module.psycopg, "connect", lambda *args, **kwargs: connection)

    store.mark_failed("doc-id", "x" * 5000)

    assert connection.committed is True
    params = cursor.executed[1][1]
    assert params[4] == "x" * 4000


def test_postgres_mark_failed_allows_missing_document(monkeypatch) -> None:
    import kb_worker.storage.postgres as postgres_module

    settings = Settings(app_env="test")
    store = PostgresStore(settings)
    cursor = FakeCursor(fetchone_values=[None])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(postgres_module.psycopg, "connect", lambda *args, **kwargs: connection)

    store.mark_failed("missing-doc-id", "boom")

    assert connection.committed is True
    params = cursor.executed[1][1]
    assert params[1] is None


def test_postgres_vector_literal_and_ensure_file() -> None:
    settings = Settings(app_env="test")
    store = PostgresStore(settings)
    cursor = FakeCursor(fetchone_values=[["file-id"]])

    assert store._vector_literal(None) is None
    assert store._vector_literal([]) is None
    assert store._vector_literal([0.1, 2]) == "[0.10000000,2.00000000]"

    file_id = store._ensure_file(cursor, "src/main.py", "doc-id", "python")

    assert file_id == "file-id"
    assert cursor.executed[0][1][4] == "py"


def test_neo4j_projection_respects_feature_flag_and_close(monkeypatch) -> None:
    import kb_worker.storage.neo4j_projection as neo4j_module

    class FakeSession:
        def __init__(self) -> None:
            self.execute_write = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError)

        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeDriver:
        def __init__(self) -> None:
            self.close_called = False

        def session(self, database=None):
            return FakeSession()

        def close(self) -> None:
            self.close_called = True

    driver = FakeDriver()
    monkeypatch.setattr(neo4j_module.GraphDatabase, "driver", lambda *args, **kwargs: driver)
    settings = Settings(app_env="test", enable_neo4j_projection=False)
    store = Neo4jProjectionStore(settings)

    store.project_bundle(ETLBundle(source_path="/tmp/doc.md"))
    store.close()

    assert driver.close_called is True


def test_neo4j_project_tx_emits_queries_for_bundle_graph() -> None:
    class FakeTx:
        def __init__(self) -> None:
            self.calls = []

        def run(self, query, **params) -> None:
            self.calls.append((query, params))

    bundle = ETLBundle(
        source_path="/tmp/main.py",
        source_type="code",
        title="main",
        language="python",
        pages=[],
        chunks=[ChunkArtifact(chunk_index=0, content="hello", page_number=1)],
        entities=[EntityMention(canonical_name="OpenAI", entity_type="keyword", mention_text="OpenAI", chunk_index=0)],
        symbols=[
            SymbolArtifact(
                symbol_name="hello",
                symbol_kind="function",
                fq_name="main.hello",
                language="python",
                start_line=1,
                end_line=1,
            )
        ],
        symbol_links=[SymbolLinkArtifact(from_symbol_fq_name="main.hello", to_symbol_fq_name="callee", link_type="CALLS")],
    )
    tx = FakeTx()

    Neo4jProjectionStore._project_tx(tx, bundle)

    joined = "\n".join(query for query, _ in tx.calls)
    assert "MERGE (d:Document" in joined
    assert "MERGE (c:Chunk" in joined
    assert "MERGE (e:Entity" in joined
    assert "MERGE (s:Symbol" in joined
    assert "MERGE (a)-[:CALLS]->(b)" in joined
