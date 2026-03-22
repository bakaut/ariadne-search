from __future__ import annotations

from pathlib import Path

import pytest

from kb_worker.services.ingest import DummyIngestService


class FakePipeline:
    def __init__(self, changed: bool = True, indexed: bool = True) -> None:
        self.closed = False
        self.postgres = type("FakePostgres", (), {"has_changed": lambda _, __: changed})()
        self._indexed = indexed

    def process_file(self, file_record) -> bool:
        return self._indexed

    def close(self) -> None:
        self.closed = True


def test_dummy_ingest_service_writes_file_and_indexes(monkeypatch, settings, tmp_path: Path) -> None:
    pipeline = FakePipeline(changed=True, indexed=True)
    monkeypatch.setattr("kb_worker.services.ingest.ETLPipeline", lambda cfg: pipeline)

    service = DummyIngestService(settings)
    upload = type(
        "Upload",
        (),
        {
            "filename": "notes/test.txt",
            "file": type("Payload", (), {"read": lambda self: b"hello knowledge"})(),
        },
    )()

    response = service.ingest_upload(upload)

    target = tmp_path / "notes" / "test.txt"
    assert response["status"] == "indexed"
    assert response["source_path"] == str(target)
    assert target.read_text() == "hello knowledge"
    assert pipeline.closed is True


def test_dummy_ingest_service_rejects_path_escape(settings) -> None:
    service = DummyIngestService(settings)

    with pytest.raises(ValueError, match="escape"):
        service._target_path("../secrets.txt", None)


def test_create_app_accepts_upload(monkeypatch, settings, tmp_path: Path) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app
    import kb_worker.app as app_module

    service = DummyIngestService(settings)
    monkeypatch.setattr(app_module, "DummyIngestService", lambda cfg: service)
    monkeypatch.setattr(
        service,
        "ingest_upload",
        lambda file, relative_path=None: {
            "status": "indexed",
            "source_path": str(tmp_path / (relative_path or file.filename)),
            "checksum": "abc",
            "size_bytes": 3,
        },
    )

    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        response = client.post(
            "/dummy/documents",
            files={"file": ("note.txt", b"hey", "text/plain")},
            data={"relative_path": "docs/note.txt"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "indexed"


def test_create_app_returns_400_for_bad_upload(monkeypatch, settings) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app
    import kb_worker.app as app_module

    service = DummyIngestService(settings)
    monkeypatch.setattr(app_module, "DummyIngestService", lambda cfg: service)
    monkeypatch.setattr(
        service,
        "ingest_upload",
        lambda file, relative_path=None: (_ for _ in ()).throw(ValueError("bad path")),
    )

    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/dummy/documents",
            files={"file": ("note.txt", b"hey", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "bad path"}
