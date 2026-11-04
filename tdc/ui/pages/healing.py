"""Healing Assistant page: rule editor per profile, preview and live recommendations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from tdc.app_context import AppContext
from tdc.assistants.healing import HealingContext, evaluate
from tdc.config.settings import PartySettings
from tdc.core.events import Topic
from tdc.core.models import FrameReading, HuntMode, Measurement
from tdc.ui.rule_editor import RuleEditor
from tdc.ui.theme import C
from tdc.ui.widgets import Card, Page


def rec_label(rec) -> QLabel:
    lbl = QLabel(f"{rec.text}  ·  {rec.reason}")
    col = C.for_priority(int(rec.priority))
    lbl.setStyleSheet(f"border-left: 4px solid {col}; padding: 4px 8px; background: {C.SURFACE};")
    return lbl


class RecList(QWidget):
    def __init__(self, empty_text: str) -> None:
        super().__init__()
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(4)
        self.empty_text = empty_text
        self.labels: list[QLabel] = []
        self.set([])

    def set(self, recs) -> None:
        while self.v.count():
            item = self.v.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.labels = [rec_label(r) for r in recs]
        for lbl in self.labels:
            self.v.addWidget(lbl)
        if not recs:
            e = QLabel(self.empty_text)
            e.setObjectName("Muted")
            self.v.addWidget(e)


class HealingPage(Page):
    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__("Healing Assistant",
                         "Rules that turn your health and mana into recommendations. The app never casts or uses anything.")
        self.ctx = ctx
        self.services = services

        # Profile selector ---------------------------------------------------------------
        pc = Card("Profile")
        row = QHBoxLayout()
        row.setSpacing(0)
        self.profile_group = QButtonGroup(self)
        self.profile_buttons: dict[HuntMode, QPushButton] = {}
        for mode in (HuntMode.SOLO, HuntMode.DUO):
            b = QPushButton(mode.value.capitalize())
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: self.select_profile(m))
            self.profile_group.addButton(b)
            self.profile_buttons[mode] = b
            row.addWidget(b)
        row.addStretch(1)
        pc.body.addLayout(row)
        self.profile_note = QLabel("")
        self.profile_note.setObjectName("Dim")
        pc.body.addWidget(self.profile_note)
        self.content.addWidget(pc)

        # Rules --------------------------------------------------------------------------
        rc = Card("Rules")
        expl = QLabel(
            "A rule matches when the value is below its threshold. When several match, the app suggests "
            "the spell or potion with the lowest threshold and uses the highest priority of all matches — "
            "so a “Critical health” warning upgrades the spell suggestion to critical.")
        expl.setWordWrap(True)
        expl.setObjectName("Dim")
        rc.body.addWidget(expl)
        self.editor = RuleEditor(ctx, ("self", "partner"))
        rc.body.addWidget(self.editor)
        self.content.addWidget(rc)

        # Preview ------------------------------------------------------------------------
        pv = Card("Try it")
        grid = QGridLayout()
        self.sliders: dict[str, QSlider] = {}
        self.slider_values: dict[str, QLabel] = {}
        for i, (key, label, default) in enumerate((("health", "Your health", 70), ("mana", "Your mana", 45),
                                                    ("partner", "Partner health", 60))):
            s = QSlider(Qt.Horizontal)
            s.setRange(0, 100)
            s.setValue(default)
            v = QLabel(f"{default}%")
            v.setFixedWidth(44)
            grid.addWidget(QLabel(label), i, 0)
            grid.addWidget(s, i, 1)
            grid.addWidget(v, i, 2)
            s.valueChanged.connect(self.update_preview)
            self.sliders[key], self.slider_values[key] = s, v
        pv.body.addLayout(grid)
        self.preview = RecList("No recommendation at these values.")
        pv.body.addWidget(self.preview)
        self.content.addWidget(pv)

        # Live -----------------------------------------------------------------------------
        lv = Card("Live recommendations")
        self.live = RecList("Nothing right now (or no readings — start recognition or a simulation).")
        lv.body.addWidget(self.live)
        self.content.addWidget(lv)
        self.content.addStretch(1)

        self.editor.rules_changed.connect(self.update_preview)
        ctx.bus.subscribe(Topic.RECOMMENDATIONS, self._on_live)
        ctx.bus.subscribe(Topic.PROFILE_CHANGED, lambda m: self.select_profile(m))
        self.selected = ctx.mode
        self.select_profile(ctx.mode)

    def select_profile(self, mode: HuntMode) -> None:
        self.selected = mode
        self.profile_buttons[mode].setChecked(True)
        profile = self.ctx.profiles.by_mode(mode)
        targets = ("self", "partner") if mode == HuntMode.DUO else ("self",)
        self.editor.targets = targets
        if profile:
            self.editor.set_profile(profile.id, mode.value)
        duo = mode == HuntMode.DUO
        self.sliders["partner"].setEnabled(duo)
        self._update_note()
        self.update_preview()

    def _update_note(self) -> None:
        active = self.ctx.mode
        note = f"Editing the {self.selected.value.capitalize()} profile."
        note += " It is the active profile." if active == self.selected else \
            f" The active profile is {active.value.capitalize()} (switch on the Dashboard)."
        self.profile_note.setText(note)

    def preview_reading(self) -> FrameReading:
        v = {k: s.value() for k, s in self.sliders.items()}
        for k, lbl in self.slider_values.items():
            lbl.setText(f"{v[k]}%")
        return FrameReading(Measurement(v["health"], 1.0), Measurement(v["mana"], 1.0),
                            Measurement(v["partner"], 1.0), source="preview")

    def update_preview(self) -> list:
        party = self.ctx.config.get(PartySettings)
        rules = self.ctx.healing_rules.for_profile(self.editor.profile_id) if self.editor.profile_id else []
        recs = evaluate(self.preview_reading(), HealingContext(rules, self.selected, 0.0, True, party.partner_name))
        self.preview.set(recs)
        return recs

    def _on_live(self, recs) -> None:
        if self.isVisible():
            self.live.set([r for r in recs if r.category in ("healing", "mana", "party")])

    def on_shown(self) -> None:
        self.editor.reload()
        self.update_preview()
