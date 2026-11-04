"""Combat Assistant page: live creatures, creature priorities and combat settings."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCompleter, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem,
)

from tdc.app_context import AppContext
from tdc.config.settings import CombatSettings
from tdc.core.errors import ValidationError
from tdc.core.events import Topic
from tdc.recognition.creatures import KNOWN_CREATURES
from tdc.ui.settings_form import SettingsCard
from tdc.ui.widgets import Card, Page


def _table(headers: tuple[str, ...]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    return t


class CombatPage(Page):
    LIVE_COLS = ("Creature", "Health", "Trend", "Time to 0 %", "Priority", "Your target")

    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__("Combat Assistant",
                         "What is around you, read from the battle list. Information only — "
                         "the app never targets or attacks.")
        self.ctx = ctx
        self.services = services

        live = Card("Creatures now")
        self.summary = QLabel("No readings — start recognition or a simulation.")
        self.summary.setObjectName("Dim")
        live.body.addWidget(self.summary)
        self.live_table = _table(self.LIVE_COLS)
        self.live_table.setMinimumHeight(200)
        live.body.addWidget(self.live_table)
        self.combat_recs = QLabel("")
        self.combat_recs.setWordWrap(True)
        live.body.addWidget(self.combat_recs)
        self.content.addWidget(live)

        pr = Card("Creature priorities")
        expl = QLabel("Give important creatures a priority (1–10). They are starred and sorted first in the HUD, "
                      "and announced when they appear (see settings below). Negative values sort them last.")
        expl.setWordWrap(True)
        expl.setObjectName("Dim")
        pr.body.addWidget(expl)
        row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Creature name")
        comp = QCompleter(sorted(set(KNOWN_CREATURES)), self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.name_edit.setCompleter(comp)
        self.prio_spin = QSpinBox()
        self.prio_spin.setRange(-10, 10)
        self.prio_spin.setValue(5)
        self.add_btn = QPushButton("Add / update")
        self.add_btn.setObjectName("Primary")
        self.remove_btn = QPushButton("Remove selected")
        row.addWidget(self.name_edit, 1)
        row.addWidget(QLabel("Priority"))
        row.addWidget(self.prio_spin)
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        pr.body.addLayout(row)
        self.prio_error = QLabel("")
        self.prio_error.setObjectName("Error")
        pr.body.addWidget(self.prio_error)
        self.prio_table = _table(("Creature", "Priority"))
        self.prio_table.setMinimumHeight(160)
        pr.body.addWidget(self.prio_table)
        self.content.addWidget(pr)

        sc = Card("Combat settings")
        self.settings_card = SettingsCard(ctx, CombatSettings)
        sc.body.addWidget(self.settings_card)
        self.content.addWidget(sc)
        self.content.addStretch(1)

        self.add_btn.clicked.connect(self.add_priority)
        self.name_edit.returnPressed.connect(self.add_priority)
        self.remove_btn.clicked.connect(self.remove_selected)
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.refresh_live)
        self.reload_priorities()

    # ------------------------------------------------------------------ priorities
    def reload_priorities(self) -> None:
        data = self.ctx.creatures.all()
        self.prio_table.setRowCount(len(data))
        for i, (name, p) in enumerate(sorted(data.items(), key=lambda kv: (-kv[1], kv[0]))):
            self.prio_table.setItem(i, 0, QTableWidgetItem(name))
            self.prio_table.setItem(i, 1, QTableWidgetItem(str(p)))

    def add_priority(self) -> bool:
        try:
            self.ctx.creatures.set(self.name_edit.text(), self.prio_spin.value())
        except ValidationError as exc:
            self.prio_error.setText(str(exc))
            return False
        self.prio_error.setText("")
        self.name_edit.clear()
        self._priorities_changed()
        return True

    def remove_selected(self) -> None:
        rows = self.prio_table.selectionModel().selectedRows()
        if not rows:
            return
        self.ctx.creatures.delete(self.prio_table.item(rows[0].row(), 0).text())
        self._priorities_changed()

    def _priorities_changed(self) -> None:
        self.ctx.bus.publish(Topic.CONFIG_CHANGED, "creatures")
        self.reload_priorities()
        if self.services:
            self.services.recognition.reload()   # new names help OCR name matching

    # ------------------------------------------------------------------ live
    def on_shown(self) -> None:
        self.reload_priorities()
        self.refresh_live()
        self._timer.start()

    def hideEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def refresh_live(self) -> None:
        if self.services is None:
            return
        snap = self.services.combat.analyzer.snapshot
        if not snap.available:
            self.summary.setText(f"No creature data: {snap.reason}.")
            self.live_table.setRowCount(0)
            self.combat_recs.setText("")
            return
        tgt = f" · your target: {snap.targeted.name or 'unrecognized'}" if snap.targeted else ""
        self.summary.setText(f"{snap.count} creature{'s' if snap.count != 1 else ''} in the battle list{tgt}")
        self.live_table.setRowCount(len(snap.creatures))
        for i, c in enumerate(snap.creatures):
            trend = "—" if c.hp_per_s is None else f"{c.hp_per_s:+.1f} %/s"
            eta = "—" if c.eta_s is None else f"{c.eta_s:.0f} s"
            vals = (c.name or "Unrecognized", "—" if c.health is None else f"{c.health:.0f} %", trend, eta,
                    str(c.priority) if c.priority else "", "●" if c.targeted else "")
            for j, v in enumerate(vals):
                self.live_table.setItem(i, j, QTableWidgetItem(v))
        recs = self.services.combat.last
        self.combat_recs.setText("  ·  ".join(r.text for r in recs) if recs else "No combat alerts.")
