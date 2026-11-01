"""A form generated from a SettingsSection's field metadata."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from tdc.config.settings import SettingsSection


class SettingsForm(QWidget):
    changed = Signal()

    def __init__(self, section: SettingsSection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cls = type(section)
        self._editors: dict[str, QWidget] = {}
        self._errors: dict[str, QLabel] = {}
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        for f in fields(section):
            m = f.metadata
            if m.get("hidden"):
                continue
            editor = self._make_editor(f, m)
            editor.setToolTip(m.get("help", ""))
            if not isinstance(editor, QCheckBox):
                editor.setMaximumWidth(380)
            self._editors[f.name] = editor
            err = QLabel("")
            err.setObjectName("Error")
            err.setVisible(False)
            self._errors[f.name] = err
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            v.addWidget(editor)
            if m.get("help") and not isinstance(editor, QCheckBox):
                h = QLabel(m["help"])
                h.setObjectName("Muted")
                h.setWordWrap(True)
                v.addWidget(h)
            v.addWidget(err)
            label = "" if isinstance(editor, QCheckBox) else m.get("label", f.name)
            form.addRow(label, box)
        self.set_values(section)

    def _make_editor(self, f, m) -> QWidget:
        default = f.default
        if isinstance(default, bool):
            w = QCheckBox(m.get("label", f.name))
            w.toggled.connect(self.changed)
            return w
        if m.get("choices"):
            w = QComboBox()
            for c in m["choices"]:
                text = str(c)
                w.addItem(text.capitalize() if text.islower() else text, c)
            w.currentIndexChanged.connect(self.changed)
            return w
        if isinstance(default, int):
            w = QSpinBox()
            w.setRange(int(m["min"] if m["min"] is not None else -1_000_000),
                       int(m["max"] if m["max"] is not None else 1_000_000))
            w.setSingleStep(int(m.get("step") or 1))
            w.setSuffix(m.get("suffix", ""))
            w.valueChanged.connect(self.changed)
            return w
        if isinstance(default, float):
            w = QDoubleSpinBox()
            w.setDecimals(2)
            w.setRange(m["min"] if m["min"] is not None else -1e9, m["max"] if m["max"] is not None else 1e9)
            w.setSingleStep(m.get("step") or 0.1)
            w.setSuffix(m.get("suffix", ""))
            w.valueChanged.connect(self.changed)
            return w
        w = QLineEdit()
        w.setMaxLength(m.get("max_len", 200))
        w.textChanged.connect(self.changed)
        return w

    def set_values(self, section: SettingsSection) -> None:
        self._section = section
        for name, w in self._editors.items():
            value = getattr(section, name)
            w.blockSignals(True)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(value)))
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setValue(value)
            elif isinstance(w, QLineEdit):
                w.setText(str(value))
            w.blockSignals(False)
        self.show_errors({})

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, w in self._editors.items():
            if isinstance(w, QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[name] = w.currentData()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                out[name] = w.value()
            elif isinstance(w, QLineEdit):
                out[name] = w.text().strip()
        return out

    def build(self) -> SettingsSection:
        """Return a new section combining the original (hidden fields) with edited values."""
        return replace(self._section, **self.values())

    def show_errors(self, errors: dict[str, str]) -> None:
        for name, lbl in self._errors.items():
            msg = errors.get(name, "")
            lbl.setText(msg)
            lbl.setVisible(bool(msg))

    def editor(self, name: str) -> QWidget:
        return self._editors[name]
