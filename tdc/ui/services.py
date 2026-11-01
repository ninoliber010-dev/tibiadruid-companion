"""Runtime services that need Qt (timers, windows) bundled together for the UI."""

from __future__ import annotations

from tdc.app_context import AppContext
from tdc.assistants.healing import HealingAssistant, HealingContext
from tdc.config.settings import NotificationSettings, PartySettings, RecognitionSettings
from tdc.core.events import Topic
from tdc.core.models import Priority, RecognitionState, RecognitionStatus
from tdc.notifications.manager import NotificationManager
from tdc.simulation.runner import SimulationRunner
from tdc.storage.repositories import HealingRule
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
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.rules = RulesCache(ctx)
        self.notifications = NotificationManager(ctx.bus, lambda: ctx.config.get(NotificationSettings))
        self.healing = HealingAssistant(ctx.bus, self._healing_context)
        self.simulation = SimulationRunner(ctx.bus, ctx.config.get(RecognitionSettings).interval_ms)
        self.hud = HudController(ctx, self.rules.get)
        self._last_state: RecognitionState | None = None
        ctx.bus.subscribe(Topic.CONFIG_CHANGED, self._on_config)
        ctx.bus.subscribe(Topic.RECOGNITION_STATUS, self._on_status)

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
        elif status.state in (RecognitionState.WINDOW_NOT_FOUND, RecognitionState.ERROR):
            self.notifications.notify("recognition.state", Priority.CRITICAL, "Monitoring unavailable",
                                      status.message, "recognition")

    def shutdown(self) -> None:
        self.simulation.stop()
        self.hud.close()
        self.healing.close()
        self.notifications.close()
