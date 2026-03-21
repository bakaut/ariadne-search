from __future__ import annotations

from pathlib import Path

from kb_worker.models import OCRBlockArtifact, PageArtifact


class OCRExtractor:
    def extract_image(self, path: Path) -> tuple[list[PageArtifact], list[OCRBlockArtifact], str]:
        """Stub OCR branch.

        Replace with OCRmyPDF / tesseract / PaddleOCR integration.
        """
        return [], [], ""
