from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from kb_worker.models import AssetArtifact, ChunkArtifact, ETLBundle, OCRBlockArtifact, PageArtifact, SymbolArtifact
from kb_worker.services.classifier import DocumentClassifier


def build_pipeline(monkeypatch, settings):
    import kb_worker.pipeline as pipeline_module

    deps = {
        "classifier": Mock(spec=DocumentClassifier),
        "text_extractor": Mock(),
        "office_pdf_extractor": Mock(),
        "ocr_extractor": Mock(),
        "chunker": Mock(),
        "enricher": Mock(),
        "entities": Mock(),
        "code_parser": Mock(),
        "embedder": Mock(),
        "postgres": Mock(),
        "neo4j": Mock(),
    }
    monkeypatch.setattr(pipeline_module, "DocumentClassifier", lambda: deps["classifier"])
    monkeypatch.setattr(pipeline_module, "TextExtractor", lambda: deps["text_extractor"])
    monkeypatch.setattr(pipeline_module, "OfficePdfExtractor", lambda: deps["office_pdf_extractor"])
    monkeypatch.setattr(pipeline_module, "OCRExtractor", lambda: deps["ocr_extractor"])
    monkeypatch.setattr(pipeline_module, "Chunker", lambda cfg: deps["chunker"])
    monkeypatch.setattr(pipeline_module, "MetadataEnricher", lambda: deps["enricher"])
    monkeypatch.setattr(pipeline_module, "EntityExtractor", lambda: deps["entities"])
    monkeypatch.setattr(pipeline_module, "CodeParser", lambda: deps["code_parser"])
    monkeypatch.setattr(pipeline_module, "OllamaEmbedder", lambda cfg: deps["embedder"])
    monkeypatch.setattr(pipeline_module, "PostgresStore", lambda cfg: deps["postgres"])
    monkeypatch.setattr(pipeline_module, "Neo4jProjectionStore", lambda cfg: deps["neo4j"])
    return pipeline_module.ETLPipeline(settings), deps


