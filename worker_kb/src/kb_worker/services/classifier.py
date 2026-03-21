from __future__ import annotations

from pathlib import Path

from kb_worker.models import DocumentType, FileRecord

TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".html", ".htm", ".json", ".yaml", ".yml", ".toml", ".log"}
OFFICE_EXTENSIONS = {".doc", ".docx", ".rtf", ".odt", ".pptx", ".xlsx"}
PDF_EXTENSIONS = {".pdf"}
CODE_EXTENSIONS = {".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".js", ".ts", ".go", ".java", ".sql", ".sh"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
DIAGRAM_EXTENSIONS = {".svg", ".drawio", ".puml", ".plantuml", ".mmd"}


class DocumentClassifier:
    def classify(self, file_record: FileRecord) -> DocumentType:
        suffix = file_record.path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            return DocumentType(source_type="text_native")
        if suffix in OFFICE_EXTENSIONS:
            return DocumentType(source_type="office_document", is_paged=True)
        if suffix in PDF_EXTENSIONS:
            requires_ocr = (file_record.mime_type or "").startswith("image/")
            return DocumentType(source_type="pdf_document", is_paged=True, requires_ocr=requires_ocr)
        if suffix in CODE_EXTENSIONS:
            return DocumentType(source_type="code", is_code=True)
        if suffix in IMAGE_EXTENSIONS:
            return DocumentType(source_type="image", is_image=True, requires_ocr=True)
        if suffix in DIAGRAM_EXTENSIONS:
            return DocumentType(source_type="diagram", is_diagram=True)
        return DocumentType(source_type="unknown")

    @staticmethod
    def guess_language(path: Path) -> str | None:
        mapping = {
            ".py": "python",
            ".c": "c",
            ".cc": "cpp",
            ".cpp": "cpp",
            ".cxx": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".java": "java",
            ".sql": "sql",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        return mapping.get(path.suffix.lower())
