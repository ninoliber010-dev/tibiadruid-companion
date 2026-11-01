"""Configuration page: one tab per settings section, generated from metadata."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QTabWidget

from tdc.app_context import AppContext
from tdc.config.settings import ALL_SECTIONS, SettingsSection
from tdc.core.errors import ConfigValidationError
from tdc.core.events import Topic
from tdc.ui.settings_form import SettingsForm
from tdc.ui.widgets import Page


class SectionEditor(QScrollArea):
    def __init__(self, ctx: AppContext, cls: type[SettingsSection]) -> None:
        super().__init__()
        self.ctx, self.cls = ctx, cls
        self.setWidgetResizable(True)
        self.form = SettingsForm(ctx.config.get(cls))
        self.setWidget(self.form)
        self.form.changed.connect(lambda: self.dirty_changed())
        self._dirty = False

    def dirty_changed(self) -> None:
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def save(self) -> bool:
        section = self.form.build()
        try:
            self.ctx.config.save(section)
        except ConfigValidationError as exc:
            self.form.show_errors(exc.errors)
            return False
        self.form.set_values(self.ctx.config.get(self.cls))
        self._dirty = False
        return True

    def revert(self) -> None:
        self.form.set_values(self.ctx.config.get(self.cls))
        self._dirty = False

    def reset_defaults(self) -> None:
        self.form.set_values(self.cls())
        self._dirty = True


class ConfigurationPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Configuration", "All settings are saved locally and apply immediately after saving.")
        self.ctx = ctx
        self.tabs = QTabWidget()
        self.editors: dict[str, SectionEditor] = {}
        for cls in ALL_SECTIONS:
            ed = SectionEditor(ctx, cls)
            self.editors[cls.SECTION] = ed
            self.tabs.addTab(ed, cls.TITLE)
        self.tabs.setMinimumHeight(460)
        self.content.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Dim")
        bar.addWidget(self.status, 1)
        self.defaults_btn = QPushButton("Restore defaults")
        self.revert_btn = QPushButton("Revert")
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("Primary")
        for b in (self.defaults_btn, self.revert_btn, self.save_btn):
            bar.addWidget(b)
        self.content.addLayout(bar)

        self.save_btn.clicked.connect(self.save_current)
        self.revert_btn.clicked.connect(lambda: (self.current().revert(), self.status.setText("Changes reverted.")))
        self.defaults_btn.clicked.connect(self._defaults)
        # Keep forms in sync when settings change elsewhere (e.g. mode switch on Dashboard).
        ctx.bus.subscribe(Topic.CONFIG_CHANGED, self._external_change)

    def current(self) -> SectionEditor:
        return self.tabs.currentWidget()  # type: ignore[return-value]

    def save_current(self) -> bool:
        ed = self.current()
        ok = ed.save()
        self.status.setText(f"{ed.cls.TITLE} settings saved." if ok else "Please fix the highlighted values.")
        return ok

    def _defaults(self) -> None:
        ed = self.current()
        if QMessageBox.question(self, "Restore defaults",
                                f"Restore default {ed.cls.TITLE} settings? You still need to press Save.") \
                == QMessageBox.Yes:
            ed.reset_defaults()
            self.status.setText("Defaults loaded — press Save to apply.")

    def _external_change(self, section: str) -> None:
        ed = self.editors.get(section)
        if ed and not ed.dirty:
            ed.revert()
