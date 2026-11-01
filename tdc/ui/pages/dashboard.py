"""Dashboard: an overview of every module's current state."""

from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidget

from tdc import __version__
from tdc.app_context import AppContext
from tdc.core.events import Topic
from tdc.core.models import HuntMode
from tdc.storage.repositories import REGION_KINDS
from tdc.ui.theme import C
from tdc.ui.widgets import Card, Page, StatCard


class DashboardPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Dashboard", "Overview of your companion. Values marked “—” are not available yet.")
        self.ctx = ctx

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

    def refresh(self) -> None:
        mode = self.ctx.mode
        self.mode_buttons[mode].setChecked(True)
        self.mode_caption.setText(
            "Monitoring yourself only." if mode == HuntMode.SOLO
            else "Monitoring yourself and one party member."
        )

        calibrated = self.ctx.regions.all()
        needed = [k for k in ("health", "mana") if k not in calibrated]
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

        self.hud_card.set("Not available", "The floating HUD arrives in Phase 2.", C.TEXT_MUTED)
        self.session_card.set("No session", "Session tracking arrives in Phase 6.", C.TEXT_MUTED)
        self.routes_card.set("—", "Route manager arrives in Phase 5.", C.TEXT_MUTED)

        size = self.ctx.paths.database.stat().st_size if self.ctx.paths.database.exists() else 0
        self.db_card.set(
            "Healthy",
            f"Schema v{self.ctx.db.schema_version()} · {size / 1024:.0f} KB",
            C.GREEN,
        )
