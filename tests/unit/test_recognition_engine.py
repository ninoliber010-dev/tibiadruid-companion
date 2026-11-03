import threading
import time

import pytest

from tdc.config.settings import PartySettings, RecognitionSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, HuntMode, Measurement, RecognitionState
from tdc.recognition.analyzers.bars import calibrate_bar
from tdc.recognition.analyzers.battle_list import find_entries
from tdc.recognition.capture import ImageCapturer
from tdc.recognition.engine import EngineConfig, RecognitionEngine
from tdc.recognition.geometry import Rect, anchors, resolve
from tdc.recognition.ocr.glyphs import GlyphLibrary
from tdc.recognition.service import RecognitionService, RecognitionWorker
from tdc.recognition.validator import ReadingValidator
from tdc.recognition.window import StaticWindowFinder, WindowInfo, title_matches
from tdc.simulation.synthetic_screen import Entry, Scene, crop, render
from tdc.storage.repositories import CalibrationRepository, GlyphRepository, Region

ORIGIN = (200, 100)   # where the fake Tibia client sits on the virtual screen


# ------------------------------------------------------------------ window / geometry
@pytest.mark.parametrize("title,ok", [
    ("Tibia", True), ("Tibia - Druid Name", True), ("Tibia Druid Companion", False),
    ("Druid Companion HUD", False), ("Notepad", False), ("TibiaWiki - Chrome", False), ("", False),
])
def test_title_matching(title, ok):
    assert title_matches(title, "Tibia") is ok


def test_region_anchors_follow_window_edges():
    right_panel = Region("health", 1110, 16, 160, 11, 1280, 800)
    assert anchors(right_panel) == ("right", "top")
    r = resolve(right_panel, 1600, 900)
    assert r.moved and r.rect.x == 1110 + 320 and r.rect.y == 16 and r.inside
    bottom_left = Region("party", 10, 700, 100, 50, 1280, 800)
    r = resolve(bottom_left, 1280, 1000)
    assert r.rect.y == 900 and r.rect.x == 10
    same = resolve(right_panel, 1280, 800)
    assert not same.moved and same.rect == Rect(1110, 16, 160, 11)
    assert not resolve(right_panel, 640, 400).inside or resolve(right_panel, 640, 400).rect.x >= 0


# ------------------------------------------------------------------ engine helpers
def calibrated_setup(scene: Scene, glyph_names=None):
    """Regions + bar calibration as a user would create them on a full-health screenshot."""
    full, truth = render(Scene(health=100, mana=100))
    regions = {k: Region(k, r.x, r.y, r.width, r.height, full.shape[1], full.shape[0])
               for k, r in truth.regions.items()}
    bars = {k: calibrate_bar(crop(full, truth.regions[k])) for k in ("health", "mana")}
    lib = GlyphLibrary()
    if glyph_names:
        teach, t2 = render(Scene(creatures=[Entry(n, 50) for n in glyph_names]))
        for e, n in zip(find_entries(crop(teach, t2.regions["battle_list"])), glyph_names):
            lib.learn(e.name_strip, n)
    img, _ = render(scene)
    cap = ImageCapturer(img, ORIGIN)
    finder = StaticWindowFinder(WindowInfo(1, "Tibia - Druid", Rect(*ORIGIN, img.shape[1], img.shape[0]), False, True))
    cfg = EngineConfig(regions=regions, bars=bars, glyphs=lib)
    return RecognitionEngine(finder, cap, cfg), cap


NAMES = ["Dragon Lord", "Dragon", "Hydra", "Frost Dragon", "Knight Partner"]


def test_full_cycle_reads_everything():
    scene = Scene(health=58, mana=33, creatures=[Entry("Dragon Lord", 85, True), Entry("Hydra", 20)],
                  party=[Entry("Knight Partner", 41)])
    engine, _ = calibrated_setup(scene, NAMES)
    engine.config.mode = HuntMode.DUO
    res = engine.cycle(123.0)
    r = res.reading
    assert res.status.state == RecognitionState.RUNNING
    assert r.health.value == pytest.approx(58, abs=1) and r.health.confidence > 0.9
    assert r.mana.value == pytest.approx(33, abs=1)
    assert [c.name for c in r.creatures] == ["Dragon Lord", "Hydra"]
    assert r.creatures[0].targeted and not r.creatures[1].targeted
    assert r.creatures[1].health.value == pytest.approx(20, abs=1.5)
    assert r.partner_health.value == pytest.approx(41, abs=1.5)
    assert r.timestamp == 123.0 and r.source == "recognition"


