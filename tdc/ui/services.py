"""Runtime services that need Qt (timers, windows) bundled together for the UI."""

from __future__ import annotations

import time

from tdc.app_context import AppContext
from tdc.assistants.healing import HealingAssistant, HealingContext
from tdc.config.settings import NotificationSettings, PartySettings, RecognitionSettings
from tdc.core.events import Topic
from tdc.core.models import Priority, RecognitionState, RecognitionStatus
from tdc.notifications.manager import NotificationManager
from tdc.recognition.service import RecognitionService
from tdc.recognition.validator import ReadingValidator
from tdc.simulation.runner import SimulationRunner
from tdc.storage.repositories import HealingRule
from tdc.ui.dispatch import QtDispatcher
from tdc.ui.hud.controller import HudController


class RulesCache:
    """Healing rules of the active profile, re-read only when they or the profile change."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._rules: list[HealingRule] | None = None
        ctx.bus.subscribe(Topic.PROFILE_CHANGED, lambda _p: self.invalidate())
        ctx.bus.subscribe(Topic.RULES_CHANGED, lambda _p: self.invalidate())

    def invalidate(self) -> None:
        self._rules = None

    def get(self) -> list[HealingRule]:
        if self._rules is None:
            profile = self.ctx.profiles.by_mode(self.ctx.mode)
            self._rules = self.ctx.healing_rules.for_profile(profile.id) if profile else []
        return self._rules


class Services:
    def __init__(self, ctx: AppContext, recognition: RecognitionService | None = None) -> None:
        self.ctx = ctx
        # The recognition worker publishes from its own thread; widgets may only be touched on
        # the GUI thread, so make sure every bus delivery is routed there.
        if not isinstance(ctx.bus.dispatcher, QtDispatcher):
            self._dispatcher = QtDispatcher()
            ctx.bus.set_dispatcher(self._dispatcher)
        self.rules = RulesCache(ctx)
        rs = lambda: ctx.config.get(RecognitionSettings)  # noqa: E731
        self.validator = ReadingValidator(ctx.bus, lambda: rs().min_confidence, lambda: rs().smoothing_frames)
        self.recognition = recognition or RecognitionService(ctx)
        self._unreadable_since: float | None = None
        self.notifications = NotificationManager(ctx.bus, lambda: ctx.config.get(NotificationSettings))
        self.healing = HealingAssistant(ctx.bus, self._healing_context)
        self.simulation = SimulationRunner(ctx.bus, ctx.config.get(RecognitionSettings).interval_ms)
        self.hud = HudController(ctx, self.rules.get)
        self._last_state: RecognitionState | None = None
        ctx.bus.subscribe(Topic.CONFIG_CHANGED, self._on_config)
        ctx.bus.subscribe(Topic.RECOGNITION_STATUS, self._on_status)
        ctx.bus.subscribe(Topic.READING_VALIDATED, self._watch_reliability)

    # ------------------------------------------------------------------ live vs simulated
    def start_recognition(self) -> None:
        self.simulation.stop()
        self.validator.reset()
        self.recognition.start()

    def stop_recognition(self) -> None:
        self.recognition.stop()

    def start_simulation(self, scenario: str) -> None:
        self.recognition.stop()
        self.validator.reset()
        self.simulation.start(scenario)

    def _watch_reliability(self, reading) -> None:
        """Warn when health has been unreadable for a while during live recognition."""
        if reading.source != "recognition":
            return
        if reading.health.value is not None:
            self._unreadable_since = None
            return
        now = time.monotonic()
        if self._unreadable_since is None:
            self._unreadable_since = now
        elif now - self._unreadable_since >= self.ctx.config.get(RecognitionSettings).low_confidence_alert_s:
            self.notifications.notify("recognition.health", Priority.ELEVATED, "Health not readable",
                                      reading.health.reason or "check calibration", "recognition")
    def _healing_context(self) -> HealingContext:
        party = self.ctx.config.get(PartySettings)
        return HealingContext(
            rules=self.rules.get(), mode=self.ctx.mode,
            min_confidence=self.ctx.config.get(RecognitionSettings).min_confidence,
            monitor_partner=party.monitor_partner, partner_name=party.partner_name,
        )

    def _on_config(self, section: str) -> None:
        if section == "recognition":
            self.simulation.set_interval(self.ctx.config.get(RecognitionSettings).interval_ms)

    def _on_status(self, status: RecognitionStatus) -> None:
        if status.state == self._last_state:
            return
        self._last_state = status.state
        if status.state == RecognitionState.SIMULATED:
            self.notifications.notify("recognition.state", Priority.NORMAL, "Simulation running",
                                      "values are simulated, not read from Tibia", "recognition")
        elif status.state == RecognitionState.RUNNING:
            self.notifications.notify("recognition.state", Priority.NORMAL, "Monitoring Tibia", "", "recognition")
        elif status.state == RecognitionState.NOT_CALIBRATED:
            self.notifications.notify("recognition.state", Priority.ELEVATED, "Recognition not set up",
                                      status.message, "recognition")
        elif status.state in (RecognitionState.WINDOW_NOT_FOUND, RecognitionState.MINIMIZED,
                              RecognitionState.ERROR):
            self.notifications.notify("recognition.state", Priority.CRITICAL, "Monitoring unavailable",
                                      status.message, "recognition")

    def shutdown(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.recognition.stop()
        self.simulation.stop()
        QCoreApplication.processEvents()      # deliver what the worker already queued
        self.hud.close()
        self.healing.close()
        self.validator.close()
        self.notifications.close()
        dispatcher = self.ctx.bus.dispatcher
        if isinstance(dispatcher, QtDispatcher) and getattr(self, "_dispatcher", None) is dispatcher:
            dispatcher.close()
