"""Battle list / party list analysis.

Each entry in Tibia's battle and party lists has a name and, under it, a small health bar
with a black border. Entries are found by detecting those bordered bars (font independent),
the fill fraction gives health, and the strip above the bar is passed to OCR for the name.
A red frame drawn left of an entry marks the creature you are attacking.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from tdc.core.models import Measurement
from tdc.recognition.analyzers.bars import close_gaps
from tdc.recognition.geometry import Rect


@dataclass
class ListProfile:
    border_max_val: int = 30      # border pixels are darker than this (0-255)
    min_bar_width: int = 24
    max_bar_height: int = 10
    min_bar_height: int = 3
    name_height: int = 14         # pixels above the bar that contain the name
    fill_min_sat: int = 80
    fill_min_val: int = 80


@dataclass
class ListEntry:
    bar: Rect                     # health bar, region coordinates
    health: Measurement
    name_strip: np.ndarray        # BGR crop above the bar
    targeted: bool
    slot: int


def _is_frame(dark: np.ndarray) -> bool:
    """True if the dark component's bounding box looks like a rectangular border."""
    h, w = dark.shape
    edges = [dark[0, :], dark[-1, :], dark[:, 0], dark[:, -1]]
    return all(e.mean() >= 0.85 for e in edges) and h >= 3 and w >= 3


def find_entries(img_bgr: np.ndarray, profile: ListProfile | None = None) -> list[ListEntry]:
    p = profile or ListProfile()
    if img_bgr is None or img_bgr.size == 0:
        return []
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    dark = (hsv[..., 2] <= p.border_max_val).astype(np.uint8)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=4)
    bars: list[Rect] = []
    for i in range(1, n):
        x, y, w, h, _area = stats[i]
        if not (p.min_bar_height <= h <= p.max_bar_height and w >= p.min_bar_width and w >= 5 * h):
            continue
        if not _is_frame(dark[y:y + h, x:x + w].astype(bool)):
            continue
        bars.append(Rect(int(x), int(y), int(w), int(h)))
    bars.sort(key=lambda r: (r.y, r.x))

    entries = []
    for slot, bar in enumerate(bars):
        entries.append(ListEntry(
            bar=bar, health=_bar_fill(hsv, bar, p),
            name_strip=img_bgr[max(0, bar.y - p.name_height - 1):max(0, bar.y - 1), bar.x:].copy(),
            targeted=_targeted(img_bgr, bar, p), slot=slot,
        ))
    return entries


def _bar_fill(hsv: np.ndarray, bar: Rect, p: ListProfile) -> Measurement:
    inner = hsv[bar.y + 1:bar.bottom - 1, bar.x + 1:bar.right - 1]
    if inner.size == 0:
        return Measurement.unavailable("bar too small")
    fill = (inner[..., 1] >= p.fill_min_sat) & (inner[..., 2] >= p.fill_min_val)
    darkish = inner[..., 2] <= max(60, p.border_max_val * 2)
    col_ratio = fill.mean(axis=0)
    filled = close_gaps(col_ratio >= 0.5, 1)
    w = inner.shape[1]
    edge = 0
    while edge < w and filled[edge]:
        edge += 1
    expected = np.arange(w) < edge
    step_fit = float((filled == expected).mean())
    explained = float((fill | darkish).mean())   # every inner pixel is fill or empty track
    conf = step_fit * explained
    return Measurement(round(100.0 * edge / w, 1), round(conf, 3))


def _targeted(img_bgr: np.ndarray, bar: Rect, p: ListProfile) -> bool:
    # Only this entry's own rows: the frame of the entry above must not count.
    top = max(0, bar.y - p.name_height + 2)
    area = img_bgr[top:bar.bottom, :max(1, bar.x)]
    if area.size == 0:
        return False
    b, g, r = area[..., 0].astype(int), area[..., 1].astype(int), area[..., 2].astype(int)
    red = (r >= 170) & (g <= 70) & (b <= 70)
    return int(red.sum()) >= 12
