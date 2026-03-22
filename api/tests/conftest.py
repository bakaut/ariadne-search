from __future__ import annotations

from pathlib import Path

import pytest

from kb_api.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        source_roots=[tmp_path],
        postgres_dsn="postgresql://kb:kb@localhost:5432/kb",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        ollama_base_url="http://localhost:11434",
        enable_exact_search=True,
        enable_embeddings=True,
        enable_graph_context=True,
        enable_image_search=False,
    )
