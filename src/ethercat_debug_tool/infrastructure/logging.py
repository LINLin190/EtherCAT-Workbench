from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..models import LogRecord


class ApplicationLogger:
    """Persistent rotating JSONL log, including all write audit records."""

    def __init__(self, directory: Path | None = None) -> None:
        root = directory or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EtherCATWorkbench" / "logs"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "ethercat-workbench.jsonl"
        self._logger = logging.getLogger(f"ethercat-workbench.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = RotatingFileHandler(self.path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

    def write(self, record: LogRecord) -> None:
        self._logger.info(
            json.dumps(
                {
                    "timestamp": record.timestamp,
                    "level": record.level,
                    "source": record.source,
                    "event": record.event,
                    "message": record.message,
                    "details": record.details,
                },
                ensure_ascii=False,
                default=str,
            )
        )
