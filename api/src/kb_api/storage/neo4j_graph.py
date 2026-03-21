from __future__ import annotations

import logging
from collections import defaultdict

from neo4j import GraphDatabase

from kb_api.config import Settings

logger = logging.getLogger(__name__)


class GraphContextStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def ping(self) -> bool:
        try:
            with self.driver.session(database=self.settings.neo4j_database) as session:
                return session.run("RETURN 1 AS ok").single()["ok"] == 1
        except Exception:  # noqa: BLE001
            logger.exception("Neo4j readiness check failed")
            return False

    def related_entities_by_source_path(self, source_paths: list[str], limit_per_doc: int = 5) -> dict[str, list[str]]:
        if not source_paths:
            return {}
        query = """
        UNWIND $source_paths AS source_path
        MATCH (d:Document {source_path: source_path})-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(e:Entity)
        RETURN source_path, collect(DISTINCT e.canonical_name)[0..$limit_per_doc] AS entities
        """
        with self.driver.session(database=self.settings.neo4j_database) as session:
            rows = session.run(query, source_paths=source_paths, limit_per_doc=limit_per_doc)
            result = defaultdict(list)
            for row in rows:
                result[row["source_path"]] = list(row["entities"] or [])
            return dict(result)
