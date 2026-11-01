"""Logging: rotating file on disk plus an in-memory ring buffer for the Diagnostics page."""

from __future__ import annotations

import logging
import logging.handlers
import threading
from collections import deque
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class MemoryLogHandler(logging.Handler):
    """Keeps the most recent log lines so the UI can show them without reading the file."""

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self._records: deque[str] = deque(maxlen=capacity)
        self._lock_ = threading.Lock()
        self.setFormatter(logging.Formatter(LOG_FORMAT, "%H:%M:%S"))
        self.error_count = 0
        self.warning_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:  # noqa: BLE001
            line = record.getMessage()
        with self._lock_:
            self._records.append(line)
            if record.levelno >= logging.ERROR:
                self.error_count += 1
            elif record.levelno >= logging.WARNING:
                self.warning_count += 1

    def lines(self, last: int | None = None) -> list[str]:
        with self._lock_:
            data = list(self._records)
        return data if last is None else data[-last:]


_memory_handler: MemoryLogHandler | None = None


def memory_handler() -> MemoryLogHandler:
    global _memory_handler
    if _memory_handler is None:
        _memory_handler = MemoryLogHandler()
    return _memory_handler


def configure_logging(log_file: Path | None, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Remove handlers we installed previously (re-configuration after settings change).
    for h in list(root.handlers):
        if getattr(h, "_tdc", False):
            root.removeHandler(h)

    handlers: list[logging.Handler] = [memory_handler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers.append(fh)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT, "%H:%M:%S"))
    console.setLevel(logging.WARNING)
    handlers.append(console)
    for h in handlers:
        h._tdc = True  # type: ignore[attr-defined]
        root.addHandler(h)


def set_level(level: str) -> None:
    logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))
