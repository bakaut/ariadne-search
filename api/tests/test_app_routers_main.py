from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from kb_api.app import create_app
from kb_api.dependencies import get_search_service
from kb_api.models import SearchPlan, SearchResponse


class FakeSearchService:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.closed = False

    def readiness(self):
        return {"status": "ok", "checks": {"postgres": True, "neo4j": True}}

    def search(self, request):
        return SearchResponse(
            query=request.query,
            plan=SearchPlan(
                exact=False,
                lexical=True,
                semantic=False,
                ocr=False,
                code=False,
                image=False,
                graph=False,
                reasons=["test"],
            ),
            total=0,
            results=[],
        )

    def close(self) -> None:
        self.closed = True


def test_get_search_service_returns_app_state_service() -> None:
    service = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(search_service=service)))

    assert get_search_service(request) is service


def test_create_app_wires_routes_lifespan_and_logging(monkeypatch, settings) -> None:
    import kb_api.app as app_module

    fake_service = FakeSearchService(settings)
    setup_logging = Mock()
    monkeypatch.setattr(app_module, "setup_logging", setup_logging)
    monkeypatch.setattr(app_module, "SearchService", lambda cfg: fake_service)

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ok", "checks": {"postgres": True, "neo4j": True}}
        assert client.post("/search", json={"query": "hello"}).json()["plan"]["lexical"] is True

    setup_logging.assert_called_once_with(settings.log_level)
    assert fake_service.closed is True


def test_main_runs_uvicorn_with_serve_args(monkeypatch, settings) -> None:
    import kb_api.main as main_module

    monkeypatch.setattr(main_module, "Settings", lambda: settings)
    monkeypatch.setattr(main_module, "build_parser", lambda: Mock(parse_args=Mock(return_value=Namespace(command="serve", host="127.0.0.1", port=9000, reload=True))))
    uvicorn_run = Mock()
    monkeypatch.setattr(main_module.uvicorn, "run", uvicorn_run)

    main_module.main()

    uvicorn_run.assert_called_once_with(
        "kb_api.app:create_app",
        host="127.0.0.1",
        port=9000,
        reload=True,
        factory=True,
    )


def test_build_parser_accepts_serve_command() -> None:
    from kb_api.main import build_parser

    parser = build_parser()

    args = parser.parse_args(["serve", "--host", "0.0.0.0", "--port", "8001", "--reload"])
    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8001
    assert args.reload is True
