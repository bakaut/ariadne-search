from __future__ import annotations

from fastapi import APIRouter, Depends

from kb_api.dependencies import get_search_service
from kb_api.services.search_service import SearchService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(search_service: SearchService = Depends(get_search_service)) -> dict[str, object]:
    return search_service.readiness()
