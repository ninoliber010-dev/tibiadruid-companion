"""Health / mana bar analysis by colour segmentation.

A bar is a horizontal strip whose left part is filled with a saturated colour and whose right
part is a dark "track". The filled fraction is the reading.

Confidence combines:
* step fit   — how well the columns follow "filled up to the edge, empty after it";
* track look — whether the unfilled part looks like a dark track (not, say, a white window
  covering the bar);
* calibration — an uncalibrated region is trusted a little less.

Best results come from *calibrating* the bar once at full health/mana: that records the fill
colour (hue) and the exact first/last column of the bar inside the region.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from tdc.core.models import Measurement


@dataclass
class BarCalibration:
    hue: float | None = None       # OpenCV hue 0-179 of the fill; None = any saturated colour
    hue_tol: float = 14.0
    min_sat: int = 90              # 0-255
    min_val: int = 70              # 0-255
    start: int | None = None       # first bar column inside the region
    end: int | None = None         # one past the last bar column
    top: int | None = None         # first bar row
    bottom: int | None = None      # one past the last bar row

    @property
    def calibrated(self) -> bool:
        return self.start is not None and self.end is not None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "BarCalibration":
        if not d:
            return cls()
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


def hue_distance(h: np.ndarray, center: float) -> np.ndarray:
    d = np.abs(h.astype(np.float32) - center)
    return np.minimum(d, 180 - d)


def fill_mask(hsv: np.ndarray, cal: BarCalibration) -> np.ndarray:
    m = (hsv[..., 1] >= cal.min_sat) & (hsv[..., 2] >= cal.min_val)
    if cal.hue is not None:
        m &= hue_distance(hsv[..., 0], cal.hue) <= cal.hue_tol
    return m


def close_gaps(flags: np.ndarray, max_gap: int = 3) -> np.ndarray:
    """Fill short False gaps between True values (text drawn over the bar, 1-px glitches)."""
    out = flags.copy()
    idx = np.flatnonzero(flags)
    if len(idx) < 2:
        return out
    gaps = np.diff(idx)
    for i, g in enumerate(gaps):
        if 1 < g <= max_gap + 1:
            out[idx[i] + 1: idx[i + 1]] = True
    return out


def _bridge_unknown(filled: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Columns hidden by text count as filled when the fill continues on both sides."""
    out = filled.copy()
    n = len(filled)
    i = 0
    while i < n:
        if known[i]:
            i += 1
            continue
        j = i
        while j < n and not known[j]:
            j += 1
        left = i > 0 and out[i - 1]
        right = j < n and out[j]
        if left and right:
            out[i:j] = True
        i = j
    return out


def analyze_bar(img_bgr: np.ndarray, cal: BarCalibration | None = None) -> Measurement:
    cal = cal or BarCalibration()
    if img_bgr is None or img_bgr.size == 0 or img_bgr.shape[1] < 8:
        return Measurement.unavailable("region too small")
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, w = hsv.shape[:2]
    x0 = cal.start if cal.start is not None else 0
    x1 = cal.end if cal.end is not None else w
    x0, x1 = max(0, min(x0, w - 1)), max(1, min(x1, w))
    if x1 - x0 < 8:
        return Measurement.unavailable("bar calibration does not fit the region")

    mask = fill_mask(hsv, cal)
    if cal.top is not None and cal.bottom is not None and 0 <= cal.top < cal.bottom <= h:
        rows = np.arange(cal.top, cal.bottom)
    else:
        row_ratio = mask[:, x0:x1].mean(axis=1)
        if row_ratio.max() <= 0:
            rows = np.arange(h)
        else:
            rows = np.flatnonzero(row_ratio >= 0.5 * row_ratio.max())
    band = mask[rows][:, x0:x1]
    band_hsv = hsv[rows][:, x0:x1]
    band_val = band_hsv[..., 2]
    bar_w = x1 - x0

    # Text drawn over the bar (white/grey, unsaturated) is neither fill nor track: ignore it.
    neutral = (band_hsv[..., 1] < 60) & (band_val > 170)
    usable = (~neutral).sum(axis=0)
    known = usable >= max(2, int(0.25 * len(rows)))
    col_ratio = np.where(known, (band & ~neutral).sum(axis=0) / np.maximum(1, usable), 0.0)
    filled = close_gaps(known & (col_ratio >= 0.5))
    filled = _bridge_unknown(filled, known)

    if not filled.any():
        # Empty bar (0 %) or not a bar at all. Only a uniform dark track counts as 0 %.
        dark = float((band_val < 110).mean())
        uniform = float(band_val.std()) < 25
        if dark > 0.9 and uniform:
            return Measurement(0.0, 0.75 if cal.calibrated else 0.6, "bar empty or not visible")
        return Measurement(None, 0.1, "no bar colour found in region")

    # The fill is anchored at the left of the bar.
    first = int(np.argmax(filled))
    if first > max(2, bar_w * 0.05):
        # Fill does not start at the left edge: not our bar (or calibration is off).
        return Measurement(None, 0.25, "bar fill does not start at the left edge")
    edge = first
    while edge < bar_w and filled[edge]:
        edge += 1

    expected = np.arange(bar_w) < edge
    step_fit = float((filled == expected).mean())
    right_cols = [c for c in range(edge, bar_w) if known[c]]
    if right_cols:
        rv = np.where(neutral[:, right_cols], np.nan, band_val[:, right_cols].astype(float))
        track_ok = float((np.nanmean(rv, axis=0) < 120).mean())
    else:
        track_ok = 1.0
    known_left = known[:edge]
    strength = float(col_ratio[:edge][known_left].mean()) if known_left.any() else 0.0
    coverage = float(known.mean())
    confidence = (step_fit * (0.45 + 0.55 * track_ok) * (0.85 + 0.15 * min(1.0, strength / 0.7))
                  * (0.6 + 0.4 * coverage))
    reason = ""
    if edge < bar_w and not known[edge]:
        # The fill runs into something covering the bar: the real edge may be hidden.
        confidence *= 0.4
        reason = "bar partly covered"
    if not cal.calibrated:
        confidence *= 0.92
    value = 100.0 * edge / bar_w
    return Measurement(round(value, 1), round(float(np.clip(confidence, 0, 1)), 3), reason)


