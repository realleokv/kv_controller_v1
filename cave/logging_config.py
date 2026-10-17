# logging_config.py
"""Structured, privacy-aware logging configuration for CAVE."""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from threading import Lock
from typing import Any, Deque, Dict, List


class MemoryErrorRingHandler(logging.Handler):
    """Keeps recent warning and error log entries in memory for the dashboard."""

    def __init__(self, max_entries: int = 50) -> None:
        super().__init__(level=logging.WARNING)
        self._entries: Deque[Dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": self.format(record),
        }
        with self._lock:
            self._entries.appendleft(entry)

    def get_recent(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_ring_handler = MemoryErrorRingHandler()


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> MemoryErrorRingHandler:
    """Configure console, rotating file, and in-memory ring buffer logging."""
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "cave.log")

    root_logger = logging.getLogger("cave")
    root_logger.setLevel(level)

    if not root_logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        _ring_handler.setFormatter(formatter)
        root_logger.addHandler(_ring_handler)

    return _ring_handler


def get_error_ring() -> MemoryErrorRingHandler:
    """Return the global in-memory error buffer for dashboard inspection."""
    return _ring_handler