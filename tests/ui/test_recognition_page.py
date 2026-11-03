import pytest

from tdc.config.settings import RecognitionSettings
from tdc.core.models import RecognitionState
from tdc.recognition.capture import ImageCapturer
from tdc.recognition.geometry import Rect
from tdc.recognition.service import CaptureUnavailable, RecognitionService, capture_reference
from tdc.recognition.window import StaticWindowFinder, WindowInfo
from tdc.simulation.synthetic_screen import Entry, Scene, render
from tdc.storage.repositories import CalibrationRepository
from tdc.ui.main_window import MainWindow
from tdc.ui.services import Services

SCENE = Scene(health=100, mana=100, creatures=[Entry("Dragon Lord", 85, True), Entry("Hydra", 30)],
              party=[Entry("Knight Partner", 64)])


@pytest.fixture
def setup(qtbot, ctx):
    img, truth = render(SCENE)
    finder = StaticWindowFinder(WindowInfo(1, "Tibia - Druid", Rect(0, 0, img.shape[1], img.shape[0]), False, True))
    svc = RecognitionService(ctx, finder, ImageCapturer(img))
    services = Services(ctx, recognition=svc)
    w = MainWindow(ctx, services)
    qtbot.addWidget(w)
    qtbot.addWidget(services.hud.window)
    page = w.pages["Visual Recognition"]
    yield ctx, services, page, img, truth
    services.shutdown()


def calibrate(page, truth):
    for kind in ("health", "mana", "battle_list", "party"):
        page.save_region(kind, truth.regions[kind])
    page.learn_bar("health")
    page.learn_bar("mana")


def test_take_screenshot_and_calibrate(setup):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    assert page.image is not None and page.image.shape == img.shape
    calibrate(page, truth)
    regions = ctx.regions.all()
    assert set(regions) == {"health", "mana", "battle_list", "party"}
    assert regions["health"].ref_width == img.shape[1]
    assert set(CalibrationRepository(ctx.db).all()) == {"health", "mana"}
    results = page.test_regions()
    assert results["health"].startswith("Reads 100%")
    assert results["battle_list"].startswith("2 entries")
    assert "bar learned" in page.rows["health"].status.text()


def test_drawing_region_on_canvas(setup, qtbot):
    ctx, services, page, img, truth = setup
    page.load_demo()
    page._select_kind("mana")
    r = truth.regions["mana"]
    page.canvas.region_drawn.emit("mana", r)
    assert ctx.regions.get("mana").x == r.x


def test_redrawing_region_drops_old_bar_calibration(setup):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    calibrate(page, truth)
    page.save_region("health", truth.regions["health"])
    assert "health" not in CalibrationRepository(ctx.db).all()


def test_learn_bar_needs_coloured_bar(setup):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    page.save_region("health", Rect(10, 300, 100, 20))   # game-view area, no bar
    page.learn_bar("health")
    assert "learned" not in page.cal_status.text()
    assert "health" not in CalibrationRepository(ctx.db).all()


def test_teach_names(setup):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    calibrate(page, truth)
    rows = [r for r in page.teach_rows if not r.isHidden()]
    assert len(rows) == 2
    rows[0].edit.setText("Dragon Lord")
    assert page.teach(rows[0])
    rows[1].edit.setText("Hydra")
    assert page.teach(rows[1])
    assert "Dragon Lord 85%" in page.test_regions()["battle_list"]
    rows[0].edit.setText("Wrong Name Here")
    assert not page.teach(rows[0])


def test_screenshot_errors_are_explained(setup):
    ctx, services, page, img, truth = setup
    services.recognition.finder = StaticWindowFinder(None)
    page.take_screenshot()
    assert "No window titled" in page.cal_status.text()
    with pytest.raises(CaptureUnavailable):
        capture_reference(services.recognition)


def test_load_image_file(setup, tmp_path):
    import cv2

    ctx, services, page, img, truth = setup
    p = tmp_path / "shot.png"
    cv2.imwrite(str(p), img)
    assert page.load_image_file(str(p))
    assert not page.load_image_file(str(tmp_path / "missing.png"))


def test_live_recognition_end_to_end(setup, qtbot):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    calibrate(page, truth)
    ctx.config.update(RecognitionSettings, interval_ms=100)
    # Now Tibia shows lower health:
    low, _ = render(Scene(health=30, mana=70, creatures=SCENE.creatures))
    services.recognition.capturer.image = low
    page.toggle_recognition()
    services.hud.show()
    qtbot.waitUntil(lambda: services.hud.vm.reading is not None
                    and services.hud.vm.reading.health.value is not None, timeout=3000)
    assert services.hud.vm.reading.health.value == pytest.approx(30, abs=1.5)
    qtbot.waitUntil(lambda: any(r.key == "heal.self" for r in services.healing.last), timeout=3000)
    assert page.state == RecognitionState.RUNNING and page.state_label.text() == "Live"
    page.toggle_recognition()
    qtbot.waitUntil(lambda: not services.recognition.running, timeout=3000)


def test_simulation_and_recognition_are_exclusive(setup, qtbot):
    ctx, services, page, img, truth = setup
    page.take_screenshot()
    calibrate(page, truth)
    services.start_simulation("steady")
    services.start_recognition()
    assert not services.simulation.running and services.recognition.running
    services.start_simulation("steady")
    assert services.simulation.running and not services.recognition.running
