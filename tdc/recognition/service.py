"""Recognition worker thread and the service that feeds it configuration. Qt-free.

The worker never touches the UI: it publishes ``FrameReading`` and ``RecognitionStatus`` on
the event bus, and the bus's dispatcher delivers them on the GUI thread.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from tdc.app_context import AppContext
from tdc.config.settings import PartySettings, RecognitionSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import RecognitionState, RecognitionStatus
from tdc.recognition.analyzers.bars import BarCalibration
from tdc.recognition.capture import Capturer, MssCapturer
from tdc.recognition.creatures import KNOWN_CREATURES, NameMatcher
from tdc.recognition.engine import EngineConfig, RecognitionEngine
from tdc.recognition.geometry import Rect
from tdc.recognition.ocr.glyphs import GlyphLibrary
from tdc.recognition.window import WindowFinder, default_window_finder
from tdc.storage.repositories import CalibrationRepository, GlyphRepository

log = logging.getLogger(__name__)

STATUS_REFRESH_S = 2.0
ERROR_BACKOFF_S = 2.0


class RecognitionWorker:
    def __init__(self, engine: RecognitionEngine, bus: EventBus, interval_s: Callable[[], float],
                 idle_interval_s: Callable[[], float]) -> None:
        self.engine = engine
        self.bus = bus
        self._interval = interval_s
        self._idle = idle_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.cycles = 0
        self.last_status: RecognitionStatus | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tdc-recognition", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None
        self.last_status = RecognitionStatus(RecognitionState.STOPPED, "Not running")
        self.bus.publish(Topic.RECOGNITION_STATUS, self.last_status)
        self.bus.publish(Topic.RECOMMENDATIONS, [])

    def set_config(self, config) -> None:
        with self._lock:
            self.engine.set_config(config)

    def _run(self) -> None:
        log.info("Recognition worker started")
        window_start, frames, last_status_at = time.monotonic(), 0, 0.0
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                with self._lock:
                    result = self.engine.cycle(time.time())
                status = result.status
            except Exception as exc:  # noqa: BLE001 - keep running, report, back off
                log.exception("Recognition cycle failed")
                status, result = RecognitionStatus(RecognitionState.ERROR, f"Recognition error: {exc}"), None
            self.cycles += 1
            if result is not None and result.reading is not None:
                self.bus.publish(Topic.FRAME_READING, result.reading)
                frames += 1
            now = time.monotonic()
            fps = frames / max(1e-6, now - window_start)
            changed = self.last_status is None or (status.state, status.message) != (
                self.last_status.state, self.last_status.message)
            if changed or now - last_status_at >= STATUS_REFRESH_S:
                status = RecognitionStatus(status.state, status.message, round(fps, 1), status.last_error)
                self.last_status = status
                self.bus.publish(Topic.RECOGNITION_STATUS, status)
                last_status_at = now
                if now - window_start > 10:
                    window_start, frames = now, 0
            if status.state == RecognitionState.RUNNING:
                wait = self._interval()
            elif status.state == RecognitionState.ERROR:
                wait = ERROR_BACKOFF_S
            else:
                wait = self._idle()
            self._stop.wait(max(0.0, wait - (time.monotonic() - t0)))
        log.info("Recognition worker stopped")


class RecognitionService:
    """Owns the engine + worker and rebuilds the engine config when settings change."""

    def __init__(self, ctx: AppContext, finder: WindowFinder | None = None,
                 capturer: Capturer | None = None) -> None:
        self.ctx = ctx
        self.capturer = capturer or MssCapturer()
        self.finder = finder or default_window_finder()
        self.calibration = CalibrationRepository(ctx.db)
        self.glyph_repo = GlyphRepository(ctx.db)
        self.engine = RecognitionEngine(self.finder, self.capturer, self.build_config())
        rs = lambda: ctx.config.get(RecognitionSettings)  # noqa: E731
        self.worker = RecognitionWorker(self.engine, ctx.bus, lambda: rs().interval_ms / 1000,
                                        lambda: rs().idle_interval_ms / 1000)
        for topic in (Topic.CONFIG_CHANGED, Topic.REGIONS_CHANGED, Topic.PROFILE_CHANGED):
            ctx.bus.subscribe(topic, lambda _p: self.reload())

    @property
    def running(self) -> bool:
        return self.worker.running

    def screen_rect(self, index: int) -> Rect | None:
        monitors = getattr(self.capturer, "monitors", None)
        if monitors is None:
            return None
        try:
            mons = monitors()
        except Exception:  # noqa: BLE001
            return None
        return mons[index - 1] if 0 < index <= len(mons) else None

    def build_config(self) -> EngineConfig:
        rs = self.ctx.config.get(RecognitionSettings)
        party = self.ctx.config.get(PartySettings)
        names = list(KNOWN_CREATURES) + list(self.ctx.creatures.all())
        return EngineConfig(
            capture_mode=rs.capture_mode,
            window_title=rs.window_title,
            screen_rect=self.screen_rect(rs.screen_index) if rs.capture_mode == "screen" else None,
            regions=self.ctx.regions.all(),
            bars={k: BarCalibration.from_dict(v) for k, v in self.calibration.all().items() if k in ("health", "mana")},
            glyphs=GlyphLibrary(self.glyph_repo.all()),
            ocr_backend=rs.ocr_backend,
            tesseract_path=rs.tesseract_path,
            matcher=NameMatcher(names),
            mode=self.ctx.mode,
            monitor_partner=party.monitor_partner,
            partner_name=party.partner_name,
            partner_slot=party.partner_slot,
        )

    def reload(self) -> None:
        self.worker.set_config(self.build_config())

    def start(self) -> None:
        self.reload()
        self.worker.start()

    def stop(self) -> None:
        if self.worker.running:
            self.worker.stop()


class CaptureUnavailable(Exception):
    """A calibration screenshot cannot be taken right now (message is user-facing)."""


def capture_reference(service: "RecognitionService"):
    """Screenshot of the Tibia client area (window mode) or the chosen monitor (screen mode).

    Returns (BGR image, client rect in screen coordinates, description).
    """
    rs = service.ctx.config.get(RecognitionSettings)
    if rs.capture_mode == "screen":
        rect = service.screen_rect(rs.screen_index)
        if rect is None:
            raise CaptureUnavailable(f"Monitor {rs.screen_index} was not found.")
        return service.capturer.grab(rect), rect, f"Monitor {rs.screen_index} ({rect.width}×{rect.height})"
    info = service.finder.find(rs.window_title)
    if info is None:
        raise CaptureUnavailable(
            f"No window titled “{rs.window_title}” was found. Start Tibia (windowed or borderless), "
            "or switch Capture mode to “screen” under Configuration → Visual Recognition.")
    if info.minimized or not info.visible:
        raise CaptureUnavailable("Tibia is minimized. Restore the window and try again.")
    return service.capturer.grab(info.client), info.client, f"{info.title} ({info.client.width}×{info.client.height})"
