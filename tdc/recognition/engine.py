"""RecognitionEngine: one capture-and-analyse cycle. Qt-free and synchronous (easy to test).

The worker thread in ``worker.py`` calls ``cycle()`` repeatedly.
"""

from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass, field

import numpy as np

from tdc.core.models import (
    CreatureReading, FrameReading, HuntMode, Measurement, RecognitionState, RecognitionStatus,
)
from tdc.recognition.analyzers.bars import BarCalibration, analyze_bar
from tdc.recognition.analyzers.battle_list import ListEntry, ListProfile, find_entries
from tdc.recognition.capture import Capturer
from tdc.recognition.creatures import NameMatcher, similarity
from tdc.recognition.geometry import Rect, resolve
from tdc.recognition.ocr.glyphs import GlyphLibrary
from tdc.recognition.window import WindowFinder
from tdc.storage.repositories import Region

log = logging.getLogger(__name__)

RESIZED_PENALTY = 0.9        # confidence factor while the window size differs from calibration
GAME_VIEW_PENALTY = 0.85     # creature bars read from the game view are noisier than the battle list


@dataclass
class EngineConfig:
    """Immutable snapshot of everything the engine needs; swapped atomically on changes."""

    capture_mode: str = "window"
    window_title: str = "Tibia"
    screen_rect: Rect | None = None          # used in "screen" mode
    regions: dict[str, Region] = field(default_factory=dict)
    bars: dict[str, BarCalibration] = field(default_factory=dict)
    list_profile: ListProfile = field(default_factory=ListProfile)
    glyphs: GlyphLibrary = field(default_factory=GlyphLibrary)
    ocr_backend: str = "template"            # template | tesseract | off
    tesseract_path: str = ""
    matcher: NameMatcher = field(default_factory=NameMatcher)
    mode: HuntMode = HuntMode.SOLO
    monitor_partner: bool = True
    partner_name: str = ""
    partner_slot: int = 1


@dataclass
class CycleResult:
    status: RecognitionStatus
    reading: FrameReading | None
    client: Rect | None = None


