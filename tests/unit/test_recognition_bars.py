import numpy as np
import pytest

from tdc.recognition.analyzers.bars import BarCalibration, analyze_bar, calibrate_bar
from tdc.recognition.geometry import Rect
from tdc.simulation.synthetic_screen import Scene, crop, render


@pytest.fixture(scope="module")
def cals():
    img, t = render(Scene(health=100, mana=100))
    return {k: calibrate_bar(crop(img, t.regions[k])) for k in ("health", "mana")}, t


def read(scene, kind, cal=None):
    img, t = render(scene)
    return analyze_bar(crop(img, t.regions[kind]), cal)


@pytest.mark.parametrize("value", [100, 95, 81, 72.5, 60, 50, 35, 20, 7, 1])
@pytest.mark.parametrize("kind", ["health", "mana"])
def test_calibrated_accuracy(cals, kind, value):
    c, _ = cals
    m = read(Scene(health=value, mana=value), kind, c[kind])
    assert m.value == pytest.approx(value, abs=1.0)
    assert m.confidence >= 0.95


def test_calibration_learns_colour_and_extents(cals):
    c, t = cals
    h, m = c["health"], c["mana"]
    assert h.calibrated and m.calibrated
    assert min(abs(h.hue), abs(180 - h.hue)) < 10      # red
    assert 100 < m.hue < 125                            # blue
    inner, region = t.bar_inner["health"], t.regions["health"]
    assert (h.start, h.end) == (inner.x - region.x, inner.right - region.x)


def test_calibration_rejects_region_without_bar():
    with pytest.raises(ValueError):
        calibrate_bar(np.full((15, 100, 3), 60, np.uint8))


def test_calibration_rejects_textured_game_view():
    img, _ = render(Scene())
    with pytest.raises(ValueError):
        calibrate_bar(crop(img, Rect(10, 300, 100, 20)))


def test_calibration_needs_border_margin(cals):
    _, t = cals
    img, _ = render(Scene(health=100))
    with pytest.raises(ValueError, match="larger"):
        calibrate_bar(crop(img, t.bar_inner["health"]))


def test_uncalibrated_is_close_but_less_confident(cals):
    c, _ = cals
    raw = read(Scene(health=50), "health")
    cal = read(Scene(health=50), "health", c["health"])
    assert raw.value == pytest.approx(50, abs=4)
    assert raw.confidence < cal.confidence


@pytest.mark.parametrize("noise", [4, 8, 12])
def test_noise_tolerance(cals, noise):
    c, _ = cals
    m = read(Scene(health=63, noise=noise, seed=noise), "health", c["health"])
    assert m.value == pytest.approx(63, abs=1.5) and m.confidence >= 0.85


def test_text_over_bar(cals):
    c, _ = cals
    for v in (90, 55, 30):
        m = read(Scene(health=v, mana=v, bar_text=True), "health", c["health"])
        assert m.value == pytest.approx(v, abs=1.5), v
        assert m.confidence >= 0.8


def test_hue_filter_ignores_other_colours(cals):
    c, t = cals
    img, _ = render(Scene(mana=80))
    # Mana calibration applied to the health bar must not "see" a red bar.
    m = analyze_bar(crop(img, t.regions["health"]), c["mana"])
    assert m.value is None or m.confidence < 0.8


def test_cover_hiding_the_fill_edge_is_unreliable(cals):
    c, t = cals
    r = t.regions["health"]
    # 80 % health, but a window covers the bar from ~53 % onwards: the edge is hidden.
    m = read(Scene(health=80, occlude=Rect(r.x + 90, r.y, 200, 30)), "health", c["health"])
    assert m.value is None or m.confidence < 0.8


def test_cover_after_visible_edge_still_reads(cals):
    c, t = cals
    r = t.regions["health"]
    # 40 % health; the cover starts after the visible end of the fill, so the value is known.
    m = read(Scene(health=40, occlude=Rect(r.x + 110, r.y, 200, 30)), "health", c["health"])
    assert m.value == pytest.approx(40, abs=1.0)


def test_fully_covered_bar_is_unavailable(cals):
    c, t = cals
    m = read(Scene(health=40, occlude=Rect(t.regions["health"].x - 5, 0, 400, 60)), "health", c["health"])
    assert m.value is None


def test_empty_bar_reads_zero_with_reduced_confidence(cals):
    c, _ = cals
    m = read(Scene(health=0), "health", c["health"])
    assert m.value == 0 and m.confidence < 0.8   # dead or hidden: never trusted as fact by default


def test_tiny_or_empty_region():
    assert analyze_bar(np.zeros((5, 3, 3), np.uint8)).value is None
    assert analyze_bar(np.zeros((0, 0, 3), np.uint8)).value is None


def test_calibration_roundtrip():
    c = BarCalibration(hue=3.5, start=4, end=150, top=2, bottom=9)
    assert BarCalibration.from_dict(c.to_dict()) == c
    assert BarCalibration.from_dict({"hue": 1, "unknown": 5}).hue == 1
    assert BarCalibration.from_dict(None) == BarCalibration()
