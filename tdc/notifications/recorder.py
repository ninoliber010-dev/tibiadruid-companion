"""Records every notification that was actually shown into ``event_log`` (local only).

Only notifications are stored — not every frame's recommendations — so the log reflects what
the player was told, without flooding the database. Phase 6 links rows to hunting sessions.
"""

from __future__ import annotations

import logging
from typing import Callable

from tdc.core.events import EventBus, Topic
from tdc.core.models import Notification
from tdc.storage.database import Database

log = logging.getLogger(__name__)
MAX_ROWS = 50_000


class EventRecorder:
    def __init__(self, db: Database, bus: EventBus, session_id: Callable[[], int | None] = lambda: None) -> None:
        self.db = db
        self._session_id = session_id
        self._writes = 0
        self._unsub = bus.subscribe(Topic.NOTIFICATION, self.record)

    def record(self, n: Notification) -> None:
        try:
            self.db.execute(
                "INSERT INTO event_log(session_id, ts, category, priority, message) VALUES (?,?,?,?,?)",
                (self._session_id(), n.timestamp, n.category, int(n.priority), n.message),
            )
            self._writes += 1
            if self._writes % 1000 == 0:
                self.prune()
        except Exception:  # noqa: BLE001 - recording must never break notifications
            log.exception("Could not record notification")

    def prune(self, keep: int = MAX_ROWS) -> None:
        self.db.execute(
            "DELETE FROM event_log WHERE id <= (SELECT id FROM event_log ORDER BY id DESC LIMIT 1 OFFSET ?)",
            (keep,),
        )

    def recent(self, limit: int = 100) -> list[dict]:
        rows = self.db.query("SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._unsub()
