from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from kb_api.models import SearchFilters, SearchHit, SearchPlan, SearchRequest


def build_service(monkeypatch, settings):
    import kb_api.services.search_service as service_module

    deps = {
        "store": Mock(),
        "graph": Mock(),
        "embedder": Mock(),
        "classifier": Mock(),
    }
    monkeypatch.setattr(service_module, "PostgresSearchStore", lambda cfg: deps["store"])
    monkeypatch.setattr(service_module, "GraphContextStore", lambda cfg: deps["graph"])
    monkeypatch.setattr(service_module, "QueryEmbedder", lambda cfg: deps["embedder"])
    monkeypatch.setattr(service_module, "QueryClassifier", lambda cfg: deps["classifier"])
    return service_module.SearchService(settings), deps


def make_row(**overrides):
    row = {
        "hit_id": "1",
        "hit_kind": "chunk",
        "source_path": "/tmp/doc.md",
        "title": "doc",
        "source_type": "text_native",
        "snippet": "snippet",
        "score": 1.0,
        "page_number": None,
        "chunk_index": 0,
        "symbol_name": None,
        "symbol_kind": None,
        "heading": None,
        "language": "markdown",
    }
    row.update(overrides)
    return row


def make_hit(**overrides) -> SearchHit:
    data = {
        "hit_id": "1",
        "channel": "lexical",
        "hit_kind": "chunk",
        "source_path": "/tmp/doc.md",
        "snippet": "snippet",
        "score": 1.0,
    }
    data.update(overrides)
    return SearchHit(**data)


def test_search_service_routes_enabled_branches_and_clamps_top_k(monkeypatch, settings) -> None:
    service, deps = build_service(monkeypatch, SettingsLike(settings, max_top_k=3))
    deps["classifier"].classify.return_value = SearchPlan(
        exact=True,
        lexical=True,
        semantic=True,
        ocr=True,
        code=True,
        image=True,
        graph=True,
        reasons=[],
    )
    deps["store"].exact_search.return_value = [make_row(hit_id="e1", score=1.0, chunk_index=None, hit_kind="file_line")]
    deps["store"].fts_search.return_value = [make_row(hit_id="l1", score=0.8)]
    deps["store"].code_search.return_value = [make_row(hit_id="c1", hit_kind="symbol", symbol_name="fn", symbol_kind="function", chunk_index=None, score=0.9)]
    deps["store"].ocr_search.return_value = [make_row(hit_id="o1", hit_kind="ocr_block", page_number=1, chunk_index=None, score=0.7)]
    deps["embedder"].embed_query.return_value = [0.1, 0.2]
    deps["store"].semantic_search.return_value = [make_row(hit_id="s1", score=0.6)]
    deps["graph"].related_entities_by_source_path.return_value = {"/tmp/doc.md": ["OpenAI"]}
    request = SearchRequest(
        query="find function in src/main.py",
        top_k=10,
        filters=SearchFilters(source_types=["text_native"], path_prefixes=["/tmp"], languages=["markdown"]),
        include_image=True,
    )

    response = service.search(request)

    deps["store"].exact_search.assert_called_once_with("find function in src/main.py", 3)
    filters = {"source_types": ["text_native"], "path_prefixes": ["/tmp"], "languages": ["markdown"]}
    deps["store"].fts_search.assert_called_once_with("find function in src/main.py", 3, filters)
    deps["store"].code_search.assert_called_once_with("find function in src/main.py", 3, filters)
    deps["store"].ocr_search.assert_called_once_with("find function in src/main.py", 3, filters)
    deps["embedder"].embed_query.assert_called_once_with("find function in src/main.py")
    deps["store"].semantic_search.assert_called_once_with([0.1, 0.2], 3, filters)
    deps["graph"].related_entities_by_source_path.assert_called_once()
    assert response.total == 3
    assert len(response.results) == 3


def test_search_service_skips_semantic_search_without_embedding(monkeypatch, settings) -> None:
    service, deps = build_service(monkeypatch, settings)
    deps["classifier"].classify.return_value = SearchPlan(
        exact=False,
        lexical=True,
        semantic=True,
        ocr=False,
        code=False,
        image=False,
        graph=False,
        reasons=[],
    )
    deps["store"].fts_search.return_value = [make_row()]
    deps["embedder"].embed_query.return_value = None

    response = service.search(SearchRequest(query="two words"))

    deps["store"].semantic_search.assert_not_called()
    assert response.total == 1


