from __future__ import annotations

from pathlib import Path

from kb_worker.models import FileRecord
from kb_worker.services.classifier import DocumentClassifier


def make_record(path: str, mime_type: str | None = None) -> FileRecord:
    return FileRecord(
        path=Path(path),
        checksum="checksum",
        size_bytes=1,
        modified_at=None,  # type: ignore[arg-type]
        mime_type=mime_type,
    )


def test_classify_pdf_with_image_mime_requires_ocr() -> None:
    classifier = DocumentClassifier()

    document_type = classifier.classify(make_record("/tmp/scan.pdf", mime_type="image/png"))

    assert document_type.source_type == "pdf_document"
    assert document_type.is_paged is True
    assert document_type.requires_ocr is True


def test_classify_known_types() -> None:
    classifier = DocumentClassifier()

    assert classifier.classify(make_record("/tmp/readme.md")).source_type == "text_native"
    assert classifier.classify(make_record("/tmp/report.docx")).source_type == "office_document"
    assert classifier.classify(make_record("/tmp/code.py")).source_type == "code"
    assert classifier.classify(make_record("/tmp/figure.png")).source_type == "image"
    assert classifier.classify(make_record("/tmp/diagram.puml")).source_type == "diagram"
    assert classifier.classify(make_record("/tmp/file.unknown")).source_type == "unknown"


def test_guess_language_maps_known_suffixes() -> None:
    classifier = DocumentClassifier()

    assert classifier.guess_language(Path("main.py")) == "python"
    assert classifier.guess_language(Path("lib.hpp")) == "cpp"
    assert classifier.guess_language(Path("config.yml")) == "yaml"
    assert classifier.guess_language(Path("notes.txt")) is None
