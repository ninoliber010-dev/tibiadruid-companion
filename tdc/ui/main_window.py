"""Main desktop window: sidebar navigation + stacked pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QStatusBar, QVBoxLayout, QWidget,
)

from tdc import APP_NAME
from tdc.app_context import AppContext
from tdc.config.settings import GeneralSettings
from tdc.core.events import Topic
from tdc.ui.icons import app_icon
from tdc.ui.pages.configuration import ConfigurationPage
from tdc.ui.pages.dashboard import DashboardPage
from tdc.ui.pages.diagnostics import DiagnosticsPage
from tdc.ui.pages.recognition import RecognitionPage
from tdc.ui.widgets import Page, PlaceholderPage

NAV_ITEMS = [
    "Dashboard", "Visual Recognition", "Combat Assistant", "Healing Assistant",
    "Party Settings", "Route Manager", "Analytics", "Configuration", "Diagnostics",
]


def build_pages(ctx: AppContext, services=None) -> dict[str, Page]:
    return {
        "Dashboard": DashboardPage(ctx, services),
        "Visual Recognition": RecognitionPage(ctx, services),
        "Combat Assistant": PlaceholderPage(
            "Combat Assistant", "Recognized creatures and informational combat hints.", 4,
            ["Creature list with names, health and health trend",
             "Configurable creature priorities", "Informational recommendations only — no targeting"]),
        "Healing Assistant": PlaceholderPage(
            "Healing Assistant", "Threshold-based healing and potion recommendations.", 4,
            ["Edit spell, potion and warning rules per Solo/Duo profile",
             "Default example rules are already stored in the database",
             "Live recommendation preview using simulated readings"]),
        "Party Settings": PlaceholderPage(
            "Party Settings", "Duo partner monitoring.", 4,
            ["Partner health thresholds separate from your own",
             "Partner recognition from the party list", "Separate duo session statistics"]),
        "Route Manager": PlaceholderPage(
            "Route Manager", "Plan and annotate hunting routes.", 5,
            ["Folders, routes and ordered waypoints", "Notes and screenshot references",
             "Import/export (JSON)", "Route visualization and informational progress"]),
        "Analytics": PlaceholderPage(
            "Analytics", "Session statistics and history.", 6,
            ["XP/hour, damage, healing, supplies and profit/loss",
             "Import from Tibia's Hunt Analyser (paste the copied text)",
             "Every value tagged Measured / Estimated / Manual / Unavailable",
             "Charts and session comparisons"]),
        "Configuration": ConfigurationPage(ctx),
        "Diagnostics": DiagnosticsPage(ctx),
    }


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__()
        self.ctx = ctx
        self.services = services
        self._really_quit = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar ---------------------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(12, 18, 12, 12)
        sb.setSpacing(2)
        title = QLabel("Druid Companion")
        title.setObjectName("AppTitle")
        sub = QLabel("for Tibia · read-only")
        sub.setObjectName("AppSubtitle")
        sb.addWidget(title)
        sb.addWidget(sub)
        sb.addSpacing(18)

        self.stack = QStackedWidget()
        self.pages = build_pages(ctx, services)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        for i, name in enumerate(NAV_ITEMS):
            btn = QPushButton(name)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, n=name: self.show_page(n))
            self.nav_group.addButton(btn, i)
            self.nav_buttons[name] = btn
            sb.addWidget(btn)
            self.stack.addWidget(self.pages[name])
        sb.addStretch(1)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.status_mode = QLabel()
        self.status_recog = QLabel("Recognition: not running")
        status.addWidget(self.status_mode)
        status.addPermanentWidget(self.status_recog)
        self.setStatusBar(status)

        ctx.bus.subscribe(Topic.PROFILE_CHANGED, lambda _m: self._update_status())
        ctx.bus.subscribe(Topic.CONFIG_CHANGED, lambda _s: self._update_status())
        ctx.bus.subscribe(Topic.APP_ERROR, self._show_error)
        ctx.bus.subscribe(Topic.RECOGNITION_STATUS,
                          lambda st: self.status_recog.setText(f"Recognition: {st.message or st.state.value}"))
        if services is not None:
            services.hud.open_main_window.connect(self.bring_to_front)
        self._update_status()
        self.show_page("Dashboard")

    def show_page(self, name: str) -> None:
        page = self.pages[name]
        self.nav_buttons[name].setChecked(True)
        self.stack.setCurrentWidget(page)
        page.on_shown()

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def current_page_name(self) -> str:
        return next(n for n, p in self.pages.items() if p is self.stack.currentWidget())

    def _update_status(self) -> None:
        self.status_mode.setText(f"Mode: {self.ctx.mode.value.capitalize()}")

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 15000)
        if self.isVisible():
            QMessageBox.warning(self, APP_NAME, message)

    # ---------------------------------------------------------------- close/tray
    def request_quit(self) -> None:
        self._really_quit = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        tray_ok = getattr(self, "tray_available", False)
        if not self._really_quit and tray_ok and self.ctx.config.get(GeneralSettings).minimize_to_tray:
            event.ignore()
            self.hide()
            return
        event.accept()
