"""Diagnostics: environment, database health, backups and live log."""

from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton

from tdc import __version__
from tdc.app_context import AppContext
from tdc.config.settings import GeneralSettings
from tdc.core.logging_setup import memory_handler
from tdc.storage.backup import create_backup, list_backups
from tdc.ui.widgets import Card, Page


class DiagnosticsPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Diagnostics", "Health checks, backups and logs. Use this page when something looks wrong.")
        self.ctx = ctx

        env = Card("Environment")
        f = QFormLayout()
        f.addRow("App version", QLabel(__version__))
        f.addRow("Python", QLabel(sys.version.split()[0]))
        f.addRow("Qt for Python", QLabel(pyside_version))
        f.addRow("Operating system", QLabel(f"{platform.system()} {platform.release()}"))
        data_lbl = QLabel(str(ctx.paths.root))
        data_lbl.setWordWrap(True)
        f.addRow("Data folder", data_lbl)
        env.body.addLayout(f)
        open_btn = QPushButton("Open data folder")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.root))))
        open_row = QHBoxLayout()
        open_row.addWidget(open_btn)
        open_row.addStretch(1)
        env.body.addLayout(open_row)
        self.content.addWidget(env)

        dbc = Card("Database")
        self.db_info = QLabel("")
        self.db_info.setWordWrap(True)
        dbc.body.addWidget(self.db_info)
        row = QHBoxLayout()
        self.check_btn = QPushButton("Run integrity check")
        self.backup_btn = QPushButton("Back up now")
        row.addWidget(self.check_btn)
        row.addWidget(self.backup_btn)
        row.addStretch(1)
        dbc.body.addLayout(row)
        self.db_status = QLabel("")
        self.db_status.setObjectName("Dim")
        dbc.body.addWidget(self.db_status)
        self.check_btn.clicked.connect(self.run_integrity_check)
        self.backup_btn.clicked.connect(self.backup_now)
        self.content.addWidget(dbc)

        logc = Card("Log (most recent)")
        self.log_counts = QLabel("")
        self.log_counts.setObjectName("Dim")
        logc.body.addWidget(self.log_counts)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(260)
        self.log_view.setMaximumBlockCount(1000)
        logc.body.addWidget(self.log_view)
        self.content.addWidget(logc)

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(1000)
        self._log_timer.timeout.connect(self.refresh_log)
        self._shown_lines = 0
        self.refresh_db()

    def on_shown(self) -> None:
        self.refresh_db()
        self.refresh_log()
        self._log_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._log_timer.stop()
        super().hideEvent(event)

    def refresh_db(self) -> None:
        counts = self.ctx.db.table_counts()
        backups = list_backups(self.ctx.paths.backups)
        nonempty = ", ".join(f"{k} {v}" for k, v in counts.items() if v and k != "schema_version")
        self.db_info.setText(
            f"File: {self.ctx.paths.database}\nSchema version: {self.ctx.db.schema_version()}\n"
            f"Rows: {nonempty or 'none'}\nBackups: {len(backups)}"
            + (f" (latest {backups[-1].name})" if backups else "")
        )

    def run_integrity_check(self) -> str:
        result = self.ctx.db.integrity_check()
        self.db_status.setText("Integrity check passed." if result == "ok" else f"Integrity problem: {result}")
        return result

    def backup_now(self) -> None:
        keep = self.ctx.config.get(GeneralSettings).backups_to_keep
        try:
            path = create_backup(self.ctx.db, self.ctx.paths.backups, keep=keep)
            self.db_status.setText(f"Backup saved: {path.name}")
        except Exception as exc:  # noqa: BLE001
            self.db_status.setText(f"Backup failed: {exc}")
        self.refresh_db()

    def refresh_log(self) -> None:
        h = memory_handler()
        lines = h.lines()
        self.log_counts.setText(f"{h.error_count} errors · {h.warning_count} warnings since start")
        if len(lines) != self._shown_lines:
            self.log_view.setPlainText("\n".join(lines[-1000:]))
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
            self._shown_lines = len(lines)
