from __future__ import annotations

import logging
from pathlib import Path

from kb_worker.config import Settings
from kb_worker.extractors.ocr import OCRExtractor
from kb_worker.extractors.office_pdf import OfficePdfExtractor
from kb_worker.extractors.text import TextExtractor
from kb_worker.models import AssetArtifact, ETLBundle, FileRecord
from kb_worker.parsers.code_parser import CodeParser
from kb_worker.services.chunker import Chunker
from kb_worker.services.classifier import DocumentClassifier
from kb_worker.services.embedder import OllamaEmbedder
from kb_worker.services.enricher import MetadataEnricher
from kb_worker.services.entity_extractor import EntityExtractor
from kb_worker.storage.neo4j_projection import Neo4jProjectionStore
from kb_worker.storage.postgres import PostgresStore

logger = logging.getLogger(__name__)


class ETLPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.classifier = DocumentClassifier()
        self.text_extractor = TextExtractor()
        self.office_pdf_extractor = OfficePdfExtractor()
        self.ocr_extractor = OCRExtractor()
        self.chunker = Chunker(settings)
        self.enricher = MetadataEnricher()
        self.entities = EntityExtractor()
        self.code_parser = CodeParser()
        self.embedder = OllamaEmbedder(settings)
        self.postgres = PostgresStore(settings)
        self.neo4j = Neo4jProjectionStore(settings)

    def close(self) -> None:
        self.neo4j.close()

    def process_file(self, file_record: FileRecord, force: bool = False) -> bool:
        if not force and not self.postgres.has_changed(file_record):
            logger.info("Skipping unchanged file: %s", file_record.path)
            return False

        bundle = ETLBundle(
            source_path=str(file_record.path),
            checksum=file_record.checksum,
            mime_type=file_record.mime_type,
        )
        document_type = self.classifier.classify(file_record)
        bundle.source_type = document_type.source_type

        try:
            self._extract_into_bundle(bundle, file_record, document_type)
            self.enricher.enrich(bundle, file_record)
            bundle.entities = self.entities.extract(bundle.chunks)
            self._embed(bundle)
            self.postgres.upsert_bundle(bundle)
            self.neo4j.project_bundle(bundle)
            logger.info("Indexed: %s", file_record.path)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to process %s", file_record.path)
            self.postgres.mark_failed(str(bundle.document_id), str(exc))
            return False

    def _extract_into_bundle(self, bundle: ETLBundle, file_record: FileRecord, document_type) -> None:
        path = file_record.path
        if document_type.source_type == "text_native":
            text = self.text_extractor.extract(path)
            bundle.chunks = self.chunker.chunk_text(text)
            return

        if document_type.source_type == "office_document":
            raw_text, pages = self.office_pdf_extractor.extract(path)
            bundle.pages = pages
            if pages:
                for page in pages:
                    bundle.chunks.extend(self.chunker.chunk_text(page.page_text, page_number=page.page_number))
            else:
                bundle.chunks = self.chunker.chunk_text(raw_text)
            return

        if document_type.source_type == "pdf_document":
            raw_text, pages = self.office_pdf_extractor.extract(path)
            bundle.pages = pages
            if document_type.requires_ocr and not pages:
                pages, ocr_blocks, ocr_text = self.ocr_extractor.extract_image(path)
                bundle.pages = pages
                bundle.ocr_blocks = ocr_blocks
                bundle.chunks = self.chunker.chunk_text(ocr_text, chunk_kind="ocr")
            else:
                for page in pages:
                    bundle.chunks.extend(self.chunker.chunk_text(page.page_text, page_number=page.page_number))
                if not bundle.chunks and raw_text:
                    bundle.chunks = self.chunker.chunk_text(raw_text)
            return

        if document_type.source_type == "image":
            bundle.assets.append(
                AssetArtifact(asset_type="image", asset_role="source_image", storage_path=str(path))
            )
            pages, ocr_blocks, ocr_text = self.ocr_extractor.extract_image(path)
            bundle.pages = pages
            bundle.ocr_blocks = ocr_blocks
            bundle.chunks = self.chunker.chunk_text(ocr_text, chunk_kind="ocr")
            return

        if document_type.source_type == "diagram":
            text = self.text_extractor.extract(path)
            bundle.chunks = self.chunker.chunk_text(text, chunk_kind="diagram")
            bundle.assets.append(
                AssetArtifact(asset_type="diagram_source", asset_role="diagram", storage_path=str(path))
            )
            return

        if document_type.source_type == "code":
            text = self.text_extractor.extract(path)
            bundle.language = self.classifier.guess_language(path)
            bundle.chunks = self.chunker.chunk_text(text, chunk_kind="code")
            bundle.symbols, bundle.symbol_links = self.code_parser.parse(path, bundle.language)
            return

        text = self.text_extractor.extract(path)
        bundle.chunks = self.chunker.chunk_text(text)

    def _embed(self, bundle: ETLBundle) -> None:
        vectors = self.embedder.embed_texts([chunk.content for chunk in bundle.chunks])
        for chunk, vector in zip(bundle.chunks, vectors, strict=False):
            chunk.embedding = vector
