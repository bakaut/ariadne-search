from __future__ import annotations

from pathlib import Path

from kb_worker.extractors.ocr import OCRExtractor
from kb_worker.extractors.office_pdf import OfficePdfExtractor
from kb_worker.extractors.text import TextExtractor


def test_text_extractor_reads_utf8_ignoring_invalid_bytes(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_bytes(b"hello\xffworld")

    content = TextExtractor().extract(path)

    assert content == "helloworld"


def test_office_pdf_extractor_returns_single_page_for_markdown(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("# Title", encoding="utf-8")

    raw_text, pages = OfficePdfExtractor().extract(path)

    assert raw_text == "# Title"
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].page_text == "# Title"


def test_office_pdf_extractor_is_stub_for_other_suffixes(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.5")

    raw_text, pages = OfficePdfExtractor().extract(path)

    assert raw_text == ""
    assert pages == []


def test_ocr_extractor_returns_empty_stub_payload(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG")

    pages, blocks, text = OCRExtractor().extract_image(path)

    assert pages == []
    assert blocks == []
    assert text == ""
