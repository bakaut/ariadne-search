from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KB_", case_sensitive=False)

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    source_roots: list[Path] = Field(default_factory=lambda: [Path("/data/knowledge")])
    include_hidden: bool = False
    follow_symlinks: bool = False
    supported_extensions: set[str] = Field(
        default_factory=lambda: {
            ".md", ".txt", ".rst", ".html", ".htm", ".json", ".yaml", ".yml", ".toml", ".log",
            ".pdf", ".doc", ".docx", ".rtf", ".odt", ".pptx", ".xlsx",
            ".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".js", ".ts", ".go", ".java", ".sql", ".sh",
            ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".svg", ".drawio", ".puml", ".plantuml", ".mmd",
        }
    )

    chunk_size_chars: int = 2000
    chunk_overlap_chars: int = 250
    scheduler_interval_seconds: int = 300

    postgres_dsn: str = "postgresql://kb:kb@postgres:5432/kb"
    postgres_schema: str = "kb"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "knowledge"

    ollama_base_url: str = "http://ollama:11434"
    text_embedding_model: str = "embeddinggemma"
    image_embedding_model: str = ""
    embedding_dimensions: int = 768
    enable_embeddings: bool = False
    enable_image_embeddings: bool = False
    enable_neo4j_projection: bool = True

    @field_validator("source_roots", mode="before")
    @classmethod
    def parse_source_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return [Path(item.strip()) for item in value.split(",") if item.strip()]
        return value
