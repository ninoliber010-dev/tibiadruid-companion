import time

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMenu

from tdc.config.settings import HudSettings, NotificationSettings
from tdc.core.events import Topic
from tdc.core.models import HuntMode, Notification, Priority
from tdc.ui.hud.window import HudWindow
from tdc.ui.main_window import MainWindow
from tdc.ui.services import Services


@pytest.fixture
def services(qtbot, ctx):
    sv = Services(ctx)
    qtbot.addWidget(sv.hud.window)
    yield sv
    sv.shutdown()


def run_sim(sv, scenario, steps):
    sv.simulation.start(scenario)
    for _ in range(steps):
        sv.simulation._tick()
    sv.hud.render(force=True)


def test_window_is_frameless_tool_on_top(services):
    services.hud.show()
    flags = services.hud.window.windowFlags()
    assert flags & Qt.FramelessWindowHint and flags & Qt.WindowStaysOnTopHint
    assert (flags & Qt.Tool) == Qt.Tool  # separate window, no taskbar entry
    assert not flags & Qt.WindowTransparentForInput


def test_always_on_top_can_be_disabled(services, ctx):
    services.hud.show()
    ctx.config.update(HudSettings, always_on_top=False)
    assert not services.hud.window.windowFlags() & Qt.WindowStaysOnTopHint
    assert services.hud.window.isVisible()


def test_click_through_toggle_and_badge(services, ctx):
    services.hud.show()
    services.hud.set_click_through(True)
    w = services.hud.window
    assert w.windowFlags() & Qt.WindowTransparentForInput
    assert not w.click_badge.isHidden() and w.isVisible()
    services.hud.set_click_through(False)
    assert not w.windowFlags() & Qt.WindowTransparentForInput
    assert w.click_badge.isHidden()
    assert ctx.config.get(HudSettings).click_through is False


def test_opacity_applied(services, ctx):
    services.hud.show()
    services.hud.set_opacity(0.6)
    assert ctx.config.get(HudSettings).opacity == 0.6
    assert services.hud.window.settings.opacity == 0.6


def test_compact_mode_shrinks_and_hides_sections(services, ctx):
    services.hud.show()
    run_sim(services, "danger", 50)
    w = services.hud.window
    expanded_h = w.height()
    services.hud.set_compact(True)
    services.hud.render(force=True)
    assert w.combat.isHidden() and w.session.isHidden()
    assert w.height() < expanded_h
    assert sum(not r.isHidden() for r in w.rec_widgets) <= 1
    services.hud.set_compact(False)
    assert not w.combat.isHidden()
    assert w.height() >= ctx.config.get(HudSettings).height  # back to (at least) the stored expanded size


def test_section_visibility_settings(services, ctx):
    services.hud.show()
    ctx.config.update(HudSettings, show_combat=False, show_session=False)
    w = services.hud.window
    assert w.combat.isHidden() and w.session.isHidden() and not w.player.isHidden()


def test_geometry_persisted(services, ctx):
    services.hud.show()
    w = services.hud.window
    w.move(321, 234)
    w.resize(350, 500)
    w._emit_geometry()
    s = ctx.config.get(HudSettings)
    assert (s.x, s.y, s.width, s.height) == (321, 234, 350, 500)


def test_offscreen_position_is_corrected():
    avail = QGuiApplication.primaryScreen().availableGeometry()
    fixed = HudWindow.ensure_on_screen(QRect(avail.right() + 5000, avail.bottom() + 5000, 300, 400))
    assert avail.intersects(fixed)
    ok = QRect(avail.x() + 10, avail.y() + 10, 300, 400)
    assert HudWindow.ensure_on_screen(ok) == ok


def test_simulation_drives_hud(services, ctx):
    services.hud.show()
    run_sim(services, "danger", 50)
    w = services.hud.window
    assert w.source_label.text() == "Simulation"
    assert w.health_bar.value is not None
    assert any(not r.isHidden() for r in w.creature_rows)
    assert any(not r.isHidden() for r in w.rec_widgets)


def test_partner_section_only_in_duo(services, ctx):
    services.hud.show()
    run_sim(services, "steady", 3)
    assert services.hud.window.party.isHidden()
    ctx.set_mode(HuntMode.DUO)
    run_sim(services, "duo", 10)
    assert not services.hud.window.party.isHidden()
    assert services.hud.window.partner_bar.value is not None


def test_critical_notification_reaches_hud(services, ctx):
    services.hud.show()
    run_sim(services, "danger", 60)  # health goes below 35 %
    criticals = [n for n in services.notifications.history if n.priority == Priority.CRITICAL]
    assert criticals
    assert not services.hud.window.toast.isHidden()
    assert services.hud.sound.last_played == "alarm"


def test_quiet_mode_silences_non_critical(services, ctx):
    services.hud.set_quiet(True)
    assert ctx.config.get(NotificationSettings).quiet_mode
    services.hud.sound.last_played = None
    ctx.bus.publish(Topic.NOTIFICATION, Notification("x", Priority.ELEVATED, "Warning", "m", "healing", sound="none"))
    assert services.hud.sound.last_played is None


def test_stopping_simulation_clears_display(services):
    services.hud.show()
    run_sim(services, "danger", 50)
    services.simulation.stop()
    services.hud.render(force=True)
    w = services.hud.window
    assert w.source_label.text() == "Not running"
    assert w.health_bar.value is None
    assert w.toast.isHidden()


def test_hide_show_and_menu(services):
    services.hud.show()
    assert services.hud.visible
    services.hud.window.close_btn.click()
    assert not services.hud.visible
    menu = QMenu()
    services.hud.populate_menu(menu)
    texts = [a.text() for a in menu.actions()]
    assert "Show HUD" in texts and "Click-through" in texts and "Quiet mode" in texts


def test_render_is_cheap(services):
    services.hud.show()
    run_sim(services, "danger", 5)
    start = time.perf_counter()
    for _ in range(100):
        services.simulation._tick()
        services.hud.render(force=True)
    per_frame_ms = (time.perf_counter() - start) * 10
    assert per_frame_ms < 20, per_frame_ms  # budget: 10 fps uses well under 20 % of one core


def test_dashboard_controls(qtbot, ctx, services):
    w = MainWindow(ctx, services)
    qtbot.addWidget(w)
    dash = w.pages["Dashboard"]
    dash.hud_toggle.click()
    assert services.hud.visible and dash.hud_toggle.text() == "Hide HUD"
    dash.scenario_box.setCurrentIndex(dash.scenario_box.findData("duo"))
    dash.sim_button.click()
    assert services.simulation.running and ctx.mode == HuntMode.DUO
    assert dash.recognition_card.value.text() == "Simulation"
    assert "Simulation" in w.status_recog.text()
    dash.sim_button.click()
    assert not services.simulation.running
    dash.click_through_box.setChecked(True)
    assert ctx.config.get(HudSettings).click_through
