"""Combat assistant: creature overview and *informational* combat hints.

It never selects targets, attacks or acts in any way. It only describes what the recognition
engine saw: how many creatures, which ones you marked as important, which are losing health
and how fast.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from tdc.config.settings import CombatSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, Priority, Recommendation


@dataclass
class CreatureInfo:
    slot: int
    name: str | None
    health: float | None
    priority: int
    targeted: bool
    hp_per_s: float | None      # negative = losing health
    eta_s: float | None         # estimated seconds until 0 % at the current rate (None if not falling)
    name_confidence: float


@dataclass
class CombatSnapshot:
    available: bool
    reason: str
    creatures: list[CreatureInfo]
    count: int
    targeted: CreatureInfo | None


def priority_of(name: str | None, priorities: dict[str, int]) -> int:
    if not name:
        return 0
    lower = name.lower()
    for n, p in priorities.items():
        if n.lower() == lower:
            return p
    return 0


class CombatAnalyzer:
    """Qt-free state machine: feed readings, get a snapshot and recommendations."""

    def __init__(self, settings: Callable[[], CombatSettings], priorities: Callable[[], dict[str, int]],
                 min_confidence: Callable[[], float]) -> None:
        self._settings = settings
        self._priorities = priorities
        self._min_conf = min_confidence
        self._history: dict[tuple[int, str], deque[tuple[float, float]]] = {}
        self.snapshot = CombatSnapshot(False, "no readings yet", [], 0, None)

    def reset(self) -> None:
        self._history.clear()
        self.snapshot = CombatSnapshot(False, "no readings yet", [], 0, None)

    def _rate(self, key: tuple[int, str], t: float, hp: float, window: float) -> float | None:
        h = self._history.setdefault(key, deque(maxlen=64))
        h.append((t, hp))
        while h and t - h[0][0] > window:
            h.popleft()
        if len(h) < 2 or h[-1][0] - h[0][0] < 0.5:
            return None
        return (h[-1][1] - h[0][1]) / (h[-1][0] - h[0][0])

    def update(self, r: FrameReading) -> tuple[CombatSnapshot, list[Recommendation]]:
        s = self._settings()
        mc = self._min_conf()
        if r.creatures_confidence < mc:
            self._history.clear()
            reason = "creature recognition below confidence threshold" if r.creatures else "no creature data"
            self.snapshot = CombatSnapshot(False, reason, [], 0, None)
            return self.snapshot, []

        prios = self._priorities()
        infos: list[CreatureInfo] = []
        seen = set()
        for c in r.creatures:
            name = c.name if c.name and c.name_confidence >= mc else None
            hp = c.health.value if c.health.value is not None and c.health.confidence >= mc else None
            key = (c.slot, name or "")
            seen.add(key)
            rate = self._rate(key, r.timestamp, hp, s.trend_window_s) if hp is not None else None
            eta = (hp / -rate) if (rate is not None and rate < -0.5 and hp) else None
            infos.append(CreatureInfo(c.slot, name, hp, priority_of(name, prios), c.targeted,
                                      round(rate, 1) if rate is not None else None,
                                      round(eta, 1) if eta is not None else None, c.name_confidence))
        for k in list(self._history):
            if k not in seen:
                del self._history[k]
        if s.sort_by_priority:
            infos.sort(key=lambda i: (-i.priority, i.slot))
        targeted = next((i for i in infos if i.targeted), None)
        self.snapshot = CombatSnapshot(True, "", infos, len(infos), targeted)
        return self.snapshot, self._recommend(infos, s, r.timestamp)

    @staticmethod
    def _recommend(infos: list[CreatureInfo], s: CombatSettings, ts: float) -> list[Recommendation]:
        recs: list[Recommendation] = []
        n = len(infos)
        if n >= s.crowd_critical:
            recs.append(Recommendation("combat.crowd", Priority.CRITICAL, f"{n} creatures on screen",
                                       f"crowd critical at {s.crowd_critical}", "combat", ts))
        elif n >= s.crowd_elevated:
            recs.append(Recommendation("combat.crowd", Priority.ELEVATED, f"{n} creatures on screen",
                                       f"crowd warning at {s.crowd_elevated}", "combat", ts))
        if s.alert_priority_creatures:
            important = [i for i in infos if i.name and i.priority >= s.priority_alert_min]
            if important:
                top = max(important, key=lambda i: i.priority)
                extra = " (your target)" if top.targeted else ""
                recs.append(Recommendation(f"combat.priority.{top.name.lower()}", Priority.NORMAL,
                                           f"Priority creature: {top.name}{extra}",
                                           f"priority {top.priority}", "combat", ts))
        return recs


class CombatAssistant:
    """Publishes combat recommendations. Combined with healing recommendations by ``RecommendationHub``."""

    def __init__(self, bus: EventBus, analyzer: CombatAnalyzer) -> None:
        self.bus = bus
        self.analyzer = analyzer
        self.last: list[Recommendation] = []
        self.updated_at = 0.0

    def on_reading(self, r: FrameReading) -> list[Recommendation]:
        _snap, recs = self.analyzer.update(r)
        self.last = recs
        self.updated_at = time.time()
        return recs