def test_process_file_skips_unchanged(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    deps["postgres"].has_changed.return_value = False

    processed = pipeline.process_file(make_file_record(path))

    assert processed is False
    deps["classifier"].classify.assert_not_called()
    deps["postgres"].upsert_bundle.assert_not_called()
    deps["neo4j"].project_bundle.assert_not_called()


def test_process_file_runs_happy_path(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    deps["postgres"].has_changed.return_value = True
    deps["classifier"].classify.return_value = SimpleNamespace(source_type="text_native")
    chunk = ChunkArtifact(chunk_index=0, content="chunk")

    def fake_extract(bundle, file_record, document_type):
        bundle.chunks = [chunk]

    pipeline._extract_into_bundle = Mock(side_effect=fake_extract)
    pipeline._embed = Mock()
    deps["entities"].extract.return_value = ["entity"]

    processed = pipeline.process_file(make_file_record(path))

    assert processed is True
    deps["enricher"].enrich.assert_called_once()
    deps["entities"].extract.assert_called_once_with([chunk])
    pipeline._embed.assert_called_once()
    deps["postgres"].upsert_bundle.assert_called_once()
    deps["neo4j"].project_bundle.assert_called_once()
    bundle = deps["postgres"].upsert_bundle.call_args.args[0]
    assert bundle.source_type == "text_native"
    assert bundle.entities == ["entity"]


def test_process_file_marks_failure_on_exception(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    deps["postgres"].has_changed.return_value = True
    deps["classifier"].classify.return_value = SimpleNamespace(source_type="text_native")
    pipeline._extract_into_bundle = Mock(side_effect=RuntimeError("boom"))

    processed = pipeline.process_file(make_file_record(path))

    assert processed is False
    deps["postgres"].mark_failed.assert_called_once()
    args = deps["postgres"].mark_failed.call_args.args
    assert args[0]
    assert "boom" in args[1]


def test_process_file_marks_failure_after_upsert(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    deps["postgres"].has_changed.return_value = True
    deps["classifier"].classify.return_value = SimpleNamespace(source_type="text_native")
    pipeline._extract_into_bundle = Mock(side_effect=lambda bundle, *_: bundle.chunks.append(ChunkArtifact(chunk_index=0, content="x")))
    pipeline._embed = Mock()
    deps["entities"].extract.return_value = []
    deps["neo4j"].project_bundle.side_effect = RuntimeError("graph failed")

    processed = pipeline.process_file(make_file_record(path))

    assert processed is False
    deps["postgres"].upsert_bundle.assert_called_once()
    deps["postgres"].mark_failed.assert_called_once()
    assert "graph failed" in deps["postgres"].mark_failed.call_args.args[1]


def test_extract_into_bundle_for_text_native(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(source_path=str(path))
    deps["text_extractor"].extract.return_value = "plain text"
    deps["chunker"].chunk_text.return_value = [ChunkArtifact(chunk_index=0, content="plain text")]

    pipeline._extract_into_bundle(bundle, make_file_record(path), SimpleNamespace(source_type="text_native"))

    deps["text_extractor"].extract.assert_called_once_with(path)
    deps["chunker"].chunk_text.assert_called_once_with("plain text")
    assert [chunk.content for chunk in bundle.chunks] == ["plain text"]


def test_extract_into_bundle_for_office_document_pages(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "slides.docx"
    path.write_text("ignored", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(source_path=str(path))
    pages = [PageArtifact(page_number=1, page_text="page one"), PageArtifact(page_number=2, page_text="page two")]
    deps["office_pdf_extractor"].extract.return_value = ("raw", pages)
    deps["chunker"].chunk_text.side_effect = [
        [ChunkArtifact(chunk_index=0, content="page one", page_number=1)],
        [ChunkArtifact(chunk_index=1, content="page two", page_number=2)],
    ]

    pipeline._extract_into_bundle(bundle, make_file_record(path), SimpleNamespace(source_type="office_document"))

    assert bundle.pages == pages
    assert [chunk.content for chunk in bundle.chunks] == ["page one", "page two"]
    assert deps["chunker"].chunk_text.call_args_list[0].kwargs == {"page_number": 1}
    assert deps["chunker"].chunk_text.call_args_list[1].kwargs == {"page_number": 2}


def test_extract_into_bundle_for_pdf_with_ocr(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(source_path=str(path))
    ocr_pages = [PageArtifact(page_number=1, page_text="ocr page")]
    ocr_blocks = [OCRBlockArtifact(text="ocr block", block_index=0)]
    deps["office_pdf_extractor"].extract.return_value = ("", [])
    deps["ocr_extractor"].extract_image.return_value = (ocr_pages, ocr_blocks, "ocr text")
    deps["chunker"].chunk_text.return_value = [ChunkArtifact(chunk_index=0, content="ocr text", chunk_kind="ocr")]

    pipeline._extract_into_bundle(
        bundle,
        make_file_record(path, mime_type="application/pdf"),
        SimpleNamespace(source_type="pdf_document", requires_ocr=True),
    )

    assert bundle.pages == ocr_pages
    assert bundle.ocr_blocks == ocr_blocks
    deps["chunker"].chunk_text.assert_called_once_with("ocr text", chunk_kind="ocr")


def test_extract_into_bundle_for_image(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(source_path=str(path))
    deps["ocr_extractor"].extract_image.return_value = ([], [], "visible text")
    deps["chunker"].chunk_text.return_value = [ChunkArtifact(chunk_index=0, content="visible text", chunk_kind="ocr")]

    pipeline._extract_into_bundle(bundle, make_file_record(path, mime_type="image/png"), SimpleNamespace(source_type="image"))

    assert bundle.assets == [AssetArtifact(asset_type="image", asset_role="source_image", storage_path=str(path))]
    deps["chunker"].chunk_text.assert_called_once_with("visible text", chunk_kind="ocr")


def test_extract_into_bundle_for_code(monkeypatch, settings, make_file_record, tmp_path) -> None:
    path = tmp_path / "main.py"
    path.write_text("def hello():\n    return 1\n", encoding="utf-8")
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(source_path=str(path))
    symbol = SymbolArtifact(
        symbol_name="hello",
        symbol_kind="function",
        fq_name="main.hello",
        language="python",
        start_line=1,
        end_line=1,
    )
    deps["text_extractor"].extract.return_value = "def hello():\n    return 1\n"
    deps["classifier"].guess_language.return_value = "python"
    deps["chunker"].chunk_text.return_value = [ChunkArtifact(chunk_index=0, content="def hello")]
    deps["code_parser"].parse.return_value = ([symbol], [])

    pipeline._extract_into_bundle(bundle, make_file_record(path), SimpleNamespace(source_type="code"))

    assert bundle.language == "python"
    assert bundle.symbols == [symbol]
    deps["code_parser"].parse.assert_called_once_with(path, "python")
    deps["chunker"].chunk_text.assert_called_once_with("def hello():\n    return 1\n", chunk_kind="code")


def test_embed_assigns_vectors_back_to_chunks(monkeypatch, settings) -> None:
    pipeline, deps = build_pipeline(monkeypatch, settings)
    bundle = ETLBundle(
        chunks=[
            ChunkArtifact(chunk_index=0, content="a"),
            ChunkArtifact(chunk_index=1, content="b"),
            ChunkArtifact(chunk_index=2, content="c"),
        ]
    )
    deps["embedder"].embed_texts.return_value = [[0.1], None]

    pipeline._embed(bundle)

    assert bundle.chunks[0].embedding == [0.1]
    assert bundle.chunks[1].embedding is None
    assert bundle.chunks[2].embedding is None


def test_close_only_closes_neo4j(monkeypatch, settings) -> None:
    pipeline, deps = build_pipeline(monkeypatch, settings)

    pipeline.close()

    deps["neo4j"].close.assert_called_once()
    deps["postgres"].close.assert_not_called()
