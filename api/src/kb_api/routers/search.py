from __future__ import annotations

from fastapi import APIRouter, Depends

from kb_api.dependencies import get_search_service
from kb_api.models import SearchRequest, SearchResponse
from kb_api.services.search_service import SearchService

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    return search_service.search(request)
