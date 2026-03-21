from __future__ import annotations

import argparse

import uvicorn

from kb_api.app import create_app
from kb_api.config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb-api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings()

    if args.command == "serve":
        uvicorn.run(
            "kb_api.app:create_app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            factory=True,
        )


if __name__ == "__main__":
    main()
