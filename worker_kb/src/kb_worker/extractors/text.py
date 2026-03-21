from __future__ import annotations

from pathlib import Path


class TextExtractor:
    def extract(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")
