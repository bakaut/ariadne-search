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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

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
