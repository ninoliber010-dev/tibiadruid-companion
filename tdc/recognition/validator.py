"""ReadingValidator: the gate between raw recognition and everything that gives advice.

* Measurements under the confidence threshold become *unavailable* (with the reason).
* Values are smoothed with a short median.
* Safety bias: a drop in health/mana is passed on immediately (an alert too many is better
  than one too late), but a large *rise* must be seen in two consecutive frames before it is
  believed — so a single bad frame can never hide an emergency.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Callable

from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, Measurement

RISE_CONFIRM = 30.0   # percentage points


class _Channel:
    def __init__(self) -> None:
        self.values: deque[float] = deque(maxlen=10)
        self.pending_rise: float | None = None

    def reset(self) -> None:
        self.values.clear()
        self.pending_rise = None

    def feed(self, m: Measurement, min_conf: float, frames: int) -> Measurement:
        if m.value is None:
            self.reset()
            return m
        if m.confidence < min_conf:
            self.reset()
            return Measurement(None, m.confidence, f"low confidence ({m.confidence:.0%})")
        v = float(m.value)
        if self.values:
            last = self.values[-1]
            if v - last > RISE_CONFIRM:
                if self.pending_rise is None or abs(self.pending_rise - v) > 10:
                    self.pending_rise = v
                    return Measurement(last, m.confidence, m.reason)   # hold the lower value
                self.values.clear()    # rise confirmed by a second frame: start fresh
            elif last - v > 15:
                # A real drop: do not let older, higher values in the median delay it.
                self.values.clear()
        self.pending_rise = None
        self.values.append(v)
        recent = sorted(list(self.values)[-frames:])
        # Median; for an even count take the lower middle value (errs on the side of caution).
        median = recent[(len(recent) - 1) // 2]
        return Measurement(round(median, 1), m.confidence, m.reason)


class ReadingValidator:
    def __init__(self, bus: EventBus, min_confidence: Callable[[], float],
                 smoothing_frames: Callable[[], int]) -> None:
        self._bus = bus
        self._min_conf = min_confidence
        self._frames = smoothing_frames
        self.health = _Channel()
        self.mana = _Channel()
        self.partner = _Channel()
        self._unsub = bus.subscribe(Topic.FRAME_READING, self.on_frame)

    def validate(self, r: FrameReading) -> FrameReading:
        mc, n = self._min_conf(), max(1, self._frames())
        return replace(
            r,
            health=self.health.feed(r.health, mc, n),
            mana=self.mana.feed(r.mana, mc, n),
            partner_health=self.partner.feed(r.partner_health, mc, n),
        )

    def on_frame(self, r: FrameReading) -> None:
        self._bus.publish(Topic.READING_VALIDATED, self.validate(r))

    def reset(self) -> None:
        for ch in (self.health, self.mana, self.partner):
            ch.reset()

    def close(self) -> None:
        self._unsub()