def test_search_service_tolerates_graph_errors(monkeypatch, settings) -> None:
    service, deps = build_service(monkeypatch, settings)
    deps["classifier"].classify.return_value = SearchPlan(
        exact=False,
        lexical=True,
        semantic=False,
        ocr=False,
        code=False,
        image=False,
        graph=True,
        reasons=[],
    )
    deps["store"].fts_search.return_value = [make_row()]
    deps["graph"].related_entities_by_source_path.side_effect = RuntimeError("neo4j down")

    response = service.search(SearchRequest(query="two words"))

    assert response.total == 1
    assert response.results[0].related_entities == []


def test_adapt_hits_applies_channel_boost_and_trims_snippet(monkeypatch, settings) -> None:
    service, _ = build_service(monkeypatch, settings)
    rows = [make_row(score=2.0, snippet=" " + ("x" * 950) + " ")]

    hits = service._adapt_hits("semantic", rows)

    assert len(hits) == 1
    assert hits[0].score == 2.0 * service.CHANNEL_BOOSTS["semantic"]
    assert len(hits[0].snippet) == 901
    assert hits[0].snippet.endswith("…")


def test_merge_hits_dedupes_and_tracks_channels(monkeypatch, settings) -> None:
    service, _ = build_service(monkeypatch, settings)
    lexical = make_hit(channel="lexical", snippet="short", score=0.8, chunk_index=0)
    semantic = make_hit(channel="semantic", snippet="longer snippet", score=0.9, chunk_index=0)

    merged = service._merge_hits([lexical, semantic], top_k=5)

    assert len(merged) == 1
    assert merged[0].score == 0.9
    assert merged[0].channel == "semantic"
    assert merged[0].snippet == "longer snippet"
    assert merged[0].metadata["channels"] == ["lexical"]


def test_apply_graph_context_uses_unique_paths_and_caps_score_boost(monkeypatch, settings) -> None:
    service, deps = build_service(monkeypatch, settings)
    hits = [
        make_hit(source_path="/tmp/a.md", score=1.0),
        make_hit(source_path="/tmp/a.md", score=1.0, hit_id="2"),
        make_hit(source_path="/tmp/b.md", score=1.0, hit_id="3"),
    ]
    deps["graph"].related_entities_by_source_path.return_value = {
        "/tmp/a.md": ["A", "B", "C", "D"],
        "/tmp/b.md": [],
    }

    service._apply_graph_context(hits)

    deps["graph"].related_entities_by_source_path.assert_called_once()
    paths = deps["graph"].related_entities_by_source_path.call_args.args[0]
    assert set(paths) == {"/tmp/a.md", "/tmp/b.md"}
    assert hits[0].related_entities == ["A", "B", "C", "D"]
    assert hits[0].score == 1.15
    assert hits[2].related_entities == []


def test_rerank_prefers_exact_then_symbols_then_related_entities(monkeypatch, settings) -> None:
    service, _ = build_service(monkeypatch, settings)
    exact = make_hit(hit_id="1", channel="exact", score=1.0)
    symbol = make_hit(hit_id="2", channel="lexical", score=1.0, symbol_name="hello")
    graphy = make_hit(hit_id="3", channel="lexical", score=1.0, related_entities=["a", "b"])

    ranked = service._rerank([graphy, symbol, exact], top_k=3)

    assert [hit.hit_id for hit in ranked] == ["1", "2", "3"]


def test_search_service_readiness_and_close(monkeypatch, settings) -> None:
    service, deps = build_service(monkeypatch, settings)
    deps["store"].ping.return_value = True
    deps["graph"].ping.return_value = False

    readiness = service.readiness()
    service.close()

    assert readiness == {"status": "ok", "checks": {"postgres": True, "neo4j": False}}
    deps["graph"].close.assert_called_once()
    deps["embedder"].close.assert_called_once()


class SettingsLike:
    def __init__(self, base, **overrides) -> None:
        self.__dict__.update(base.model_dump())
        self.__dict__.update(overrides)
