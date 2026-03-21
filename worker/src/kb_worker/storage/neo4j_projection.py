from __future__ import annotations

import logging

from neo4j import GraphDatabase

from kb_worker.config import Settings
from kb_worker.models import ETLBundle

logger = logging.getLogger(__name__)


class Neo4jProjectionStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def project_bundle(self, bundle: ETLBundle) -> None:
        if not self.settings.enable_neo4j_projection:
            return
        with self.driver.session(database=self.settings.neo4j_database) as session:
            session.execute_write(self._project_tx, bundle)

    @staticmethod
    def _project_tx(tx, bundle: ETLBundle) -> None:
        tx.run(
            """
            MERGE (d:Document {doc_id: $doc_id})
            SET d.title = $title,
                d.source_path = $source_path,
                d.source_type = $source_type,
                d.language = $language
            """,
            doc_id=str(bundle.document_id),
            title=bundle.title,
            source_path=bundle.source_path,
            source_type=bundle.source_type,
            language=bundle.language,
        )

        for page in bundle.pages:
            tx.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (p:Page {page_id: $page_id})
                SET p.page_number = $page_number,
                    p.render_path = $render_path
                MERGE (d)-[:HAS_PAGE]->(p)
                """,
                doc_id=str(bundle.document_id),
                page_id=f"{bundle.document_id}:{page.page_number}",
                page_number=page.page_number,
                render_path=page.render_path,
            )

        for chunk in bundle.chunks:
            tx.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (c:Chunk {chunk_id: $chunk_id})
                SET c.chunk_index = $chunk_index,
                    c.chunk_kind = $chunk_kind,
                    c.heading = $heading
                MERGE (d)-[:HAS_CHUNK]->(c)
                """,
                doc_id=str(bundle.document_id),
                chunk_id=f"{bundle.document_id}:{chunk.chunk_index}",
                chunk_index=chunk.chunk_index,
                chunk_kind=chunk.chunk_kind,
                heading=chunk.heading,
            )
            if chunk.page_number is not None:
                tx.run(
                    """
                    MATCH (p:Page {page_id: $page_id})
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MERGE (p)-[:HAS_CHUNK]->(c)
                    """,
                    page_id=f"{bundle.document_id}:{chunk.page_number}",
                    chunk_id=f"{bundle.document_id}:{chunk.chunk_index}",
                )

        for entity in bundle.entities:
            tx.run(
                """
                MERGE (e:Entity {entity_key: $entity_key})
                SET e.entity_id = $entity_key,
                    e.canonical_name = $canonical_name,
                    e.entity_type = $entity_type
                """,
                entity_key=f"{entity.entity_type}:{entity.canonical_name.lower()}",
                canonical_name=entity.canonical_name,
                entity_type=entity.entity_type,
            )
            if entity.chunk_index is not None:
                tx.run(
                    """
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MATCH (e:Entity {entity_key: $entity_key})
                    MERGE (c)-[:MENTIONS]->(e)
                    """,
                    chunk_id=f"{bundle.document_id}:{entity.chunk_index}",
                    entity_key=f"{entity.entity_type}:{entity.canonical_name.lower()}",
                )

        for symbol in bundle.symbols:
            tx.run(
                """
                MERGE (s:Symbol {fq_name: $fq_name})
                SET s.symbol_id = $fq_name,
                    s.symbol_name = $symbol_name,
                    s.symbol_kind = $symbol_kind,
                    s.language = $language
                """,
                fq_name=symbol.fq_name,
                symbol_name=symbol.symbol_name,
                symbol_kind=symbol.symbol_kind,
                language=symbol.language,
            )
        for link in bundle.symbol_links:
            tx.run(
                """
                MATCH (a:Symbol {fq_name: $from_fq_name})
                MATCH (b:Symbol {fq_name: $to_fq_name})
                MERGE (a)-[:CALLS]->(b)
                """,
                from_fq_name=link.from_symbol_fq_name,
                to_fq_name=link.to_symbol_fq_name,
            )
