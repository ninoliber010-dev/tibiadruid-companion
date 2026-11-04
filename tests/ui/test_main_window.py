import threading

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QSpinBox

from tdc.app import QtDispatcher
from tdc.config.settings import HudSettings
from tdc.core.events import EventBus
from tdc.core.models import HuntMode
from tdc.storage.backup import list_backups
from tdc.ui.main_window import NAV_ITEMS, MainWindow
from tdc.ui.widgets import PlaceholderPage


def test_navigation_shows_every_page(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    for name in NAV_ITEMS:
        w.nav_buttons[name].click()
        assert w.current_page_name() == name


def test_unbuilt_modules_are_clearly_marked(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    placeholders = {n for n, p in w.pages.items() if isinstance(p, PlaceholderPage)}
    assert "Dashboard" not in placeholders and "Configuration" not in placeholders
    assert placeholders == {"Route Manager", "Analytics"}


def test_dashboard_mode_switch(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    dash = w.pages["Dashboard"]
    dash.mode_buttons[HuntMode.DUO].click()
    assert ctx.mode == HuntMode.DUO
    assert "Duo" in w.status_mode.text()
    assert dash.healing_card.value.text() == "Duo"


def test_configuration_save_and_validation(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    page = w.pages["Configuration"]
    w.show_page("Configuration")
    page.tabs.setCurrentWidget(page.editors["hud"])
    form = page.editors["hud"].form
    width: QSpinBox = form.editor("width")
    width.setValue(480)
    assert page.save_current()
    assert ctx.config.get(HudSettings).width == 480
    # Hidden fields (position) are preserved by the form.
    ctx.config.update(HudSettings, x=777)
    page.editors["hud"].revert()
    width.setValue(500)
    page.save_current()
    assert ctx.config.get(HudSettings).x == 777


def test_configuration_shows_validation_errors(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    page = w.pages["Configuration"]
    page.tabs.setCurrentWidget(page.editors["recognition"])
    form = page.editors["recognition"].form
    form.editor("interval_ms").setValue(1500)
    form.editor("idle_interval_ms").setValue(1000)
    assert not page.save_current()
    assert "fix" in page.status.text()
    assert not form._errors["idle_interval_ms"].isHidden()


def test_diagnostics_backup_and_integrity(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    w.show_page("Diagnostics")
    diag = w.pages["Diagnostics"]
    diag.backup_btn.click()
    assert len(list_backups(ctx.paths.backups)) == 1
    assert diag.run_integrity_check() == "ok"


def test_qt_dispatcher_delivers_on_gui_thread(qtbot):
    bus = EventBus(QtDispatcher())
    received = []
    bus.subscribe("x", lambda p: received.append((p, QThread.currentThread() is QApplication.instance().thread())))
    t = threading.Thread(target=lambda: bus.publish("x", 42))
    t.start()
    t.join()
    qtbot.waitUntil(lambda: bool(received), timeout=2000)
    assert received == [(42, True)]
