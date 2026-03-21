from __future__ import annotations

import re

from kb_api.config import Settings
from kb_api.models import SearchPlan, SearchRequest


class QueryClassifier:
    CODE_HINTS = {
        "function",
        "class",
        "method",
        "import",
        "module",
        "symbol",
        "repo",
        "file",
        ".py",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".go",
        ".ts",
        ".js",
        "dockerfile",
        "yaml",
    }
    OCR_HINTS = {"scan", "scanned", "ocr", "screenshot", "pdf", "slide", "image text"}
    IMAGE_HINTS = {"image", "picture", "drawing", "diagram", "schema", "screenshot", "figure"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def classify(self, request: SearchRequest) -> SearchPlan:
        q = request.query.lower()
        reasons: list[str] = []
        has_path_hint = "/" in q or "\\" in q or re.search(r"\b\w+\.\w+\b", q) is not None
        has_regex_hint = bool(re.search(r"[\[\]\(\)\*\+\?\|]", request.query))
        code = request.include_code and any(hint in q for hint in self.CODE_HINTS)
        ocr = request.include_ocr and any(hint in q for hint in self.OCR_HINTS)
        image = request.include_image and self.settings.enable_image_search and any(
            hint in q for hint in self.IMAGE_HINTS
        )
        exact = request.include_exact and self.settings.enable_exact_search and (has_path_hint or has_regex_hint)
        semantic = request.include_semantic and self.settings.enable_embeddings and len(request.query.split()) >= 2
        graph = request.include_graph_context and self.settings.enable_graph_context
        lexical = True

        if exact:
            reasons.append("query looks path-like or regex-like, enabling exact search")
        if code:
            reasons.append("query contains code-oriented hints")
        if ocr:
            reasons.append("query mentions scanned/image-like material")
        if semantic:
            reasons.append("semantic search enabled for multi-word query")
        if graph:
            reasons.append("graph context enabled for explanation and expansion")
        if image:
            reasons.append("visual search enabled by query hints")
        if not reasons:
            reasons.append("defaulting to lexical search")

        return SearchPlan(
            exact=exact,
            lexical=lexical,
            semantic=semantic,
            ocr=ocr,
            code=code,
            image=image,
            graph=graph,
            reasons=reasons,
        )
