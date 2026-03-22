from __future__ import annotations

import hashlib
from pathlib import Path

from kb_worker.config import Settings
from kb_worker.services import scanner as scanner_module
from kb_worker.services.scanner import FileScanner


def test_scanner_filters_hidden_and_unsupported_files(tmp_path: Path, monkeypatch) -> None:
    visible = tmp_path / "visible.md"
    visible.write_text("hello", encoding="utf-8")
    hidden = tmp_path / ".secret.md"
    hidden.write_text("secret", encoding="utf-8")
    unsupported = tmp_path / "data.bin"
    unsupported.write_bytes(b"\x00\x01")
    (tmp_path / "nested").mkdir()
    nested = tmp_path / "nested" / "script.py"
    nested.write_text("print('hi')", encoding="utf-8")
    settings = Settings(app_env="test", source_roots=[tmp_path], include_hidden=False)
    monkeypatch.setattr(FileScanner, "_checksum", staticmethod(lambda path: f"sum:{path.name}"))
    monkeypatch.setattr(FileScanner, "_mime_type", staticmethod(lambda path: f"type/{path.suffix.lstrip('.')}"))

    records = FileScanner(settings).scan()

    assert [record.path.name for record in records] == ["visible.md", "script.py"]
    assert [record.checksum for record in records] == ["sum:visible.md", "sum:script.py"]
    assert [record.mime_type for record in records] == ["type/md", "type/py"]


def test_scanner_includes_hidden_files_when_enabled(tmp_path: Path, monkeypatch) -> None:
    hidden = tmp_path / ".secret.md"
    hidden.write_text("secret", encoding="utf-8")
    settings = Settings(app_env="test", source_roots=[tmp_path], include_hidden=True)
    monkeypatch.setattr(FileScanner, "_checksum", staticmethod(lambda path: "sum"))
    monkeypatch.setattr(FileScanner, "_mime_type", staticmethod(lambda path: "text/plain"))

    records = FileScanner(settings).scan()

    assert [record.path.name for record in records] == [".secret.md"]


def test_checksum_uses_sha256(tmp_path: Path) -> None:
    path = tmp_path / "payload.txt"
    path.write_text("hello", encoding="utf-8")

    checksum = FileScanner._checksum(path)

    assert checksum == hashlib.sha256(b"hello").hexdigest()


def test_mime_type_returns_none_on_magic_failure(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "payload.txt"
    path.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(scanner_module.magic, "from_file", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError))

    assert FileScanner._mime_type(path) is None
