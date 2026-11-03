"""A small thread-safe publish/subscribe event bus.

The bus itself is Qt-free. A *dispatcher* decides where subscriber callbacks run:
by default they run synchronously in the publishing thread (used in tests); the desktop
app installs a dispatcher that marshals every delivery onto the Qt GUI thread, so
background workers can publish safely without touching widgets.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[[Any], None]
Dispatcher = Callable[[Callable[[], None]], None]


class Topic(str, Enum):
    FRAME_READING = "recognition.frame"            # FrameReading (raw)
    READING_VALIDATED = "recognition.validated"    # FrameReading (confidence-gated)
    RECOGNITION_STATUS = "recognition.status"      # RecognitionStatus
    RECOMMENDATIONS = "assistants.recommendations"  # list[Recommendation]
    NOTIFICATION = "notifications.show"            # Notification
    CONFIG_CHANGED = "config.changed"              # section name (str)
    PROFILE_CHANGED = "profile.changed"            # HuntMode
    SESSION_UPDATED = "session.updated"            # session snapshot
    ROUTE_CHANGED = "route.changed"                # route id
    RULES_CHANGED = "healing.rules_changed"        # profile id
    REGIONS_CHANGED = "recognition.regions_changed"  # region kind or None
    APP_ERROR = "app.error"                        # str


def _direct(fn: Callable[[], None]) -> None:
    fn()


class EventBus:
    def __init__(self, dispatcher: Dispatcher | None = None) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._dispatcher: Dispatcher = dispatcher or _direct

    def set_dispatcher(self, dispatcher: Dispatcher) -> None:
        self._dispatcher = dispatcher

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    def subscribe(self, topic: Topic | str, handler: Handler) -> Callable[[], None]:
        """Register ``handler``; returns a function that unsubscribes it."""
        key = topic.value if isinstance(topic, Topic) else topic
        with self._lock:
            self._subs[key].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subs[key].remove(handler)
                except ValueError:
                    pass

        return unsubscribe

    def publish(self, topic: Topic | str, payload: Any = None) -> None:
        key = topic.value if isinstance(topic, Topic) else topic
        with self._lock:
            handlers = list(self._subs.get(key, ()))
        for handler in handlers:
            self._dispatcher(lambda h=handler: self._safe_call(key, h, payload))

    @staticmethod
    def _safe_call(key: str, handler: Handler, payload: Any) -> None:
        # One faulty subscriber must never take down the others or the publisher.
        try:
            handler(payload)
        except Exception:  # noqa: BLE001
            log.exception("Event handler for %s failed", key)

    def subscriber_count(self, topic: Topic | str) -> int:
        key = topic.value if isinstance(topic, Topic) else topic
        with self._lock:
            return len(self._subs.get(key, ()))
