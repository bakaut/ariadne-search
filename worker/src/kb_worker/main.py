from __future__ import annotations

import argparse
import sys

from kb_worker.config import Settings
from kb_worker.logging import setup_logging
from kb_worker.scheduler import WorkerScheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run-once")
    subparsers.add_parser("run-forever")
    serve = subparsers.add_parser("serve-dummy-api")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8010)
    serve.add_argument("--reload", action="store_true")
    return parser


def serve_dummy_api(host: str, port: int, reload: bool) -> None:
    import uvicorn

    uvicorn.run(
        "kb_worker.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve-dummy-api":
        serve_dummy_api(host=args.host, port=args.port, reload=args.reload)
        return

    settings = Settings()
    setup_logging(settings.log_level)

    scheduler = WorkerScheduler(settings)
    try:
        if args.command == "run-once":
            scheduler.run_once()
        elif args.command == "run-forever":
            scheduler.run_forever()
        else:
            parser.print_help()
            sys.exit(2)
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
