"""Event-bus dispatcher that runs every subscriber callback on the Qt GUI thread."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal


class QtDispatcher(QObject):
    """Emitting from a worker thread to a QObject living in the GUI thread is queued by Qt;
    emitting from the GUI thread calls directly."""

    _call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.closed = False
        self._call.connect(self._run, Qt.AutoConnection)

    def __call__(self, fn: Callable[[], None]) -> None:
        if not self.closed:
            self._call.emit(fn)

    def _run(self, fn: Callable[[], None]) -> None:
        # Deliveries still queued when the app shuts down are dropped (their targets are gone).
        if not self.closed:
            fn()

    def close(self) -> None:
        self.closed = True
