"""Application bootstrap."""

from __future__ import annotations

import logging
import sys
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from tdc import APP_ID, APP_NAME, __version__
from tdc.app_context import AppContext
from tdc.config.settings import GeneralSettings
from tdc.core.events import Topic
from tdc.core.logging_setup import configure_logging, set_level
from tdc.core.paths import AppPaths
from tdc.core.errors import DatabaseError

log = logging.getLogger(__name__)


class QtDispatcher(QObject):
    """Delivers event-bus callbacks on the GUI thread.

    Emitting a signal from a worker thread to a QObject living in the GUI thread is
    queued by Qt automatically; emitting from the GUI thread calls directly.
    """

    _call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._call.connect(self._run, Qt.AutoConnection)

    def __call__(self, fn: Callable[[], None]) -> None:
        self._call.emit(fn)

    @staticmethod
    def _run(fn: Callable[[], None]) -> None:
        fn()


def _enable_dpi_awareness() -> None:
    """Per-monitor DPI awareness so screen coordinates are physical pixels (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:  # noqa: BLE001 - Qt also sets this; failure is not fatal
        pass


def _setup_tray(app: QApplication, window, services) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    from tdc.core.models import Priority
    from tdc.ui.icons import app_icon

    tray = QSystemTrayIcon(app_icon(), app)
    tray.setToolTip(APP_NAME)
    menu = QMenu()

    def rebuild() -> None:
        # Rebuilt each time so check marks always match the saved settings.
        menu.clear()
        menu.addAction("Open main window").triggered.connect(window.bring_to_front)
        menu.addSeparator()
        services.hud.populate_menu(menu)
        if services.simulation.running:
            menu.addAction("Stop simulation").triggered.connect(services.simulation.stop)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(window.request_quit)

    menu.aboutToShow.connect(rebuild)
    rebuild()
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.bring_to_front() if reason == QSystemTrayIcon.Trigger else None
    )

    def on_notification(n) -> None:
        # Critical alerts still reach the player when the HUD is hidden.
        if n.priority == Priority.CRITICAL and not services.hud.visible:
            tray.showMessage(APP_NAME, n.message, QSystemTrayIcon.Critical, n.duration_ms)

    services.ctx.bus.subscribe(Topic.NOTIFICATION, on_notification)
    tray.show()
    tray._menu = menu  # keep a reference
    return tray


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    smoke_test = "--smoke-test" in argv  # start, show every page, exit (used to verify builds)
    _enable_dpi_awareness()
    app = QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    paths = AppPaths.default().ensure()
    configure_logging(paths.log_file)
    log.info("Starting %s %s (data: %s)", APP_NAME, __version__, paths.root)

    from tdc.core.events import EventBus
    from tdc.ui.icons import app_icon
    from tdc.ui.main_window import MainWindow
    from tdc.ui.theme import apply_theme

    apply_theme(app)
    app.setWindowIcon(app_icon())

    dispatcher = QtDispatcher()
    bus = EventBus(dispatcher)
    try:
        ctx = AppContext.create(paths, bus)
    except DatabaseError as exc:
        log.exception("Could not open database")
        QMessageBox.critical(None, APP_NAME, f"Could not open the database:\n{exc}")
        return 1

    set_level(ctx.config.get(GeneralSettings).log_level)
    bus.subscribe(Topic.CONFIG_CHANGED,
                  lambda s: set_level(ctx.config.get(GeneralSettings).log_level) if s == "general" else None)

    from tdc.ui.services import Services

    services = Services(ctx)
    window = MainWindow(ctx, services)
    tray = _setup_tray(app, window, services)
    window.tray_available = tray is not None
    window.show()
    if ctx.config.get(GeneralSettings).show_hud_on_launch:
        services.hud.show()

    def on_quit() -> None:
        log.info("Shutting down")
        services.shutdown()
        ctx.shutdown()

    app.aboutToQuit.connect(on_quit)
    if smoke_test:
        from PySide6.QtCore import QTimer

        def run_smoke() -> None:
            for name in window.pages:
                window.show_page(name)
                app.processEvents()
            services.hud.show()
            services.simulation.start("danger")
            for _ in range(5):
                services.simulation._tick()
                app.processEvents()
            services.hud.render(force=True)
            services.simulation.stop()
            log.info("Smoke test passed: %d pages shown", len(window.pages))
            print("SMOKE TEST OK")
            window.request_quit()
            app.quit()

        QTimer.singleShot(300, run_smoke)
    window.destroyed.connect(app.quit)
    # Without a tray the app ends when the window closes.
    window.setAttribute(Qt.WA_DeleteOnClose, True)
    return app.exec()
