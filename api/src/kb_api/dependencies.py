from __future__ import annotations

from fastapi import Request

from kb_api.services.search_service import SearchService


def get_search_service(request: Request) -> SearchService:
    return request.app.state.search_service
