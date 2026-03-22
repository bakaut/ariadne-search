from __future__ import annotations

from kb_api.config import Settings
from kb_api.models import SearchRequest
from kb_api.services.query_classifier import QueryClassifier


def test_query_classifier_defaults_to_lexical_only_for_simple_query(settings: Settings) -> None:
    classifier = QueryClassifier(settings)

    plan = classifier.classify(SearchRequest(query="hello"))

    assert plan.lexical is True
    assert plan.exact is False
    assert plan.semantic is False
    assert plan.code is False
    assert plan.ocr is False
    assert plan.image is False
    assert plan.graph is True
    assert "graph context enabled for explanation and expansion" in plan.reasons


def test_query_classifier_enables_exact_semantic_and_code_branches(settings: Settings) -> None:
    classifier = QueryClassifier(settings)

    plan = classifier.classify(SearchRequest(query="find function in src/main.py"))

    assert plan.exact is True
    assert plan.semantic is True
    assert plan.code is True
    assert plan.lexical is True


def test_query_classifier_enables_ocr_and_respects_feature_flags(settings: Settings) -> None:
    classifier = QueryClassifier(Settings(app_env="test", enable_exact_search=False, enable_embeddings=False))

    plan = classifier.classify(SearchRequest(query="ocr in scanned pdf slide"))

    assert plan.ocr is True
    assert plan.exact is False
    assert plan.semantic is False


def test_query_classifier_enables_image_only_when_allowed(settings: Settings) -> None:
    classifier = QueryClassifier(Settings(app_env="test", enable_image_search=True))

    plan = classifier.classify(SearchRequest(query="diagram schema", include_image=True))

    assert plan.image is True
