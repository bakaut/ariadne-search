from __future__ import annotations

import logging
import time

from kb_worker.config import Settings
from kb_worker.pipeline import ETLPipeline
from kb_worker.services.scanner import FileScanner

logger = logging.getLogger(__name__)


class WorkerScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scanner = FileScanner(settings)
        self.pipeline = ETLPipeline(settings)

    def close(self) -> None:
        self.pipeline.close()

    def run_once(self) -> int:
        processed = 0
        files = self.scanner.scan()
        for file_record in files:
            processed += int(self.pipeline.process_file(file_record))
        logger.info("Cycle complete, processed=%s", processed)
        return processed

    def run_forever(self) -> None:
        try:
            while True:
                self.run_once()
                time.sleep(self.settings.scheduler_interval_seconds)
        finally:
            self.close()
