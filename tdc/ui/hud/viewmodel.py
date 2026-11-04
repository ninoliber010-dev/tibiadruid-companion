"""HUD view-model: turns events into a plain ``HudState`` the HUD window paints.

Qt-free so it can be unit-tested. Rules it enforces:
* a value below the confidence threshold is shown as unavailable, with the reason;
* if no reading arrived recently the whole display is marked stale (no frozen numbers);
* status colours come from the user's own healing thresholds, not hard-coded numbers.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from tdc.core.models import (
    FrameReading, HuntMode, Measurement, Priority, RecognitionState, RecognitionStatus, Recommendation,
)
from tdc.storage.repositories import HealingRule

# Level names map to colours in the HUD: ok=green, low=blue, warn=amber, critical=red, unknown=grey
LEVEL_FOR_PRIORITY = {Priority.NORMAL: "low", Priority.ELEVATED: "warn", Priority.CRITICAL: "critical"}


@dataclass
class BarState:
    label: str
    value: float | None = None
    text: str = "—"
    level: str = "unknown"
    confidence: float | None = None
    note: str = ""


@dataclass
class CreatureRow:
    name: str
    health: float | None
    health_text: str
    trend: str = ""   # "↓", "↑" or ""
    priority: int = 0
    targeted: bool = False


@dataclass
class RecRow:
    priority: Priority
    text: str
    reason: str


@dataclass
class HudState:
    mode: HuntMode
    profile_name: str
    source: str                 # "Simulation", "Live", "Not running", ...
    source_level: str           # ok / warn / critical / unknown
    health: BarState
    mana: BarState
    partner: BarState | None
    creatures: list[CreatureRow] = field(default_factory=list)
    creature_summary: str = "—"
    creature_note: str = ""
    recommendations: list[RecRow] = field(default_factory=list)
    monitoring_time: str = "—"
    xp_per_hour: str = "—"
    xp_note: str = "Session analytics arrive in Phase 6"
    route: str = "—"
    stale: bool = True
    advice_note: str = "Waiting for readings"


def pct(value: float) -> str:
    """Whole percent, rounded down (59.6 -> 59 %) so text never contradicts a threshold."""
    return f"{math.floor(value + 1e-9):d}%"


def _fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class HudViewModel:
    def __init__(
        self,
        min_confidence: Callable[[], float],
        rules: Callable[[], list[HealingRule]],
        mode: Callable[[], HuntMode],
        profile_name: Callable[[], str],
        partner_name: Callable[[], str] = lambda: "",
        stale_after: Callable[[], float] = lambda: 2.0,
        clock: Callable[[], float] = time.time,
        priorities: Callable[[], dict[str, int]] = lambda: {},
        sort_by_priority: Callable[[], bool] = lambda: False,
    ) -> None:
        self._priorities = priorities
        self._sort_by_priority = sort_by_priority
        self._min_conf = min_confidence
        self._rules = rules
        self._mode = mode
        self._profile_name = profile_name
        self._partner_name = partner_name
        self._stale_after = stale_after
        self._clock = clock
        self.reading: FrameReading | None = None
        self.received_at: float | None = None
        self.recommendations: list[Recommendation] = []
        self.status = RecognitionStatus(RecognitionState.STOPPED, "Recognition not running")
        self.monitoring_since: float | None = None
        self._prev_creature_hp: dict[tuple[int, str], float] = {}
        self._trends: dict[tuple[int, str], str] = {}
        self.dirty = True

    # ------------------------------------------------------------------ inputs
    def on_reading(self, reading: FrameReading) -> None:
        now = self._clock()
        if self.monitoring_since is None:
            self.monitoring_since = now
        self._update_trends(reading)
        self.reading = reading
        self.received_at = now
        self.dirty = True

    def on_recommendations(self, recs: list[Recommendation]) -> None:
        self.recommendations = list(recs)
        self.dirty = True

    def on_status(self, status: RecognitionStatus) -> None:
        self.status = status
        if status.state == RecognitionState.STOPPED:
            self.monitoring_since = None
            self.reading = None
            self.recommendations = []
            self._prev_creature_hp.clear()
            self._trends.clear()
        self.dirty = True

    def _update_trends(self, reading: FrameReading) -> None:
        seen = {}
        for c in reading.creatures:
            if c.health.value is None or not c.name:
                continue
            key = (c.slot, c.name)
            prev = self._prev_creature_hp.get(key)
            if prev is not None:
                delta = c.health.value - prev
                self._trends[key] = "↓" if delta < -1 else "↑" if delta > 1 else self._trends.get(key, "")
            seen[key] = c.health.value
        self._prev_creature_hp = seen
        self._trends = {k: v for k, v in self._trends.items() if k in seen}

    # ------------------------------------------------------------------ output
    def is_stale(self) -> bool:
        if self.received_at is None:
            return True
        return self._clock() - self.received_at > self._stale_after()

    def _level(self, value: float, target: str, resource: str) -> str:
        matched = [r.priority for r in self._rules()
                   if r.enabled and r.target == target and r.resource == resource and value < r.threshold]
        if not matched:
            return "ok"
        return LEVEL_FOR_PRIORITY[Priority(max(matched))]

    def _bar(self, label: str, m: Measurement | None, target: str, resource: str, stale: bool) -> BarState:
        if stale or m is None:
            return BarState(label, note="no recent reading")
        if m.value is None:
            return BarState(label, note=m.reason or "unavailable")
        if m.confidence < self._min_conf():
            return BarState(label, confidence=m.confidence,
                            note=f"low confidence ({m.confidence:.0%})")
        return BarState(label, value=m.value, text=pct(m.value), level=self._level(m.value, target, resource),
                        confidence=m.confidence)

    def state(self) -> HudState:
        stale = self.is_stale()
        r = self.reading
        mode = self._mode()
        partner_label = self._partner_name() or "Partner"

        health = self._bar("Health", r.health if r else None, "self", "health", stale)
        mana = self._bar("Mana", r.mana if r else None, "self", "mana", stale)
        partner = None
        if mode == HuntMode.DUO:
            partner = self._bar(partner_label, r.partner_health if r else None, "partner", "health", stale)

        creatures: list[CreatureRow] = []
        summary, note = "—", ""
        if r is None or stale:
            note = "no recent reading"
        elif r.creatures_confidence < self._min_conf():
            note = "creature recognition below confidence threshold" if r.creatures else "no creature data"
        else:
            prios = {k.lower(): v for k, v in self._priorities().items()}
            for c in sorted(r.creatures, key=lambda c: c.slot):
                hp = c.health.value if c.health.confidence >= self._min_conf() else None
                known = c.name and c.name_confidence >= self._min_conf()
                name = c.name if known else "Unrecognized"
                creatures.append(CreatureRow(name, hp, pct(hp) if hp is not None else "—",
                                             self._trends.get((c.slot, c.name or ""), ""),
                                             priority=prios.get(name.lower(), 0) if known else 0,
                                             targeted=c.targeted))
            if self._sort_by_priority():
                creatures.sort(key=lambda row: -row.priority)   # stable: keeps list order within a priority
            summary = str(len(creatures))

        recs = [] if stale else [RecRow(x.priority, x.text, x.reason)
                                 for x in sorted(self.recommendations, key=lambda x: -x.priority)]

        if stale:
            advice = "Waiting for readings"
        elif recs:
            advice = ""
        else:
            unreliable = [b.label.lower() for b in (health, mana) if b.value is None]
            advice = ("No advice — " + " and ".join(unreliable) + " unreliable") if unreliable else "No action needed"

        st = self.status.state
        if st == RecognitionState.SIMULATED:
            source, level = "Simulation", "warn" if stale else "ok"
        elif st == RecognitionState.RUNNING:
            source, level = ("Live — no data" if stale else "Live"), ("warn" if stale else "ok")
        elif st in (RecognitionState.WINDOW_NOT_FOUND, RecognitionState.MINIMIZED, RecognitionState.ERROR):
            source, level = self.status.message or st.value, "critical"
        elif st == RecognitionState.NOT_CALIBRATED:
            source, level = "Not calibrated", "warn"
        else:
            source, level = "Not running", "unknown"

        monitoring = "—"
        if self.monitoring_since is not None:
            monitoring = _fmt_duration(self._clock() - self.monitoring_since)

        self.dirty = False
        return HudState(
            mode=mode, profile_name=self._profile_name(), source=source, source_level=level,
            health=health, mana=mana, partner=partner, creatures=creatures, creature_summary=summary,
            creature_note=note, recommendations=recs, monitoring_time=monitoring, stale=stale,
            advice_note=advice,
        )
