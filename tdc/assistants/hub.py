"""RecommendationHub: runs every assistant on each validated reading and publishes ONE list.

The notification manager treats each published list as "everything that is active right now",
so healing and combat advice must be combined before publishing.
"""

from __future__ import annotations

from typing import Callable

from tdc.assistants.combat import CombatAssistant
from tdc.assistants.healing import HealingContext, evaluate
from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, Recommendation


class RecommendationHub:
    def __init__(self, bus: EventBus, healing_context: Callable[[], HealingContext],
                 combat: CombatAssistant | None = None) -> None:
        self.bus = bus
        self._healing_context = healing_context
        self.combat = combat
        self.last: list[Recommendation] = []
        self.last_healing: list[Recommendation] = []
        self._unsub = bus.subscribe(Topic.READING_VALIDATED, self.on_reading)

    def on_reading(self, reading: FrameReading) -> None:
        healing = evaluate(reading, self._healing_context())
        combat = self.combat.on_reading(reading) if self.combat else []
        recs = sorted(healing + combat, key=lambda r: (-r.priority, r.category != "healing"))
        self.last_healing = healing
        self.last = recs
        self.bus.publish(Topic.RECOMMENDATIONS, recs)

    def close(self) -> None:
        self._unsub()
