from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KB_", case_sensitive=False)

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    api_title: str = "Knowledge Base Search API"
    api_version: str = "0.1.0"

    source_roots: list[Path] = Field(default_factory=lambda: [Path("/data/knowledge")])
    postgres_dsn: str = "postgresql://kb:kb@postgres:5432/kb"
    postgres_schema: str = "kb"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "knowledge"

    ollama_base_url: str = "http://ollama:11434"
    text_embedding_model: str = "embeddinggemma"
    embedding_dimensions: int = 768

    default_top_k: int = 10
    max_top_k: int = 50
    enable_exact_search: bool = True
    enable_embeddings: bool = True
    enable_graph_context: bool = True
    enable_image_search: bool = False

    @field_validator("source_roots", mode="before")
    @classmethod
    def parse_source_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return [Path(item.strip()) for item in value.split(",") if item.strip()]
        return value
