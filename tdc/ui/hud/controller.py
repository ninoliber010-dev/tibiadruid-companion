"""HudController: connects the event bus, settings and the HUD window."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from tdc.app_context import AppContext
from tdc.config.settings import CombatSettings, HudSettings, NotificationSettings, PartySettings, RecognitionSettings
from tdc.core.events import Topic
from tdc.core.models import Notification, RecognitionState
from tdc.ui.hud.sound import SoundPlayer
from tdc.ui.hud.viewmodel import HudViewModel
from tdc.ui.hud.window import HudWindow

log = logging.getLogger(__name__)

RENDER_INTERVAL_MS = 100     # at most 10 repaints per second
CLOCK_REFRESH_MS = 1000      # time-based fields (timer, staleness) refresh even without events


class HudController(QObject):
    visibility_changed = Signal(bool)
    open_main_window = Signal()

    def __init__(self, ctx: AppContext, rules_provider, priorities_provider=lambda: {}) -> None:
        super().__init__()
        self.ctx = ctx
        self.vm = HudViewModel(
            min_confidence=lambda: ctx.config.get(RecognitionSettings).min_confidence,
            rules=rules_provider,
            mode=lambda: ctx.mode,
            profile_name=self._profile_name,
            partner_name=lambda: ctx.config.get(PartySettings).partner_name,
            stale_after=lambda: max(2.0, 4 * ctx.config.get(RecognitionSettings).interval_ms / 1000),
            priorities=priorities_provider,
            sort_by_priority=lambda: ctx.config.get(CombatSettings).sort_by_priority,
        )
        self.window = HudWindow()
        self.sound = SoundPlayer(ctx.paths.root / "sounds")
        self.render_count = 0
        self._since_full = 0

        bus = ctx.bus
        self._unsubs = [
            bus.subscribe(Topic.READING_VALIDATED, self.vm.on_reading),
            bus.subscribe(Topic.RECOMMENDATIONS, self.vm.on_recommendations),
            bus.subscribe(Topic.RECOGNITION_STATUS, self._on_status),
            bus.subscribe(Topic.NOTIFICATION, self.on_notification),
            bus.subscribe(Topic.CONFIG_CHANGED, self._on_config),
            bus.subscribe(Topic.PROFILE_CHANGED, lambda _m: setattr(self.vm, "dirty", True)),
        ]

        self.window.geometry_changed.connect(self._save_geometry)
        self.window.compact_toggled.connect(self.set_compact)
        self.window.hide_requested.connect(self.hide)
        self.window.menu_requested.connect(self._show_menu)

        self._timer = QTimer(self)
        self._timer.setInterval(RENDER_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self.window.apply_settings(ctx.config.get(HudSettings))
        self.render(force=True)

    def _profile_name(self) -> str:
        p = self.ctx.profiles.by_mode(self.ctx.mode)
        return p.name if p else "—"

    # ------------------------------------------------------------------ visibility
    @property
    def visible(self) -> bool:
        return self.window.isVisible()

    def show(self) -> None:
        self.window.apply_settings(self.ctx.config.get(HudSettings))
        self.window.show()
        self._timer.start()
        self.render(force=True)
        self.visibility_changed.emit(True)

    def hide(self) -> None:
        self.window.hide()
        self._timer.stop()
        self.visibility_changed.emit(False)

    def toggle(self) -> None:
        self.hide() if self.visible else self.show()

    # ------------------------------------------------------------------ settings shortcuts
    def set_click_through(self, on: bool) -> None:
        self.ctx.config.update(HudSettings, click_through=on)

    def set_compact(self, compact: bool) -> None:
        self.ctx.config.update(HudSettings, mode="compact" if compact else "expanded")

    def set_opacity(self, opacity: float) -> None:
        self.ctx.config.update(HudSettings, opacity=round(opacity, 2))

    def set_quiet(self, on: bool) -> None:
        self.ctx.config.update(NotificationSettings, quiet_mode=on)

    def _on_config(self, section: str) -> None:
        if section == "hud":
            self.window.apply_settings(self.ctx.config.get(HudSettings))
            self.render(force=True)
        elif section in ("party", "recognition", "general", "combat", "creatures"):
            self.vm.dirty = True

    def _save_geometry(self, x: int, y: int, w: int, h: int) -> None:
        s = self.ctx.config.get(HudSettings)
        w = max(220, min(900, w))
        h = max(120, min(1400, h))
        if (s.x, s.y, s.width, s.height) == (x, y, w, h):
            return
        s.x, s.y, s.width, s.height = x, y, w, h
        try:
            self.ctx.config.save(s)
        except Exception:  # noqa: BLE001
            log.exception("Could not save HUD position")

    # ------------------------------------------------------------------ rendering
    def _tick(self) -> None:
        self._since_full += RENDER_INTERVAL_MS
        if self.vm.dirty or self._since_full >= CLOCK_REFRESH_MS:
            self.render()

    def render(self, force: bool = False) -> None:
        if not force and not self.window.isVisible():
            return
        self._since_full = 0
        self.window.update_state(self.vm.state())
        self.render_count += 1

    def _on_status(self, status) -> None:
        self.vm.on_status(status)
        if status.state == RecognitionState.STOPPED:
            self.window.clear_notification()

    def on_notification(self, n: Notification) -> None:
        if self.window.isVisible():
            self.window.show_notification(n)
        self.sound.play(n.sound, n.volume)

    # ------------------------------------------------------------------ menu (shared with tray)
    def populate_menu(self, menu: QMenu, include_visibility: bool = True) -> None:
        hud = self.ctx.config.get(HudSettings)
        notes = self.ctx.config.get(NotificationSettings)
        if include_visibility:
            a = menu.addAction("Hide HUD" if self.visible else "Show HUD")
            a.triggered.connect(self.toggle)
        ct = menu.addAction("Click-through")
        ct.setCheckable(True)
        ct.setChecked(hud.click_through)
        ct.triggered.connect(self.set_click_through)
        cp = menu.addAction("Compact mode")
        cp.setCheckable(True)
        cp.setChecked(hud.mode == "compact")
        cp.triggered.connect(self.set_compact)
        op = menu.addMenu("Opacity")
        group = QActionGroup(op)
        for pct in (100, 90, 80, 70, 60, 50, 40):
            act = QAction(f"{pct}%", op)
            act.setCheckable(True)
            act.setChecked(abs(hud.opacity * 100 - pct) < 2.5)
            act.triggered.connect(lambda _=False, v=pct / 100: self.set_opacity(v))
            group.addAction(act)
            op.addAction(act)
        q = menu.addAction("Quiet mode")
        q.setCheckable(True)
        q.setChecked(notes.quiet_mode)
        q.triggered.connect(self.set_quiet)

    def _show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self.window)
        self.populate_menu(menu, include_visibility=False)
        menu.addSeparator()
        menu.addAction("Open main window").triggered.connect(self.open_main_window)
        menu.addAction("Hide HUD").triggered.connect(self.hide)
        menu.exec(pos)

    def close(self) -> None:
        for u in self._unsubs:
            u()
        self._timer.stop()
        self.window.close()
