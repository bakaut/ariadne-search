from __future__ import annotations

from argparse import Namespace
from unittest.mock import Mock

import pytest

from kb_worker.config import Settings
from kb_worker.scheduler import WorkerScheduler


def build_scheduler(monkeypatch, settings):
    import kb_worker.scheduler as scheduler_module

    scanner = Mock()
    pipeline = Mock()
    monkeypatch.setattr(scheduler_module, "FileScanner", lambda cfg: scanner)
    monkeypatch.setattr(scheduler_module, "ETLPipeline", lambda cfg: pipeline)
    return scheduler_module.WorkerScheduler(settings), scanner, pipeline


def test_scheduler_run_once_counts_processed(monkeypatch, settings) -> None:
    scheduler, scanner, pipeline = build_scheduler(monkeypatch, settings)
    scanner.scan.return_value = ["a", "b", "c"]
    pipeline.process_file.side_effect = [True, False, True]

    processed = scheduler.run_once()

    assert processed == 2


def test_scheduler_run_forever_sleeps_and_closes(monkeypatch, settings) -> None:
    scheduler, _, _ = build_scheduler(monkeypatch, settings)
    scheduler.run_once = Mock()
    scheduler.close = Mock()

    def fake_sleep(seconds: int) -> None:
        raise RuntimeError(f"sleep:{seconds}")

    import kb_worker.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match=f"sleep:{settings.scheduler_interval_seconds}"):
        scheduler.run_forever()

    scheduler.run_once.assert_called_once()
    scheduler.close.assert_called_once()


def test_build_parser_accepts_supported_commands() -> None:
    from kb_worker.main import build_parser

    parser = build_parser()

    assert parser.parse_args(["run-once"]).command == "run-once"
    assert parser.parse_args(["run-forever"]).command == "run-forever"


def test_main_run_once_calls_scheduler_and_closes(monkeypatch, settings) -> None:
    import kb_worker.main as main_module

    scheduler = Mock()
    monkeypatch.setattr(main_module, "Settings", lambda: settings)
    monkeypatch.setattr(main_module, "setup_logging", Mock())
    monkeypatch.setattr(main_module, "WorkerScheduler", lambda cfg: scheduler)
    monkeypatch.setattr(main_module, "build_parser", lambda: Mock(parse_args=Mock(return_value=Namespace(command="run-once"))))

    main_module.main()

    scheduler.run_once.assert_called_once()
    scheduler.close.assert_called_once()


def test_main_run_forever_currently_double_closes_when_scheduler_does_so_too(monkeypatch, settings) -> None:
    import kb_worker.main as main_module

    class FakeScheduler:
        def __init__(self) -> None:
            self.close = Mock()

        def run_forever(self) -> None:
            try:
                raise RuntimeError("stop")
            finally:
                self.close()

    scheduler = FakeScheduler()
    monkeypatch.setattr(main_module, "Settings", lambda: settings)
    monkeypatch.setattr(main_module, "setup_logging", Mock())
    monkeypatch.setattr(main_module, "WorkerScheduler", lambda cfg: scheduler)
    monkeypatch.setattr(main_module, "build_parser", lambda: Mock(parse_args=Mock(return_value=Namespace(command="run-forever"))))

    with pytest.raises(RuntimeError, match="stop"):
        main_module.main()

    assert scheduler.close.call_count == 2
