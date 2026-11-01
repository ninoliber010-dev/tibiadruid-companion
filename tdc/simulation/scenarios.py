"""Scripted, deterministic hunt scenarios that produce ``FrameReading`` objects.

Used to develop and test the HUD, notifications and assistants before (and alongside) real
screen recognition. Simulated data is always labelled ``source="simulation"``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from tdc.core.models import CreatureReading, FrameReading, Measurement

CREATURES = ["Dragon Lord", "Dragon", "Frost Dragon", "Hydra", "Serpent Spawn", "Medusa",
             "Grim Reaper", "Werehyaena", "Lost Soul", "Juggernaut"]


@dataclass
class ScenarioInfo:
    key: str
    title: str
    description: str


SCENARIOS = [
    ScenarioInfo("steady", "Steady hunt", "Comfortable solo hunt with small health dips and regular mana use."),
    ScenarioInfo("danger", "Dangerous pull", "Several creatures at once; health drops into the critical range."),
    ScenarioInfo("duo", "Duo — partner in trouble", "Partner health dips below the warning and critical thresholds."),
    ScenarioInfo("dropout", "Recognition problems", "Readings lose confidence and sometimes disappear."),
]


@dataclass
class Simulator:
    scenario: str = "steady"
    seed: int = 7
    t: float = 0.0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.scenario not in {s.key for s in SCENARIOS}:
            raise ValueError(f"Unknown scenario {self.scenario!r}")
        self._rng = random.Random(self.seed)

    def step(self, dt: float, timestamp: float | None = None) -> FrameReading:
        self.t += dt
        fn = getattr(self, f"_{self.scenario}")
        reading: FrameReading = fn(self.t)
        if timestamp is not None:
            reading = FrameReading(**{**reading.__dict__, "timestamp": timestamp})
        return reading

    # ------------------------------------------------------------------ helpers
    def _noise(self, amount: float) -> float:
        return self._rng.uniform(-amount, amount)

    @staticmethod
    def _clamp(v: float) -> float:
        return max(0.0, min(100.0, v))

    def _m(self, value: float, conf: float = 0.97) -> Measurement:
        return Measurement(round(self._clamp(value), 1), round(max(0.0, min(1.0, conf + self._noise(0.02))), 3))

    def _creatures(self, t: float, count: int, period: float = 9.0) -> tuple[CreatureReading, ...]:
        out = []
        for i in range(count):
            phase = (t / period + i * 0.37) % 1.0
            hp = 100 * (1 - phase)
            name = CREATURES[(i + int(t // period)) % len(CREATURES)]
            out.append(CreatureReading(name, self._m(hp, 0.95), name_confidence=0.9 + self._noise(0.05), slot=i))
        return tuple(out)

    # ------------------------------------------------------------------ scenarios
    def _steady(self, t: float) -> FrameReading:
        hp = 88 + 10 * math.sin(t / 3.0) + self._noise(2)
        mp = 100 - (t * 6 % 70) + self._noise(1)
        return FrameReading(self._m(hp), self._m(mp),
                            creatures=self._creatures(t, 2 + int(t / 7) % 3), creatures_confidence=0.92,
                            source="simulation")

    def _danger(self, t: float) -> FrameReading:
        cycle = t % 24
        if cycle < 8:
            hp = 95 - cycle * 2
        elif cycle < 14:
            hp = 80 - (cycle - 8) * 9.5   # down to ~23 %
        else:
            hp = 23 + (cycle - 14) * 7
        mp = 70 - (cycle * 2.2) + self._noise(1)
        n = 2 if cycle < 8 else 6
        return FrameReading(self._m(hp + self._noise(1.5)), self._m(mp),
                            creatures=self._creatures(t, n, period=6), creatures_confidence=0.9,
                            source="simulation")

    def _duo(self, t: float) -> FrameReading:
        base = self._steady(t)
        cycle = t % 20
        partner = 95 - cycle * 4.5 if cycle < 15 else 27 + (cycle - 15) * 14
        return FrameReading(base.health, base.mana, partner_health=self._m(partner + self._noise(1.5), 0.93),
                            creatures=base.creatures, creatures_confidence=base.creatures_confidence,
                            source="simulation")

    def _dropout(self, t: float) -> FrameReading:
        base = self._steady(t)
        cycle = t % 12
        if cycle < 4:
            return base
        if cycle < 8:
            # Confidence collapses (e.g. a window covering the health bar).
            return FrameReading(self._m(base.health.value or 0, 0.45), self._m(base.mana.value or 0, 0.5),
                                creatures=(), creatures_confidence=0.3, source="simulation")
        return FrameReading(Measurement.unavailable("Tibia window not visible"),
                            Measurement.unavailable("Tibia window not visible"),
                            creatures=(), creatures_confidence=0.0, source="simulation")
