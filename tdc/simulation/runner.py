"""Drives a Simulator on a QTimer and publishes its readings like the real recognition engine."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QTimer, Signal

from tdc.core.events import EventBus, Topic
from tdc.core.models import RecognitionState, RecognitionStatus
from tdc.simulation.scenarios import Simulator

log = logging.getLogger(__name__)


class SimulationRunner(QObject):
    running_changed = Signal(bool)

    def __init__(self, bus: EventBus, interval_ms: int = 250) -> None:
        super().__init__()
        self._bus = bus
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.interval_ms = interval_ms
        self.sim: Simulator | None = None

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def start(self, scenario: str) -> None:
        self.sim = Simulator(scenario)
        self._timer.start(self.interval_ms)
        log.info("Simulation started: %s", scenario)
        self._bus.publish(Topic.RECOGNITION_STATUS, RecognitionStatus(
            RecognitionState.SIMULATED, f"Simulation: {scenario}", fps=1000 / self.interval_ms))
        self._tick()
        self.running_changed.emit(True)

    def stop(self) -> None:
        if not self.running:
            return
        self._timer.stop()
        self.sim = None
        log.info("Simulation stopped")
        self._bus.publish(Topic.RECOGNITION_STATUS, RecognitionStatus(RecognitionState.STOPPED, "Not running"))
        self._bus.publish(Topic.RECOMMENDATIONS, [])
        self.running_changed.emit(False)

    def set_interval(self, interval_ms: int) -> None:
        self.interval_ms = interval_ms
        if self.running:
            self._timer.setInterval(interval_ms)

    def _tick(self) -> None:
        if self.sim is None:
            return
        reading = self.sim.step(self.interval_ms / 1000.0, timestamp=time.time())
        # Phase 3 inserts the ReadingValidator; until then simulated readings are already "clean"
        # and consumers still apply their own confidence checks.
        self._bus.publish(Topic.READING_VALIDATED, reading)
