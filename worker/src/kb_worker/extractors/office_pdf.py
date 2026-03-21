from __future__ import annotations

from pathlib import Path

from kb_worker.models import PageArtifact


class OfficePdfExtractor:
    def extract(self, path: Path) -> tuple[str, list[PageArtifact]]:
        """Stub implementation.

        Replace with Apache Tika / pypdf / python-docx / libreoffice-based extraction.
        """
        raw_text = path.read_text(encoding="utf-8", errors="ignore") if path.suffix.lower() in {".md", ".txt"} else ""
        pages = [PageArtifact(page_number=1, page_text=raw_text)] if raw_text else []
        return raw_text, pages