def test_partner_selected_by_name_over_slot():
    scene = Scene(party=[Entry("Dragon", 90), Entry("Knight Partner", 30)])
    engine, _ = calibrated_setup(scene, NAMES)
    engine.config.mode, engine.config.partner_name, engine.config.partner_slot = HuntMode.DUO, "Knight Partner", 1
    assert engine.cycle(0).reading.partner_health.value == pytest.approx(30, abs=1.5)


def test_partner_not_monitored_in_solo():
    engine, _ = calibrated_setup(Scene(party=[Entry("Knight Partner", 30)]))
    assert engine.cycle(0).reading.partner_health.value is None


def test_unknown_names_without_glyphs():
    engine, _ = calibrated_setup(Scene(creatures=[Entry("Dragon", 50)]))
    c = engine.cycle(0).reading.creatures[0]
    assert c.name is None and c.health.value == pytest.approx(50, abs=1.5)


def test_window_missing_minimized_and_uncalibrated():
    engine, _ = calibrated_setup(Scene())
    engine.finder = StaticWindowFinder(None)
    assert engine.cycle(0).status.state == RecognitionState.WINDOW_NOT_FOUND
    engine.finder = StaticWindowFinder(WindowInfo(1, "Tibia", Rect(0, 0, 1280, 800), True, True))
    assert engine.cycle(0).status.state == RecognitionState.MINIMIZED
    engine.finder = StaticWindowFinder(WindowInfo(1, "Tibia", Rect(*ORIGIN, 1280, 800), False, True))
    engine.set_config(EngineConfig())
    res = engine.cycle(0)
    assert res.status.state == RecognitionState.NOT_CALIBRATED and res.reading is None


def test_region_outside_window_is_unavailable():
    engine, _ = calibrated_setup(Scene())
    engine.finder = StaticWindowFinder(WindowInfo(1, "Tibia", Rect(*ORIGIN, 300, 200), False, True))
    engine.config.regions = {"health": Region("health", 400, 10, 100, 10, 0, 0)}
    assert engine.cycle(0).reading.health.reason == "region outside the Tibia window"


def test_window_moved_regions_follow():
    scene = Scene(health=64)
    engine, cap = calibrated_setup(scene)
    cap.origin = (900, 400)
    engine.finder = StaticWindowFinder(WindowInfo(1, "Tibia", Rect(900, 400, 1280, 800), False, True))
    assert engine.cycle(0).reading.health.value == pytest.approx(64, abs=1)


def test_resized_window_lowers_confidence_and_says_so():
    import numpy as np

    img, _ = render(Scene(health=64))
    wide = np.zeros((800, 1480, 3), np.uint8)
    wide[:, 200:] = img           # window 200 px wider; right panel keeps its distance to the edge
    engine, cap = calibrated_setup(Scene())
    cap.image, cap.origin = wide, (0, 0)
    engine.finder = StaticWindowFinder(WindowInfo(1, "Tibia", Rect(0, 0, 1480, 800), False, True))
    res = engine.cycle(0)
    assert res.reading.health.value == pytest.approx(64, abs=1)
    assert res.reading.health.confidence < 0.95
    assert "resized" in res.status.message


def test_change_detection_skips_unchanged_regions():
    engine, cap = calibrated_setup(Scene(health=70))
    engine.cycle(0)
    first = engine.analyses
    engine.cycle(1)
    assert engine.analyses == first          # nothing changed on screen
    img, _ = render(Scene(health=50))
    cap.image = img
    assert engine.cycle(2).reading.health.value == pytest.approx(50, abs=1)
    assert engine.analyses > first


def test_screen_mode_uses_fixed_rect():
    engine, _ = calibrated_setup(Scene(health=44))
    engine.finder = StaticWindowFinder(None)
    engine.config.capture_mode = "screen"
    engine.config.screen_rect = Rect(*ORIGIN, 1280, 800)
    assert engine.cycle(0).reading.health.value == pytest.approx(44, abs=1)
    engine.config.screen_rect = None
    assert engine.cycle(0).status.state == RecognitionState.ERROR


