"""NotificationManager: decides *whether* and *how* to tell the player about something.

Inputs: recommendation lists from the assistants, plus direct ``notify`` calls (session,
route and recognition events). Output: ``Notification`` objects on ``Topic.NOTIFICATION``.

Anti-spam rules
* A recommendation that stays active is announced once, not on every frame.
* It is announced again when its priority escalates (e.g. elevated -> critical).
* A critical recommendation that stays active is repeated after the cooldown, as a reminder.
* A key that flickers on/off is not re-announced within the cooldown at the same priority.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from tdc.config.settings import NotificationSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import Notification, Priority, Recommendation

log = logging.getLogger(__name__)

CATEGORIES = ("healing", "mana", "party", "combat", "session", "recognition")

_TITLES = {Priority.NORMAL: "Info", Priority.ELEVATED: "Warning", Priority.CRITICAL: "Critical"}


class NotificationManager:
    def __init__(self, bus: EventBus, settings: Callable[[], NotificationSettings],
                 clock: Callable[[], float] = time.monotonic, history_size: int = 200) -> None:
        self._bus = bus
        self._settings = settings
        self._clock = clock
        self._active: dict[str, Priority] = {}          # currently active recommendation keys
        self._last_sent: dict[str, tuple[float, Priority]] = {}
        self.history: deque[Notification] = deque(maxlen=history_size)
        self._unsub = [bus.subscribe(Topic.RECOMMENDATIONS, self.on_recommendations)]

    def close(self) -> None:
        for u in self._unsub:
            u()

    # ------------------------------------------------------------------ inputs
    def on_recommendations(self, recs: list[Recommendation]) -> None:
        now = self._clock()
        cooldown = self._settings().cooldown_s
        current: dict[str, Recommendation] = {r.key: r for r in recs}
        for key, rec in current.items():
            previous = self._active.get(key)
            last = self._last_sent.get(key)
            if previous is None:
                # Newly active. Suppress flicker: same key+priority announced moments ago.
                if last and last[1] >= rec.priority and now - last[0] < cooldown:
                    continue
                self._emit(rec.key, rec.priority, rec.text, rec.reason, rec.category, now)
            elif rec.priority > previous:
                self._emit(rec.key, rec.priority, rec.text, rec.reason, rec.category, now)
            elif rec.priority == Priority.CRITICAL and last and now - last[0] >= max(cooldown, 1.0):
                self._emit(rec.key, rec.priority, rec.text, rec.reason, rec.category, now)
        self._active = {k: r.priority for k, r in current.items()}

    def notify(self, key: str, priority: Priority, text: str, reason: str = "",
               category: str = "session") -> Notification | None:
        """One-off event (session started, route milestone, recognition lost...)."""
        now = self._clock()
        last = self._last_sent.get(key)
        if last and last[1] >= priority and now - last[0] < self._settings().cooldown_s:
            return None
        return self._emit(key, priority, text, reason, category, now)

    # ------------------------------------------------------------------ filtering
    def allowed(self, priority: Priority, category: str) -> bool:
        s = self._settings()
        if not s.enabled:
            return False
        if s.quiet_mode and not (priority == Priority.CRITICAL and s.critical_ignores_quiet):
            return False
        if not {Priority.NORMAL: s.show_normal, Priority.ELEVATED: s.show_elevated,
                Priority.CRITICAL: s.show_critical}[priority]:
            return False
        cat_flag = "cat_session" if category in ("session", "route") else f"cat_{category}"
        return bool(getattr(s, cat_flag, True))

    def _sound_for(self, priority: Priority) -> str:
        s = self._settings()
        if not s.sound_enabled or s.volume == 0:
            return "none"
        if s.quiet_mode and priority != Priority.CRITICAL:
            return "none"
        return {Priority.NORMAL: s.sound_normal, Priority.ELEVATED: s.sound_elevated,
                Priority.CRITICAL: s.sound_critical}[priority]

    def _emit(self, key: str, priority: Priority, text: str, reason: str, category: str,
              now: float) -> Notification | None:
        if not self.allowed(priority, category):
            return None
        s = self._settings()
        n = Notification(
            key=key, priority=priority, title=_TITLES[priority], message=text if not reason else f"{text} — {reason}",
            category=category, sound=self._sound_for(priority), volume=s.volume, duration_ms=s.duration_ms,
        )
        self._last_sent[key] = (now, priority)
        self.history.append(n)
        log.debug("Notification %s [%s] %s", key, priority.name, n.message)
        self._bus.publish(Topic.NOTIFICATION, n)
        return n
