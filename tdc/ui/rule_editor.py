"""Healing-rule table + edit dialog, shared by the Healing Assistant and Party pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from tdc.app_context import AppContext
from tdc.assistants.defaults import POTION_SUGGESTIONS, SPELL_SUGGESTIONS, WARNING_SUGGESTIONS, default_rules
from tdc.core.errors import ValidationError
from tdc.core.events import Topic
from tdc.storage.repositories import HealingRule
from tdc.ui.theme import C

PRIORITY_NAMES = {0: "Normal", 1: "Elevated", 2: "Critical"}
KIND_NAMES = {"spell": "Spell", "potion": "Potion", "warning": "Warning only"}
TARGET_NAMES = {"self": "You", "partner": "Partner"}
RESOURCE_NAMES = {"health": "Health", "mana": "Mana"}


class RuleDialog(QDialog):
    def __init__(self, rule: HealingRule, allowed_targets: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit rule" if rule.id else "New rule")
        self.rule = rule
        form = QFormLayout()
        self.target = QComboBox()
        for t in allowed_targets:
            self.target.addItem(TARGET_NAMES[t], t)
        self.kind = QComboBox()
        for k, label in KIND_NAMES.items():
            self.kind.addItem(label, k)
        self.name = QLineEdit()
        self.name.setMaxLength(60)
        self.resource = QComboBox()
        for r, label in RESOURCE_NAMES.items():
            self.resource.addItem(label, r)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 100)
        self.threshold.setDecimals(0)
        self.threshold.setSuffix(" %")
        self.priority = QComboBox()
        for p, label in PRIORITY_NAMES.items():
            self.priority.addItem(label, p)
        self.enabled = QCheckBox("Enabled")
        form.addRow("For", self.target)
        form.addRow("Type", self.kind)
        form.addRow("Name / text", self.name)
        form.addRow("Watch", self.resource)
        form.addRow("When below", self.threshold)
        form.addRow("Priority", self.priority)
        form.addRow("", self.enabled)
        self.error = QLabel("")
        self.error.setObjectName("Error")
        self.error.setWordWrap(True)
        hint = QLabel("The app shows this as a recommendation. It never casts spells or uses items.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(self.error)
        lay.addWidget(buttons)

        self.target.setCurrentIndex(max(0, self.target.findData(rule.target)))
        self.kind.setCurrentIndex(max(0, self.kind.findData(rule.kind)))
        self.name.setText(rule.name)
        self.resource.setCurrentIndex(max(0, self.resource.findData(rule.resource)))
        self.threshold.setValue(rule.threshold)
        self.priority.setCurrentIndex(max(0, self.priority.findData(rule.priority)))
        self.enabled.setChecked(rule.enabled)
        self.kind.currentIndexChanged.connect(self._suggest)
        self.target.currentIndexChanged.connect(self._target_changed)
        self._suggest()
        self._target_changed()

    def _suggest(self) -> None:
        names = {"spell": SPELL_SUGGESTIONS, "potion": POTION_SUGGESTIONS}.get(self.kind.currentData(),
                                                                                 WARNING_SUGGESTIONS)
        c = QCompleter(names, self)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        self.name.setCompleter(c)
        self.name.setPlaceholderText(", ".join(names[:3]) + "…")

    def _target_changed(self) -> None:
        partner = self.target.currentData() == "partner"
        if partner:
            self.resource.setCurrentIndex(self.resource.findData("health"))
        self.resource.setEnabled(not partner)

    def result_rule(self) -> HealingRule:
        r = self.rule
        return HealingRule(r.id, r.profile_id, self.target.currentData(), self.kind.currentData(),
                           self.name.text().strip(), self.resource.currentData(), self.threshold.value(),
                           self.priority.currentData(), self.enabled.isChecked(), r.sort_order)

    def _accept(self) -> None:
        try:
            self.result_rule().validate()
        except ValidationError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class RuleEditor(QWidget):
    """Table of rules for one profile, optionally limited to one target (self/partner)."""

    rules_changed = Signal()
    COLUMNS = ("On", "For", "Type", "Name", "Watch", "Below", "Priority")

    def __init__(self, ctx: AppContext, targets: tuple[str, ...] = ("self", "partner"), parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.targets = targets
        self.profile_id: int | None = None
        self.mode = "solo"
        self.rules: list[HealingRule] = []
        self.dialog_factory = RuleDialog     # replaced in tests

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        self.table.itemChanged.connect(self._item_changed)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton("Add rule")
        self.add_btn.setObjectName("Primary")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.up_btn = QPushButton("▲")
        self.down_btn = QPushButton("▼")
        self.defaults_btn = QPushButton("Restore example rules")
        for b in (self.add_btn, self.edit_btn, self.delete_btn, self.up_btn, self.down_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.defaults_btn)
        self.add_btn.clicked.connect(self.add)
        self.edit_btn.clicked.connect(self.edit_selected)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.up_btn.clicked.connect(lambda: self.move_selected(-1))
        self.down_btn.clicked.connect(lambda: self.move_selected(1))
        self.defaults_btn.clicked.connect(self.restore_defaults)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------ data
    def set_profile(self, profile_id: int, mode: str) -> None:
        self.profile_id, self.mode = profile_id, mode
        self.reload()

    def reload(self) -> None:
        if self.profile_id is None:
            return
        self.rules = [r for r in self.ctx.healing_rules.for_profile(self.profile_id) if r.target in self.targets]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rules))
        for row, r in enumerate(self.rules):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
            self.table.setItem(row, 0, on)
            values = (TARGET_NAMES[r.target], KIND_NAMES[r.kind], r.name, RESOURCE_NAMES[r.resource],
                      f"{r.threshold:g} %", PRIORITY_NAMES[r.priority])
            for col, v in enumerate(values, start=1):
                item = QTableWidgetItem(v)
                if col == 6:
                    item.setForeground(Qt.GlobalColor.white)
                    item.setBackground(_priority_brush(r.priority))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.blockSignals(False)

    def _changed(self) -> None:
        self.ctx.bus.publish(Topic.RULES_CHANGED, self.profile_id)
        self.reload()
        self.rules_changed.emit()

    def selected_index(self) -> int | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return rows[0].row() if rows else None

    # ------------------------------------------------------------------ actions
    def add(self) -> HealingRule | None:
        order = max((r.sort_order for r in self.ctx.healing_rules.for_profile(self.profile_id)), default=-1) + 1
        rule = HealingRule(None, self.profile_id, self.targets[0], "spell", "", "health", 50, 1, True, order)
        return self._run_dialog(rule)

    def edit_selected(self) -> HealingRule | None:
        i = self.selected_index()
        if i is None:
            return None
        return self._run_dialog(self.rules[i])

    def _run_dialog(self, rule: HealingRule) -> HealingRule | None:
        dlg = self.dialog_factory(rule, self.targets, self)
        if dlg.exec() != QDialog.Accepted:
            return None
        new = dlg.result_rule()
        self.ctx.healing_rules.save(new)
        self._changed()
        return new

    def delete_selected(self) -> bool:
        i = self.selected_index()
        if i is None:
            return False
        self.ctx.healing_rules.delete(self.rules[i].id)
        self._changed()
        return True

    def move_selected(self, delta: int) -> None:
        i = self.selected_index()
        if i is None or not 0 <= i + delta < len(self.rules):
            return
        a, b = self.rules[i], self.rules[i + delta]
        a.sort_order, b.sort_order = b.sort_order, a.sort_order
        if a.sort_order == b.sort_order:
            a.sort_order += delta
        self.ctx.healing_rules.save(a)
        self.ctx.healing_rules.save(b)
        self._changed()
        self.table.selectRow(i + delta)

    def restore_defaults(self, confirm: bool = True) -> None:
        if confirm and QMessageBox.question(
                self, "Restore example rules",
                "Replace the rules shown here with the example Elder Druid rules?") != QMessageBox.Yes:
            return
        for r in self.rules:
            self.ctx.healing_rules.delete(r.id)
        base = max((r.sort_order for r in self.ctx.healing_rules.for_profile(self.profile_id)), default=-1) + 1
        for i, (target, kind, name, resource, threshold, priority) in enumerate(default_rules(self.mode)):
            if target in self.targets:
                self.ctx.healing_rules.save(HealingRule(None, self.profile_id, target, kind, name, resource,
                                                        threshold, priority, True, base + i))
        self._changed()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        rule = self.rules[item.row()]
        rule.enabled = item.checkState() == Qt.Checked
        self.ctx.healing_rules.save(rule)
        self.ctx.bus.publish(Topic.RULES_CHANGED, self.profile_id)
        self.rules_changed.emit()


def _priority_brush(priority: int):
    from PySide6.QtGui import QBrush, QColor

    col = QColor(C.for_priority(priority))
    col.setAlpha(90)
    return QBrush(col)