# ------------------------------------------------------------------ validator
def frames(*values, conf=0.95):
    return [FrameReading(Measurement(v, conf) if v is not None else Measurement.unavailable("x"),
                         Measurement(80, conf)) for v in values]


def run_validator(values, conf=0.95, n=3):
    v = ReadingValidator(EventBus(), lambda: 0.8, lambda: n)
    return [v.validate(f).health.value for f in frames(*values, conf=conf)]


def test_validator_low_confidence_unavailable():
    v = ReadingValidator(EventBus(), lambda: 0.8, lambda: 3)
    out = v.validate(frames(50, conf=0.6)[0]).health
    assert out.value is None and "low confidence" in out.reason


def test_validator_smooths_single_glitch_upwards():
    assert run_validator([70, 70, 71, 95, 70, 70])[3] <= 71     # one bad high frame does not show


def test_validator_passes_drops_immediately():
    out = run_validator([90, 90, 90, 40])
    assert out[3] == 40


def test_validator_confirms_large_rises():
    out = run_validator([30, 30, 85, 86, 86])
    assert out[2] == 30          # held for one frame
    assert out[3] in (85, 86)    # confirmed on the second frame


def test_validator_resets_on_missing_data():
    out = run_validator([60, None, 62])
    assert out[1] is None and out[2] == 62


def test_validator_publishes_validated():
    bus = EventBus()
    got = []
    bus.subscribe(Topic.READING_VALIDATED, got.append)
    ReadingValidator(bus, lambda: 0.8, lambda: 3)
    bus.publish(Topic.FRAME_READING, frames(50)[0])
    assert got and got[0].health.value == 50


# ------------------------------------------------------------------ worker / service
def test_worker_thread_publishes_and_stops():
    engine, _ = calibrated_setup(Scene(health=77))
    bus = EventBus()
    readings, statuses = [], []
    lock = threading.Lock()
    bus.subscribe(Topic.FRAME_READING, lambda r: (lock.acquire(), readings.append(r), lock.release()))
    bus.subscribe(Topic.RECOGNITION_STATUS, statuses.append)
    w = RecognitionWorker(engine, bus, lambda: 0.02, lambda: 0.05)
    w.start()
    deadline = time.time() + 3
    while len(readings) < 5 and time.time() < deadline:
        time.sleep(0.01)
    w.stop()
    assert len(readings) >= 5 and not w.running
    assert readings[0].health.value == pytest.approx(77, abs=1)
    assert statuses[0].state == RecognitionState.RUNNING
    assert statuses[-1].state == RecognitionState.STOPPED


def test_worker_survives_engine_errors():
    class Boom:
        def cycle(self, ts):
            raise RuntimeError("capture failed")

        def set_config(self, c):
            pass

    bus = EventBus()
    statuses = []
    bus.subscribe(Topic.RECOGNITION_STATUS, statuses.append)
    w = RecognitionWorker(Boom(), bus, lambda: 0.01, lambda: 0.01)
    w.start()
    time.sleep(0.1)
    assert w.running
    w.stop()
    assert statuses[0].state == RecognitionState.ERROR and "capture failed" in statuses[0].message


def test_service_builds_config_from_database(ctx):
    ctx.regions.save(Region("health", 10, 10, 100, 10, 1280, 800))
    CalibrationRepository(ctx.db).save("health", {"hue": 2.0, "start": 3, "end": 90})
    GlyphRepository(ctx.db).save_many({"3x3:ff80": "x"})
    ctx.creatures.set("Custom Boss", 3)
    ctx.config.update(RecognitionSettings, capture_mode="window", ocr_backend="template")
    ctx.config.update(PartySettings, partner_name="Knighty")
    svc = RecognitionService(ctx, StaticWindowFinder(None), ImageCapturer(render(Scene())[0]))
    cfg = svc.build_config()
    assert "health" in cfg.regions and cfg.bars["health"].hue == 2.0
    assert len(cfg.glyphs) == 1 and "Custom Boss" in cfg.matcher.names
    assert cfg.partner_name == "Knighty"
    ctx.regions.save(Region("mana", 10, 30, 100, 10, 1280, 800))
    ctx.bus.publish(Topic.REGIONS_CHANGED, "mana")
    assert "mana" in svc.engine.config.regions
