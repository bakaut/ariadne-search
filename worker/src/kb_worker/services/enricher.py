from __future__ import annotations

from pathlib import Path

from kb_worker.models import ETLBundle, FileRecord
from kb_worker.services.classifier import DocumentClassifier


class MetadataEnricher:
    def __init__(self) -> None:
        self.classifier = DocumentClassifier()

    def enrich(self, bundle: ETLBundle, file_record: FileRecord) -> ETLBundle:
        path = file_record.path
        bundle.title = path.stem
        bundle.language = self.classifier.guess_language(path)
        bundle.metadata.update(
            {
                "filename": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": file_record.size_bytes,
                "modified_at": file_record.modified_at.isoformat(),
                "repo_hint": self._repo_hint(path),
                "path_parts": list(path.parts),
            }
        )
        return bundle

    @staticmethod
    def _repo_hint(path: Path) -> str | None:
        for parent in path.parents:
            if (parent / ".git").exists():
                return str(parent)
        return None