def calibrate_bar(img_bgr: np.ndarray, base: BarCalibration | None = None) -> BarCalibration:
    """Learn colour and extents from a screenshot of a FULL bar. Raises ValueError if unusable."""
    base = base or BarCalibration()
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    loose = BarCalibration(min_sat=base.min_sat, min_val=base.min_val)
    mask = fill_mask(hsv, loose)
    if mask.sum() < 20:
        raise ValueError("No coloured bar found in this region.")
    hues = hsv[..., 0][mask].astype(np.float32)
    # Circular median of hue (red wraps around 0/180).
    angles = hues * (2 * np.pi / 180)
    mean_angle = np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())
    hue = float((mean_angle * 180 / (2 * np.pi)) % 180)

    cal = BarCalibration(hue=round(hue, 1), hue_tol=base.hue_tol, min_sat=base.min_sat, min_val=base.min_val)
    m = fill_mask(hsv, cal)
    row_ratio = m.mean(axis=1)
    rows = np.flatnonzero(row_ratio >= 0.5 * row_ratio.max())
    col_ratio = m[rows].mean(axis=0)
    cols = np.flatnonzero(close_gaps(col_ratio >= 0.34))
    if len(cols) < 10:
        raise ValueError("The bar is too short; select a wider region.")
    cal.start, cal.end = int(cols[0]), int(cols[-1]) + 1
    cal.top, cal.bottom = int(rows[0]), int(rows[-1]) + 1
    _check_looks_like_bar(hsv, m, cal)
    return cal


def _check_looks_like_bar(hsv: np.ndarray, mask: np.ndarray, cal: BarCalibration) -> None:
    """A status bar is one even colour framed by something darker (border or track)."""
    h, w = hsv.shape[:2]
    inside = mask[cal.top:cal.bottom, cal.start:cal.end]
    if inside.mean() < 0.85:
        raise ValueError("The coloured area is not solid; make sure the bar is full and not covered.")
    fill_v = hsv[cal.top:cal.bottom, cal.start:cal.end, 2][inside]
    fill_h = hsv[cal.top:cal.bottom, cal.start:cal.end, 0][inside].astype(np.float32)
    spread = float(np.median(hue_distance(fill_h, cal.hue or 0)))
    if spread > 6 or float(fill_v.std()) > 35:
        raise ValueError("The colour is not even enough to be a status bar.")
    ring = []
    if cal.top > 0:
        ring.append(hsv[cal.top - 1, cal.start:cal.end, 2])
    if cal.bottom < h:
        ring.append(hsv[cal.bottom, cal.start:cal.end, 2])
    if cal.start > 0:
        ring.append(hsv[cal.top:cal.bottom, cal.start - 1, 2])
    if cal.end < w:
        ring.append(hsv[cal.top:cal.bottom, cal.end, 2])
    if not ring:
        raise ValueError("Draw the rectangle a few pixels larger than the bar so its border is included.")
    border_v = float(np.concatenate(ring).astype(np.float32).mean())
    if border_v > float(fill_v.mean()) - 30:
        raise ValueError("No bar border found around the coloured area; is this really the bar?")
