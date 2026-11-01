"""Dashboard: an overview of every module's current state."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from tdc import __version__
from tdc.app_context import AppContext
from tdc.core.events import Topic
from tdc.config.settings import HudSettings
from tdc.core.models import HuntMode, RecognitionState, RecognitionStatus
from tdc.simulation.scenarios import SCENARIOS
from tdc.storage.repositories import REGION_KINDS
from tdc.ui.theme import C
from tdc.ui.widgets import Card, Page, StatCard


class DashboardPage(Page):
    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__("Dashboard", "Overview of your companion. Values marked “—” are not available yet.")
        self.ctx = ctx
        self.services = services
        self.recognition_state = RecognitionState.STOPPED

        # Mode switch -----------------------------------------------------------
        mode_card = Card("Hunting mode")
        row = QHBoxLayout()
        row.setSpacing(0)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[HuntMode, QPushButton] = {}
        for mode, label in ((HuntMode.SOLO, "Solo"), (HuntMode.DUO, "Duo")):
            b = QPushButton(label)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: self.ctx.set_mode(m))
            self.mode_group.addButton(b)
            self.mode_buttons[mode] = b
            row.addWidget(b)
        row.addStretch(1)
        mode_card.body.addLayout(row)
        self.mode_caption = QLabel("")
        self.mode_caption.setObjectName("Dim")
        mode_card.body.addWidget(self.mode_caption)
        self.content.addWidget(mode_card)

        # Status grid ------------------------------------------------------------
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        self.recognition_card = StatCard("Visual recognition")
        self.healing_card = StatCard("Healing profile")
        self.hud_card = StatCard("Floating HUD")
        self.session_card = StatCard("Hunting session")
        self.routes_card = StatCard("Route")
        self.db_card = StatCard("Local database")
        cards = [self.recognition_card, self.healing_card, self.hud_card,
                 self.session_card, self.routes_card, self.db_card]
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        self.content.addWidget(grid_host)

        # HUD + simulation controls -------------------------------------------------
        controls = QWidget()
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(14)

        hud = Card("HUD controls")
        row1 = QHBoxLayout()
        self.hud_toggle = QPushButton("Show HUD")
        self.hud_toggle.setObjectName("Primary")
        row1.addWidget(self.hud_toggle)
        row1.addStretch(1)
        hud.body.addLayout(row1)
        self.click_through_box = QCheckBox("Click-through (mouse passes through the HUD)")
        self.compact_box = QCheckBox("Compact mode")
        hud.body.addWidget(self.click_through_box)
        hud.body.addWidget(self.compact_box)
        hint = QLabel("Drag the HUD by its background, resize from the bottom-right corner, "
                      "right-click it for options. Position and size are remembered.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hud.body.addWidget(hint)
        cl.addWidget(hud, 1)

        sim = Card("Simulation (test data)")
        row2 = QHBoxLayout()
        self.scenario_box = QComboBox()
        for sc in SCENARIOS:
            self.scenario_box.addItem(sc.title, sc.key)
        self.sim_button = QPushButton("Start simulation")
        row2.addWidget(self.scenario_box, 1)
        row2.addWidget(self.sim_button)
        sim.body.addLayout(row2)
        self.scenario_desc = QLabel("")
        self.scenario_desc.setObjectName("Dim")
        self.scenario_desc.setWordWrap(True)
        sim.body.addWidget(self.scenario_desc)
        sim_note = QLabel("Feeds made-up readings through the HUD, healing recommendations and "
                          "notifications so you can try them before screen recognition exists. "
                          "The HUD labels this data as “Simulation”.")
        sim_note.setObjectName("Muted")
        sim_note.setWordWrap(True)
        sim.body.addWidget(sim_note)
        cl.addWidget(sim, 1)
        self.content.addWidget(controls)

        self.scenario_box.currentIndexChanged.connect(self._update_scenario_desc)
        self._update_scenario_desc()
        if services is None:
            for w in (self.hud_toggle, self.click_through_box, self.compact_box, self.scenario_box, self.sim_button):
                w.setEnabled(False)
        else:
            self.hud_toggle.clicked.connect(services.hud.toggle)
            self.click_through_box.toggled.connect(
                lambda on: services.hud.set_click_through(on) if on != ctx.config.get(HudSettings).click_through else None)
            self.compact_box.toggled.connect(
                lambda on: services.hud.set_compact(on) if on != (ctx.config.get(HudSettings).mode == "compact") else None)
            self.sim_button.clicked.connect(self._toggle_simulation)
            services.hud.visibility_changed.connect(lambda _v: self.refresh())
            services.simulation.running_changed.connect(lambda _v: self.refresh())
        ctx.bus.subscribe(Topic.RECOGNITION_STATUS, self._on_status)

        # Read-only notice -------------------------------------------------------
        notice = Card("Read-only companion")
        txt = QLabel(
            "This app only looks at your screen and shows information. It never sends keyboard "
            "or mouse input to Tibia, never reads or changes game memory, and never casts spells "
            "or uses items for you."
        )
        txt.setWordWrap(True)
        txt.setObjectName("Dim")
        notice.body.addWidget(txt)
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("Muted")
        notice.body.addWidget(ver)
        self.content.addWidget(notice)
        self.content.addStretch(1)

        ctx.bus.subscribe(Topic.PROFILE_CHANGED, lambda _m: self.refresh())
        ctx.bus.subscribe(Topic.CONFIG_CHANGED, lambda _s: self.refresh())
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def _update_scenario_desc(self) -> None:
        key = self.scenario_box.currentData()
        self.scenario_desc.setText(next(s.description for s in SCENARIOS if s.key == key))

    def _toggle_simulation(self) -> None:
        sim = self.services.simulation
        if sim.running:
            sim.stop()
        else:
            if self.scenario_box.currentData() == "duo" and self.ctx.mode != HuntMode.DUO:
                self.ctx.set_mode(HuntMode.DUO)
            sim.start(self.scenario_box.currentData())
            if not self.services.hud.visible:
                self.services.hud.show()

    def _on_status(self, status: RecognitionStatus) -> None:
        self.recognition_state = status.state
        self.refresh()

    def refresh(self) -> None:
        mode = self.ctx.mode
        self.mode_buttons[mode].setChecked(True)
        self.mode_caption.setText(
            "Monitoring yourself only." if mode == HuntMode.SOLO
            else "Monitoring yourself and one party member."
        )

        calibrated = self.ctx.regions.all()
        needed = [k for k in ("health", "mana") if k not in calibrated]
        if self.recognition_state == RecognitionState.SIMULATED:
            self.recognition_card.set("Simulation", "Readings are simulated test data, not from Tibia.", C.AMBER)
        else:
            self.recognition_card.set(
                "Not running",
                f"{len(calibrated)}/{len(REGION_KINDS)} regions calibrated. "
                "Screen recognition arrives in Phase 3.",
                C.TEXT_MUTED if needed else C.AMBER,
            )

        profile = self.ctx.profiles.by_mode(mode)
        if profile:
            rules = [r for r in self.ctx.healing_rules.for_profile(profile.id) if r.enabled]
            self.healing_card.set(profile.name, f"{len(rules)} active rules (recommendations only)", C.GREEN)
        else:
            self.healing_card.set("No profile", "Create a profile in Healing Assistant", C.RED)

        hud_settings = self.ctx.config.get(HudSettings)
        if self.services is None:
            self.hud_card.set("Not available", "HUD services are not running.", C.TEXT_MUTED)
        else:
            shown = self.services.hud.visible
            extras = []
            if hud_settings.click_through:
                extras.append("click-through on")
            extras.append(f"{hud_settings.mode}, {hud_settings.opacity:.0%} opacity")
            self.hud_card.set("Shown" if shown else "Hidden", " · ".join(extras), C.GREEN if shown else C.TEXT_MUTED)
            self.hud_toggle.setText("Hide HUD" if shown else "Show HUD")
            for box, val in ((self.click_through_box, hud_settings.click_through),
                             (self.compact_box, hud_settings.mode == "compact")):
                box.blockSignals(True)
                box.setChecked(val)
                box.blockSignals(False)
            running = self.services.simulation.running
            self.sim_button.setText("Stop simulation" if running else "Start simulation")
            self.scenario_box.setEnabled(not running)
        self.session_card.set("No session", "Session tracking arrives in Phase 6.", C.TEXT_MUTED)
        self.routes_card.set("—", "Route manager arrives in Phase 5.", C.TEXT_MUTED)

        size = self.ctx.paths.database.stat().st_size if self.ctx.paths.database.exists() else 0
        self.db_card.set(
            "Healthy",
            f"Schema v{self.ctx.db.schema_version()} · {size / 1024:.0f} KB",
            C.GREEN,
        )
