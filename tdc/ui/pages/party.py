"""Party Settings page: duo partner monitoring."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from tdc.app_context import AppContext
from tdc.config.settings import PartySettings, RecognitionSettings
from tdc.core.events import Topic
from tdc.core.models import HuntMode
from tdc.ui.hud.widgets import ResourceBar
from tdc.ui.rule_editor import RuleEditor
from tdc.ui.settings_form import SettingsCard
from tdc.ui.theme import C
from tdc.ui.widgets import Card, Page


class PartyPage(Page):
    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__("Party Settings", "Monitor one duo partner. Partner thresholds are separate from your own.")
        self.ctx = ctx
        self.services = services

        mode = Card("Mode")
        row = QHBoxLayout()
        self.mode_label = QLabel("")
        self.mode_btn = QPushButton("")
        self.mode_btn.clicked.connect(self.toggle_mode)
        row.addWidget(self.mode_label, 1)
        row.addWidget(self.mode_btn)
        mode.body.addLayout(row)
        self.content.addWidget(mode)

        status = Card("Partner now")
        self.partner_bar = ResourceBar("Partner", C.GREEN)
        self.partner_bar.setMinimumWidth(300)
        status.body.addWidget(self.partner_bar)
        self.partner_note = QLabel("")
        self.partner_note.setObjectName("Dim")
        status.body.addWidget(self.partner_note)
        self.content.addWidget(status)

        sc = Card("Partner")
        hint = QLabel("Draw the party list region on the Visual Recognition page. With a name set (and its letters "
                      "taught) the partner is found by name; otherwise by position in the party list.")
        hint.setWordWrap(True)
        hint.setObjectName("Dim")
        sc.body.addWidget(hint)
        self.settings_card = SettingsCard(ctx, PartySettings)
        sc.body.addWidget(self.settings_card)
        self.content.addWidget(sc)

        rc = Card("Partner thresholds (Duo profile)")
        self.editor = RuleEditor(ctx, ("partner",))
        rc.body.addWidget(self.editor)
        stats = QLabel("Duo hunts get their own statistics in Analytics (Phase 6).")
        stats.setObjectName("Muted")
        rc.body.addWidget(stats)
        self.content.addWidget(rc)
        self.content.addStretch(1)

        duo = ctx.profiles.by_mode(HuntMode.DUO)
        if duo:
            self.editor.set_profile(duo.id, "duo")
        ctx.bus.subscribe(Topic.READING_VALIDATED, self._on_reading)
        ctx.bus.subscribe(Topic.PROFILE_CHANGED, lambda _m: self.refresh())
        self.refresh()

    def toggle_mode(self) -> None:
        self.ctx.set_mode(HuntMode.SOLO if self.ctx.mode == HuntMode.DUO else HuntMode.DUO)

    def refresh(self) -> None:
        duo = self.ctx.mode == HuntMode.DUO
        self.mode_label.setText("Duo mode: your partner is monitored." if duo
                                else "Solo mode: partner monitoring is off.")
        self.mode_btn.setText("Switch to Solo" if duo else "Switch to Duo")
        if not duo:
            self.partner_bar.set_state(self.ctx.config.get(PartySettings).partner_name or "Partner",
                                       None, "—", "unknown", "solo mode", None)
            self.partner_note.setText("")

    def _on_reading(self, reading) -> None:
        if self.ctx.mode != HuntMode.DUO:
            return
        m = reading.partner_health
        name = self.ctx.config.get(PartySettings).partner_name or "Partner"
        min_conf = self.ctx.config.get(RecognitionSettings).min_confidence
        if m.value is None or m.confidence < min_conf:
            self.partner_bar.set_state(name, None, "—", "unknown", m.reason or "unavailable", m.confidence)
            self.partner_note.setText("")
            return
        rules = [r for r in self.editor.rules if r.enabled and m.value < r.threshold]
        level = {0: "low", 1: "warn", 2: "critical"}[max(r.priority for r in rules)] if rules else "ok"
        self.partner_bar.set_state(name, m.value, f"{m.value:.0f}%", level, "", m.confidence)
        self.partner_note.setText(f"Confidence {m.confidence:.0%} · source: {reading.source}")

    def on_shown(self) -> None:
        self.editor.reload()
        self.refresh()
