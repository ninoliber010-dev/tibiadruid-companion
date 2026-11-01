"""Immutable data models shared between modules.

Every value that comes from recognition carries a confidence and, when unavailable,
a reason. Nothing downstream should ever have to guess whether a number is real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Priority(IntEnum):
    NORMAL = 0
    ELEVATED = 1
    CRITICAL = 2


class Reliability(str, Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    MANUAL = "manual"
    UNAVAILABLE = "unavailable"


class HuntMode(str, Enum):
    SOLO = "solo"
    DUO = "duo"


class RecognitionState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    WINDOW_NOT_FOUND = "window_not_found"
    MINIMIZED = "minimized"
    NOT_CALIBRATED = "not_calibrated"
    ERROR = "error"
    SIMULATED = "simulated"


@dataclass(frozen=True)
class Measurement:
    """A single recognized value (e.g. health %) with its confidence in [0, 1]."""

    value: float | None
    confidence: float = 0.0
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None

    @classmethod
    def unavailable(cls, reason: str) -> "Measurement":
        return cls(None, 0.0, reason)


@dataclass(frozen=True)
class CreatureReading:
    name: str | None
    health: Measurement
    name_confidence: float = 0.0
    slot: int = 0


@dataclass(frozen=True)
class FrameReading:
    """Everything recognized from one capture cycle."""

    health: Measurement
    mana: Measurement
    partner_health: Measurement = field(default_factory=lambda: Measurement.unavailable("not monitored"))
    creatures: tuple[CreatureReading, ...] = ()
    creatures_confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    source: str = "recognition"


@dataclass(frozen=True)
class RecognitionStatus:
    state: RecognitionState
    message: str = ""
    fps: float = 0.0
    last_error: str = ""


@dataclass(frozen=True)
class Recommendation:
    """Information for the player. Never an action the app performs."""

    key: str  # stable identity used for de-duplication, e.g. "heal.self"
    priority: Priority
    text: str
    reason: str = ""
    category: str = "healing"
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Notification:
    """A toast/sound event produced by the NotificationManager."""

    key: str
    priority: Priority
    title: str
    message: str
    category: str
    sound: str = "none"        # none | soft | chime | alarm
    volume: int = 70           # 0-100
    duration_ms: int = 4000
    timestamp: float = field(default_factory=time.time)
