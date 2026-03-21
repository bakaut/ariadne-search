from __future__ import annotations

import json
import logging
from typing import Iterable
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from kb_worker.config import Settings
from kb_worker.models import ETLBundle, FileRecord

logger = logging.getLogger(__name__)


class PostgresStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.schema = settings.postgres_schema

    def has_changed(self, file_record: FileRecord) -> bool:
        sql = f"""
            SELECT checksum
            FROM {self.schema}.documents
            WHERE source_path = %s
            LIMIT 1
        """
        with psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (str(file_record.path),))
                row = cur.fetchone()
                return not row or row["checksum"] != file_record.checksum

    def upsert_bundle(self, bundle: ETLBundle) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as conn:
            with conn.cursor() as cur:
                job_id = uuid4()
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.index_jobs (id, document_id, job_type, status, started_at, worker_id)
                    VALUES (%s, %s, %s, %s, now(), %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (str(job_id), str(bundle.document_id), "etl_index", "running", "worker"),
                )
                self._upsert_document(cur, bundle)
                self._replace_pages(cur, bundle)
                self._replace_assets(cur, bundle)
                self._replace_ocr_blocks(cur, bundle)
                self._replace_chunks(cur, bundle)
                self._replace_entities(cur, bundle)
                self._replace_symbols(cur, bundle)
                cur.execute(
                    f"""
                    UPDATE {self.schema}.index_jobs
                    SET status = %s, finished_at = now(), error_text = NULL
                    WHERE id = %s
                    """,
                    ("done", str(job_id)),
                )
            conn.commit()

    def mark_failed(self, document_id: str, error_text: str) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.index_jobs (id, document_id, job_type, status, started_at, finished_at, error_text, worker_id)
                    VALUES (%s, %s, %s, %s, now(), now(), %s, %s)
                    """,
                    (str(uuid4()), document_id, "etl_index", "failed", error_text[:4000], "worker"),
                )
            conn.commit()

    def _upsert_document(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(
            f"""
            INSERT INTO {self.schema}.documents (
              id, source_path, source_type, title, checksum, mime_type, language,
              indexed_at, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s, %s::jsonb)
            ON CONFLICT (source_path) DO UPDATE SET
              source_type = EXCLUDED.source_type,
              title = EXCLUDED.title,
              checksum = EXCLUDED.checksum,
              mime_type = EXCLUDED.mime_type,
              language = EXCLUDED.language,
              indexed_at = now(),
              status = EXCLUDED.status,
              metadata_json = EXCLUDED.metadata_json
            RETURNING id
            """,
            (
                str(bundle.document_id),
                bundle.source_path,
                bundle.source_type,
                bundle.title,
                bundle.checksum,
                bundle.mime_type,
                bundle.language,
                "indexed",
                json.dumps(bundle.metadata),
            ),
        )
        persisted_document_id = cur.fetchone()[0]
        bundle.document_id = persisted_document_id

    def _replace_pages(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(f"DELETE FROM {self.schema}.pages WHERE document_id = %s", (str(bundle.document_id),))
        for page in bundle.pages:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.pages (
                  id, document_id, page_number, page_label, page_text, render_path,
                  width, height, page_embedding_model, page_embedding, metadata_json
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s,
                  %s::jsonb
                )
                """,
                (
                    str(uuid4()),
                    str(bundle.document_id),
                    page.page_number,
                    str(page.page_number),
                    page.page_text,
                    page.render_path,
                    page.width,
                    page.height,
                    self.settings.text_embedding_model if page.page_embedding else None,
                    self._vector_literal(page.page_embedding),
                    json.dumps(page.metadata),
                ),
            )

    def _replace_assets(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(f"DELETE FROM {self.schema}.assets WHERE document_id = %s", (str(bundle.document_id),))
        for asset in bundle.assets:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.assets (
                  id, document_id, page_id, asset_type, asset_role, storage_path,
                  mime_type, caption_text, ocr_text, metadata_json
                ) VALUES (%s, %s, NULL, %s, %s, %s, NULL, %s, %s, %s::jsonb)
                """,
                (
                    str(uuid4()),
                    str(bundle.document_id),
                    asset.asset_type,
                    asset.asset_role,
                    asset.storage_path,
                    asset.caption_text,
                    asset.ocr_text,
                    json.dumps(asset.metadata),
                ),
            )

    def _replace_ocr_blocks(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(f"DELETE FROM {self.schema}.ocr_blocks WHERE document_id = %s", (str(bundle.document_id),))
        for block in bundle.ocr_blocks:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.ocr_blocks (
                  id, document_id, page_id, asset_id, block_index, text, confidence, bbox_json, metadata_json
                ) VALUES (%s, %s, NULL, NULL, %s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    str(uuid4()),
                    str(bundle.document_id),
                    block.block_index,
                    block.text,
                    block.confidence,
                    json.dumps(block.bbox_json or {}),
                    json.dumps(block.metadata),
                ),
            )

    def _replace_chunks(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(f"DELETE FROM {self.schema}.chunks WHERE document_id = %s", (str(bundle.document_id),))
        for chunk in bundle.chunks:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.chunks (
                  id, document_id, page_id, chunk_index, chunk_kind, heading, content,
                  token_count, char_count, start_offset, end_offset, content_hash,
                  embedding_model, embedding, metadata_json
                ) VALUES (
                  %s, %s, NULL, %s, %s, %s, %s,
                  %s, %s, %s, %s, md5(%s),
                  %s, %s, %s::jsonb
                )
                """,
                (
                    str(uuid4()),
                    str(bundle.document_id),
                    chunk.chunk_index,
                    chunk.chunk_kind,
                    chunk.heading,
                    chunk.content,
                    None,
                    len(chunk.content),
                    chunk.start_offset,
                    chunk.end_offset,
                    chunk.content,
                    self.settings.text_embedding_model if chunk.embedding else None,
                    self._vector_literal(chunk.embedding),
                    json.dumps(chunk.metadata),
                ),
            )

    def _replace_entities(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        for entity in bundle.entities:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.entities (
                  id, canonical_name, entity_type, normalized_name, confidence, description, metadata_json
                ) VALUES (%s, %s, %s, lower(%s), %s, NULL, '{{}}'::jsonb)
                ON CONFLICT (normalized_name, entity_type) DO UPDATE SET
                  canonical_name = EXCLUDED.canonical_name,
                  confidence = GREATEST({self.schema}.entities.confidence, EXCLUDED.confidence)
                RETURNING id
                """,
                (str(uuid4()), entity.canonical_name, entity.entity_type, entity.canonical_name, entity.confidence),
            )
            entity_id = cur.fetchone()[0]
            if entity.chunk_index is not None:
                cur.execute(
                    f"""
                    INSERT INTO {self.schema}.chunk_entities (
                      chunk_id, entity_id, mention_text, mention_count, start_offset, end_offset, confidence
                    )
                    SELECT c.id, %s, %s, 1, NULL, NULL, %s
                    FROM {self.schema}.chunks c
                    WHERE c.document_id = %s AND c.chunk_index = %s
                    ON CONFLICT DO NOTHING
                    """,
                    (entity_id, entity.mention_text, entity.confidence, str(bundle.document_id), entity.chunk_index),
                )

    def _replace_symbols(self, cur: psycopg.Cursor, bundle: ETLBundle) -> None:
        cur.execute(
            f"DELETE FROM {self.schema}.symbols WHERE file_id IN (SELECT id FROM {self.schema}.files WHERE document_id = %s)",
            (str(bundle.document_id),),
        )
        file_id = self._ensure_file(cur, bundle.source_path, str(bundle.document_id), bundle.language)
        for symbol in bundle.symbols:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.symbols (
                  id, file_id, repo_id, symbol_name, symbol_kind, fq_name,
                  signature, language, start_line, end_line, metadata_json
                ) VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    str(uuid4()),
                    file_id,
                    symbol.symbol_name,
                    symbol.symbol_kind,
                    symbol.fq_name,
                    symbol.signature,
                    symbol.language,
                    symbol.start_line,
                    symbol.end_line,
                    json.dumps(symbol.metadata),
                ),
            )
        cur.execute(
            f"DELETE FROM {self.schema}.symbol_links WHERE from_symbol_id IN (SELECT s.id FROM {self.schema}.symbols s WHERE s.file_id = %s)",
            (file_id,),
        )
        for link in bundle.symbol_links:
            cur.execute(
                f"""
                INSERT INTO {self.schema}.symbol_links (id, from_symbol_id, to_symbol_id, link_type, confidence, metadata_json)
                SELECT %s, s1.id, s2.id, %s, %s, %s::jsonb
                FROM {self.schema}.symbols s1
                JOIN {self.schema}.symbols s2 ON s2.fq_name = %s
                WHERE s1.fq_name = %s
                """,
                (
                    str(uuid4()),
                    link.link_type,
                    link.confidence,
                    json.dumps(link.metadata),
                    link.to_symbol_fq_name,
                    link.from_symbol_fq_name,
                ),
            )

    def _ensure_file(self, cur: psycopg.Cursor, source_path: str, document_id: str, language: str | None) -> str:
        cur.execute(
            f"""
            INSERT INTO {self.schema}.files (
              id, repo_id, document_id, relative_path, file_type, extension, language, checksum, metadata_json
            ) VALUES (%s, NULL, %s, %s, %s, %s, %s, '', '{{}}'::jsonb)
            ON CONFLICT (document_id, relative_path) DO UPDATE SET language = EXCLUDED.language
            RETURNING id
            """,
            (str(uuid4()), document_id, source_path, "file", source_path.rsplit(".", 1)[-1] if "." in source_path else "", language),
        )
        return cur.fetchone()[0]

    @staticmethod
    def _vector_literal(vector: list[float] | None) -> str | None:
        if not vector:
            return None
        return "[" + ",".join(f"{item:.8f}" for item in vector) + "]"
