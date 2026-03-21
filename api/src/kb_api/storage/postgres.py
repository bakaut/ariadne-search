from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from kb_api.config import Settings

logger = logging.getLogger(__name__)


class PostgresSearchStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.schema = settings.postgres_schema

    def ping(self) -> bool:
        try:
            with psycopg.connect(self.settings.postgres_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone()[0] == 1
        except Exception:  # noqa: BLE001
            logger.exception("PostgreSQL readiness check failed")
            return False

    def fts_search(self, query: str, top_k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        where_sql, params = self._document_filters(filters)
        sql = f"""
            SELECT
                c.id::text AS hit_id,
                'chunk' AS hit_kind,
                d.source_path,
                d.title,
                d.source_type,
                c.chunk_index,
                NULL::integer AS page_number,
                c.heading,
                left(c.content, 800) AS snippet,
                ts_rank_cd(c.tsv, websearch_to_tsquery('simple', %(query)s)) AS score,
                NULL::text AS symbol_name,
                NULL::text AS symbol_kind,
                d.language
            FROM {self.schema}.chunks c
            JOIN {self.schema}.documents d ON d.id = c.document_id
            WHERE c.tsv @@ websearch_to_tsquery('simple', %(query)s)
            {where_sql}
            ORDER BY score DESC, d.source_path ASC
            LIMIT %(top_k)s
        """
        params.update({"query": query, "top_k": top_k})
        return self._fetch(sql, params)

    def semantic_search(self, embedding: list[float], top_k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        where_sql, params = self._document_filters(filters)
        vector_literal = self._vector_literal(embedding)
        sql = f"""
            SELECT
                c.id::text AS hit_id,
                'chunk' AS hit_kind,
                d.source_path,
                d.title,
                d.source_type,
                c.chunk_index,
                NULL::integer AS page_number,
                c.heading,
                left(c.content, 800) AS snippet,
                (1 - (c.embedding <=> %(embedding)s::vector))::double precision AS score,
                NULL::text AS symbol_name,
                NULL::text AS symbol_kind,
                d.language
            FROM {self.schema}.chunks c
            JOIN {self.schema}.documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            {where_sql}
            ORDER BY c.embedding <=> %(embedding)s::vector ASC
            LIMIT %(top_k)s
        """
        params.update({"embedding": vector_literal, "top_k": top_k})
        return self._fetch(sql, params)

    def ocr_search(self, query: str, top_k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        where_sql, params = self._document_filters(filters)
        sql = f"""
            SELECT
                ob.id::text AS hit_id,
                'ocr_block' AS hit_kind,
                d.source_path,
                d.title,
                d.source_type,
                NULL::integer AS chunk_index,
                p.page_number,
                NULL::text AS heading,
                left(ob.text, 800) AS snippet,
                ts_rank_cd(ob.tsv, websearch_to_tsquery('simple', %(query)s)) AS score,
                NULL::text AS symbol_name,
                NULL::text AS symbol_kind,
                d.language
            FROM {self.schema}.ocr_blocks ob
            JOIN {self.schema}.documents d ON d.id = ob.document_id
            LEFT JOIN {self.schema}.pages p ON p.id = ob.page_id
            WHERE ob.tsv @@ websearch_to_tsquery('simple', %(query)s)
            {where_sql}
            ORDER BY score DESC, d.source_path ASC
            LIMIT %(top_k)s
        """
        params.update({"query": query, "top_k": top_k})
        return self._fetch(sql, params)

    def code_search(self, query: str, top_k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        where_sql, params = self._document_filters(filters)
        sql = f"""
            SELECT
                s.id::text AS hit_id,
                'symbol' AS hit_kind,
                d.source_path,
                d.title,
                d.source_type,
                NULL::integer AS chunk_index,
                NULL::integer AS page_number,
                NULL::text AS heading,
                left(coalesce(s.signature, s.fq_name, s.symbol_name), 800) AS snippet,
                CASE
                    WHEN lower(s.symbol_name) = lower(%(query)s) THEN 1.0
                    WHEN lower(s.fq_name) = lower(%(query)s) THEN 0.98
                    ELSE 0.80
                END::double precision AS score,
                s.symbol_name,
                s.symbol_kind,
                s.language
            FROM {self.schema}.symbols s
            JOIN {self.schema}.files f ON f.id = s.file_id
            JOIN {self.schema}.documents d ON d.id = f.document_id
            WHERE (
                lower(s.symbol_name) LIKE lower('%%' || %(query)s || '%%')
                OR lower(s.fq_name) LIKE lower('%%' || %(query)s || '%%')
                OR lower(coalesce(s.signature, '')) LIKE lower('%%' || %(query)s || '%%')
            )
            {where_sql}
            ORDER BY score DESC, d.source_path ASC
            LIMIT %(top_k)s
        """
        params.update({"query": query, "top_k": top_k})
        return self._fetch(sql, params)

    def exact_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not self.settings.enable_exact_search:
            return results
        for root in self.settings.source_roots:
            if not Path(root).exists():
                continue
            try:
                proc = subprocess.run(
                    [
                        "rg",
                        "--line-number",
                        "--with-filename",
                        "--max-count",
                        str(top_k),
                        query,
                        str(root),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                logger.warning("ripgrep is not installed in API container")
                return []
            if proc.returncode not in (0, 1):
                logger.warning("ripgrep exited with code %s: %s", proc.returncode, proc.stderr)
                continue
            for idx, line in enumerate(proc.stdout.splitlines()[:top_k]):
                path, line_no, snippet = self._parse_rg_line(line)
                if not path:
                    continue
                results.append(
                    {
                        "hit_id": f"exact:{idx}:{path}:{line_no}",
                        "hit_kind": "file_line",
                        "source_path": path,
                        "title": Path(path).name,
                        "source_type": "raw_file",
                        "chunk_index": None,
                        "page_number": None,
                        "heading": None,
                        "snippet": snippet,
                        "score": 1.0,
                        "symbol_name": None,
                        "symbol_kind": None,
                        "language": None,
                    }
                )
        return results[:top_k]

    def _document_filters(self, filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        source_types = filters.get("source_types") or []
        path_prefixes = filters.get("path_prefixes") or []
        languages = filters.get("languages") or []
        if source_types:
            clauses.append("AND d.source_type = ANY(%(source_types)s)")
            params["source_types"] = source_types
        if path_prefixes:
            clauses.append("AND (" + " OR ".join(
                f"d.source_path LIKE %(path_prefix_{i})s" for i, _ in enumerate(path_prefixes)
            ) + ")")
            for i, prefix in enumerate(path_prefixes):
                params[f"path_prefix_{i}"] = f"{prefix}%"
        if languages:
            clauses.append("AND coalesce(d.language, '') = ANY(%(languages)s)")
            params["languages"] = languages
        return ("\n            " + "\n            ".join(clauses)) if clauses else "", params

    def _fetch(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{item:.8f}" for item in vector) + "]"

    @staticmethod
    def _parse_rg_line(line: str) -> tuple[str | None, int | None, str]:
        parts = line.split(":", 2)
        if len(parts) < 3:
            return None, None, line
        path, line_no, snippet = parts
        try:
            return path, int(line_no), snippet.strip()
        except ValueError:
            return path, None, snippet.strip()