class RecognitionEngine:
    def __init__(self, finder: WindowFinder, capturer: Capturer, config: EngineConfig | None = None) -> None:
        self.finder = finder
        self.capturer = capturer
        self.config = config or EngineConfig()
        self._cache: dict[str, tuple[int, object]] = {}   # region kind -> (crc, analysis result)
        self._tesseract = None
        self.analyses = 0       # number of analyzer runs (change detection skips the rest)

    def set_config(self, config: EngineConfig) -> None:
        self.config = config
        self._cache.clear()
        self._tesseract = None

    # ------------------------------------------------------------------ helpers
    def _client(self) -> tuple[Rect | None, RecognitionStatus | None]:
        cfg = self.config
        if cfg.capture_mode == "screen":
            if cfg.screen_rect is None:
                return None, RecognitionStatus(RecognitionState.ERROR, "Selected monitor not found")
            return cfg.screen_rect, None
        info = self.finder.find(cfg.window_title)
        if info is None:
            return None, RecognitionStatus(RecognitionState.WINDOW_NOT_FOUND, "Tibia window not found")
        if info.minimized or not info.visible:
            return None, RecognitionStatus(RecognitionState.MINIMIZED, "Tibia is minimized")
        if info.client.width < 50 or info.client.height < 50:
            return None, RecognitionStatus(RecognitionState.MINIMIZED, "Tibia window is too small")
        return info.client, None

    def _grab(self, kind: str, client: Rect) -> tuple[np.ndarray | None, bool, str]:
        region = self.config.regions.get(kind)
        if region is None:
            return None, False, "not calibrated"
        res = resolve(region, client.width, client.height)
        if not res.inside:
            return None, res.moved, "region outside the Tibia window"
        img = self.capturer.grab(res.rect.translated(client.x, client.y))
        return img, res.moved, ""

    def _cached(self, kind: str, img: np.ndarray, fn):
        crc = zlib.crc32(img.tobytes())
        hit = self._cache.get(kind)
        if hit and hit[0] == crc:
            return hit[1]
        result = fn(img)
        self.analyses += 1
        self._cache[kind] = (crc, result)
        return result

    def _read_name(self, strip: np.ndarray) -> tuple[str | None, float]:
        cfg = self.config
        if cfg.ocr_backend == "off" or strip.size == 0:
            return None, 0.0
        if cfg.ocr_backend == "tesseract":
            if self._tesseract is None:
                from tdc.recognition.ocr.tesseract import TesseractOcr

                self._tesseract = TesseractOcr(cfg.tesseract_path)
            raw, conf = self._tesseract.read(strip)
        else:
            if not len(cfg.glyphs):
                return None, 0.0
            raw, conf = cfg.glyphs.read(strip)
        if not raw:
            return None, 0.0
        name, sim = cfg.matcher.match(raw)
        if name is None:
            # Unknown creature: show what was read if it is clean, otherwise nothing.
            return (raw, conf * 0.8) if "?" not in raw and conf >= 0.95 else (None, 0.0)
        return name, round(conf * sim, 3)

    # ------------------------------------------------------------------ cycle
    def _bar(self, kind: str, client: Rect) -> Measurement:
        img, moved, why = self._grab(kind, client)
        if img is None:
            return Measurement.unavailable(why)
        cal = self.config.bars.get(kind)
        m: Measurement = self._cached(kind, img, lambda im: analyze_bar(im, cal))
        if moved and m.value is not None:
            m = Measurement(m.value, round(m.confidence * RESIZED_PENALTY, 3), "window resized since calibration")
        return m

    def _entries(self, kind: str, client: Rect) -> tuple[list[ListEntry] | None, bool, str]:
        img, moved, why = self._grab(kind, client)
        if img is None:
            return None, moved, why
        entries = self._cached(kind, img, lambda im: find_entries(im, self.config.list_profile))
        return entries, moved, ""

    def _creatures(self, client: Rect) -> tuple[tuple[CreatureReading, ...], float]:
        source = "battle_list" if "battle_list" in self.config.regions else "creatures"
        entries, moved, why = self._entries(source, client)
        if entries is None:
            return (), 0.0
        factor = (RESIZED_PENALTY if moved else 1.0) * (GAME_VIEW_PENALTY if source == "creatures" else 1.0)
        out = []
        for e in entries:
            name, name_conf = self._read_name(e.name_strip)
            hm = Measurement(e.health.value, round(e.health.confidence * factor, 3))
            out.append(CreatureReading(name, hm, name_conf, e.slot, targeted=e.targeted))
        list_conf = float(np.mean([c.health.confidence for c in out])) if out else 0.95 * factor
        return tuple(out), round(list_conf, 3)

    def _partner(self, client: Rect) -> Measurement:
        cfg = self.config
        if cfg.mode != HuntMode.DUO or not cfg.monitor_partner:
            return Measurement.unavailable("not monitored")
        entries, moved, why = self._entries("party", client)
        if entries is None:
            return Measurement.unavailable(why)
        if not entries:
            return Measurement.unavailable("no one in the party list")
        chosen = None
        if cfg.partner_name:
            scored = []
            for e in entries:
                raw, _ = self._read_name(e.name_strip) if cfg.ocr_backend != "off" else (None, 0)
                if raw:
                    scored.append((similarity(raw, cfg.partner_name), e))
            if scored:
                best = max(scored, key=lambda t: t[0])
                if best[0] >= 0.75:
                    chosen = best[1]
        if chosen is None:
            idx = cfg.partner_slot - 1
            if idx >= len(entries):
                return Measurement.unavailable(f"party list has no entry {cfg.partner_slot}")
            chosen = entries[idx]
        m = chosen.health
        if moved and m.value is not None:
            m = Measurement(m.value, round(m.confidence * RESIZED_PENALTY, 3))
        return m

    def cycle(self, timestamp: float) -> CycleResult:
        client, problem = self._client()
        if problem:
            self._cache.clear()
            return CycleResult(problem, None)
        assert client is not None
        if not ({"health", "mana"} & set(self.config.regions)):
            return CycleResult(RecognitionStatus(RecognitionState.NOT_CALIBRATED,
                                                 "Health and mana regions are not calibrated"), None, client)
        health = self._bar("health", client)
        mana = self._bar("mana", client)
        creatures, creatures_conf = self._creatures(client)
        partner = self._partner(client)
        reading = FrameReading(health, mana, partner, creatures, creatures_conf, timestamp, source="recognition")
        resized = any(resolve(r, client.width, client.height).moved for r in self.config.regions.values())
        msg = "Live" + (" · window resized since calibration" if resized else "")
        return CycleResult(RecognitionStatus(RecognitionState.RUNNING, msg), reading, client)
