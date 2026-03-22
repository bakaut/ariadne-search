from __future__ import annotations

from pathlib import Path

import pytest

from kb_worker.config import Settings
from kb_worker.services.ingest import DummyIngestService

SUPPORTED_UPLOAD_SUFFIXES = sorted(Settings(app_env="test").supported_extensions)


class FakePipeline:
    def __init__(self, changed: bool = True, indexed: bool = True) -> None:
        self.closed = False
        self.postgres = type("FakePostgres", (), {"has_changed": lambda _, __: changed})()
        self._indexed = indexed
        self.force = None

    def process_file(self, file_record, force: bool = False) -> bool:
        self.force = force
        return self._indexed

    def close(self) -> None:
        self.closed = True


def make_upload(filename: str, payload: bytes = b"hello knowledge"):
    return type(
        "Upload",
        (),
        {
            "filename": filename,
            "file": type("Payload", (), {"read": lambda self: payload})(),
        },
    )()


def test_dummy_ingest_service_writes_file_and_indexes(monkeypatch, settings, tmp_path: Path) -> None:
    pipeline = FakePipeline(changed=True, indexed=True)
    monkeypatch.setattr("kb_worker.services.ingest.ETLPipeline", lambda cfg: pipeline)

    service = DummyIngestService(settings)
    upload = make_upload("notes/test.txt")

    response = service.ingest_upload(upload)

    target = tmp_path / "notes" / "test.txt"
    assert response["status"] == "indexed"
    assert response["source_path"] == str(target)
    assert target.read_text() == "hello knowledge"
    assert pipeline.closed is True
    assert pipeline.force is False


def test_dummy_ingest_service_force_reindexes_unchanged_file(monkeypatch, settings, tmp_path: Path) -> None:
    pipeline = FakePipeline(changed=False, indexed=True)
    monkeypatch.setattr("kb_worker.services.ingest.ETLPipeline", lambda cfg: pipeline)

    service = DummyIngestService(settings)
    response = service.ingest_upload(make_upload("notes/test.txt"), force=True)

    assert response["status"] == "indexed"
    assert pipeline.force is True


@pytest.mark.parametrize("suffix", SUPPORTED_UPLOAD_SUFFIXES)
def test_dummy_ingest_service_accepts_supported_extensions(
    monkeypatch, settings, tmp_path: Path, suffix: str
) -> None:
    pipeline = FakePipeline(changed=True, indexed=True)
    monkeypatch.setattr("kb_worker.services.ingest.ETLPipeline", lambda cfg: pipeline)

    service = DummyIngestService(settings)
    response = service.ingest_upload(
        make_upload("ignored.bin", payload=b"stub payload"),
        relative_path=f"uploads/sample{suffix}",
    )

    target = tmp_path / "uploads" / f"sample{suffix}"
    assert response["status"] == "indexed"
    assert response["source_path"] == str(target)
    assert target.read_bytes() == b"stub payload"


def test_dummy_ingest_service_rejects_unsupported_extension(settings) -> None:
    service = DummyIngestService(settings)

    with pytest.raises(ValueError, match="Unsupported file extension: \\.wav"):
        service._target_path("uploads/sample.wav", None)


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
        lambda file, relative_path=None, force=False: {
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
            data={"relative_path": "docs/note.txt", "force": "true"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "indexed"


def test_create_app_exposes_upload_contract_in_openapi(settings) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app

    app = create_app(settings)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/dummy/documents"]["post"]
    assert operation["summary"] == "Upload and index a document"
    assert "multipart/form-data" in operation["requestBody"]["content"]
    force_schema = (
        operation["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"]["force"]
    )
    assert force_schema["type"] == "boolean"
    assert operation["responses"]["200"]["description"].startswith("The file was accepted")
    assert operation["responses"]["400"]["description"].startswith("Validation error")
    assert operation["responses"]["500"]["description"].startswith("The file was saved")


def test_create_app_rejects_unsupported_extension_with_real_service(settings) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app

    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/dummy/documents",
            files={"file": ("sample.wav", b"RIFF....WAVE", "audio/wav")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported file extension: .wav"}


def test_create_app_returns_400_for_bad_upload(monkeypatch, settings) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app
    import kb_worker.app as app_module

    service = DummyIngestService(settings)
    monkeypatch.setattr(app_module, "DummyIngestService", lambda cfg: service)
    monkeypatch.setattr(
        service,
        "ingest_upload",
        lambda file, relative_path=None, force=False: (_ for _ in ()).throw(ValueError("bad path")),
    )

    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/dummy/documents",
            files={"file": ("note.txt", b"hey", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "bad path"}


def test_create_app_returns_500_for_index_failure(monkeypatch, settings) -> None:
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    from kb_worker.app import create_app
    import kb_worker.app as app_module

    service = DummyIngestService(settings)
    monkeypatch.setattr(app_module, "DummyIngestService", lambda cfg: service)
    monkeypatch.setattr(
        service,
        "ingest_upload",
        lambda file, relative_path=None, force=False: (_ for _ in ()).throw(RuntimeError("index failed")),
    )

    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/dummy/documents",
            files={"file": ("note.txt", b"hey", "text/plain")},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "index failed"}
