"""Healing recommendation engine (Elder Druid).

Turns validated health/mana readings into *recommendations for the player*. It never acts.

For each group (self-health, self-mana, partner-health) the engine looks at every enabled rule
whose threshold the current value is below:
* the suggested action is the matching spell/potion with the lowest threshold (the strongest
  response configured for this situation);
* the priority is the highest priority among all matching rules (so a "critical" warning rule
  escalates the spell suggestion);
* if only warning rules match, the warning itself is shown.
Readings below the confidence threshold produce no advice — the HUD shows them as unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, HuntMode, Measurement, Priority, Recommendation
from tdc.storage.repositories import HealingRule

GROUPS = (
    # key, target, resource, category, label
    ("heal.self", "self", "health", "healing", "Health"),
    ("mana.self", "self", "mana", "mana", "Mana"),
    ("heal.partner", "partner", "health", "party", "Partner health"),
)


@dataclass
class HealingContext:
    rules: list[HealingRule]
    mode: HuntMode
    min_confidence: float
    monitor_partner: bool = True
    partner_name: str = ""


def usable(m: Measurement, min_confidence: float) -> bool:
    return m.value is not None and m.confidence >= min_confidence


def evaluate(reading: FrameReading, ctx: HealingContext) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for key, target, resource, category, label in GROUPS:
        if target == "partner" and (ctx.mode != HuntMode.DUO or not ctx.monitor_partner):
            continue
        m = {"health": reading.health, "mana": reading.mana}[resource] if target == "self" else reading.partner_health
        if not usable(m, ctx.min_confidence):
            continue
        value = float(m.value)
        matching = [r for r in ctx.rules
                    if r.enabled and r.target == target and r.resource == resource and value < r.threshold]
        if not matching:
            continue
        priority = Priority(max(r.priority for r in matching))
        actions = [r for r in matching if r.kind in ("spell", "potion")]
        if actions:
            chosen = min(actions, key=lambda r: (r.threshold, -r.priority, r.sort_order))
            verb = "Use" if chosen.kind == "potion" else "Cast"
            text = f"{verb} {chosen.name}"
        else:
            chosen = min(matching, key=lambda r: (r.threshold, -r.priority))
            text = chosen.name
        if target == "partner":
            label = f"{ctx.partner_name or 'Partner'} health"
        strictest = min(r.threshold for r in matching)
        reason = f"{label} {math.floor(value + 1e-9):d}% < {strictest:g}%"
        recs.append(Recommendation(key=key, priority=priority, text=text, reason=reason, category=category,
                                   timestamp=reading.timestamp))
    recs.sort(key=lambda r: -r.priority)
    return recs


class HealingAssistant:
    """Subscribes to validated readings and publishes healing recommendations."""

    def __init__(self, bus: EventBus, context_provider) -> None:
        self._bus = bus
        self._provider = context_provider     # () -> HealingContext (rules cached by caller)
        self.last: list[Recommendation] = []
        self._unsub = [bus.subscribe(Topic.READING_VALIDATED, self.on_reading)]

    def on_reading(self, reading: FrameReading) -> None:
        recs = evaluate(reading, self._provider())
        self.last = recs
        self._bus.publish(Topic.RECOMMENDATIONS, recs)

    def clear(self) -> None:
        self.last = []
        self._bus.publish(Topic.RECOMMENDATIONS, [])

    def close(self) -> None:
        for u in self._unsub:
            u()
