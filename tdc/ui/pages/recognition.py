"""Visual Recognition page: calibration and live status."""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from tdc.app_context import AppContext
from tdc.config.settings import RecognitionSettings
from tdc.core.events import Topic
from tdc.core.models import RecognitionState, RecognitionStatus
from tdc.recognition.analyzers.bars import BarCalibration, analyze_bar, calibrate_bar
from tdc.recognition.analyzers.battle_list import find_entries
from tdc.recognition.geometry import Rect
from tdc.recognition.ocr.glyphs import GlyphLibrary
from tdc.recognition.service import CaptureUnavailable, capture_reference
from tdc.simulation.synthetic_screen import demo_scene, render
from tdc.storage.repositories import Region
from tdc.ui.region_canvas import REGION_COLORS, REGION_LABELS, RegionCanvas, bgr_to_pixmap
from tdc.ui.theme import C
from tdc.ui.widgets import Card, Page

log = logging.getLogger(__name__)
MAX_TEACH_ROWS = 8
DISPLAY_ORDER = ("health", "mana", "battle_list", "party", "creatures")
PREVIEW_MAX_W, PREVIEW_MAX_H = 340, 110


def crop(img: np.ndarray, r: Rect) -> np.ndarray:
    return img[r.y:r.bottom, r.x:r.right].copy()


class RegionRow(QWidget):
    """One region: colour chip, name, status, test result, actions."""

    def __init__(self, kind: str, page: "RecognitionPage") -> None:
        super().__init__()
        self.kind = kind
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setHorizontalSpacing(8)
        self.select_btn = QPushButton(REGION_LABELS[kind])
        self.select_btn.setCheckable(True)
        self.select_btn.setToolTip("Select, then drag a rectangle on the screenshot")
        self.select_btn.setStyleSheet(f"QPushButton {{ border-left: 4px solid {REGION_COLORS[kind]}; text-align: left; }}")
        self.status = QLabel("not set")
        self.status.setObjectName("Dim")
        self.result = QLabel("")
        self.result.setObjectName("Muted")
        self.preview = QLabel()
        self.preview.setMinimumHeight(4)
        self.select_btn.setMinimumWidth(170)
        lay.addWidget(self.select_btn, 0, 0)
        self.learn_btn = None
        col = 1
        lay.setColumnStretch(0, 1)
        if kind in ("health", "mana"):
            self.learn_btn = QPushButton("Learn bar")
            self.learn_btn.setToolTip("Do this while the bar is FULL: learns its colour and exact edges")
            self.learn_btn.clicked.connect(lambda: page.learn_bar(kind))
            lay.addWidget(self.learn_btn, 0, col)
            col += 1
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(lambda: page.clear_region(kind))
        lay.addWidget(self.clear_btn, 0, col)
        self.status.setWordWrap(True)
        self.result.setWordWrap(True)
        lay.addWidget(self.status, 1, 0, 1, col + 1)
        lay.addWidget(self.result, 2, 0, 1, col + 1)
        lay.addWidget(self.preview, 3, 0, 1, col + 1)


class TeachRow(QWidget):
    def __init__(self, page: "RecognitionPage") -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.image = QLabel()
        self.image.setFixedWidth(200)
        self.read = QLabel("")
        self.read.setObjectName("Dim")
        self.read.setFixedWidth(130)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type the name exactly")
        self.btn = QPushButton("Teach")
        self.btn.clicked.connect(lambda: page.teach(self))
        lay.addWidget(self.image)
        lay.addWidget(self.read)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.btn)
        self.strip: np.ndarray | None = None


class RecognitionPage(Page):
    def __init__(self, ctx: AppContext, services=None) -> None:
        super().__init__("Visual Recognition",
                         "Show the app where Tibia draws your bars and lists. It only reads screen pixels.")
        self.ctx = ctx
        self.services = services
        self.image: np.ndarray | None = None
        self.state = RecognitionState.STOPPED

        # Status --------------------------------------------------------------------
        status = Card("Live recognition")
        row = QHBoxLayout()
        self.state_dot = QLabel("●")
        self.state_label = QLabel("Not running")
        self.state_label.setObjectName("CardValue")
        self.toggle_btn = QPushButton("Start recognition")
        self.toggle_btn.setObjectName("Primary")
        row.addWidget(self.state_dot)
        row.addWidget(self.state_label, 1)
        row.addWidget(self.toggle_btn)
        status.body.addLayout(row)
        self.state_detail = QLabel("")
        self.state_detail.setObjectName("Dim")
        self.state_detail.setWordWrap(True)
        status.body.addWidget(self.state_detail)
        self.content.addWidget(status)

        # Calibration ---------------------------------------------------------------------
        cal = Card("Calibration")
        steps = QLabel(
            "1. Take a screenshot while Tibia shows full health and mana.  "
            "2. Pick a region below and drag a rectangle around it on the screenshot.  "
            "3. Press “Learn bar” for health and mana.  4. Teach creature names further down.")
        steps.setWordWrap(True)
        steps.setObjectName("Dim")
        cal.body.addWidget(steps)
        tools = QHBoxLayout()
        self.shot_btn = QPushButton("Take screenshot of Tibia")
        self.load_btn = QPushButton("Load image…")
        self.demo_btn = QPushButton("Load demo screenshot")
        self.demo_btn.setToolTip("A synthetic Tibia-like image to try calibration without the game")
        self.fit_btn = QPushButton("Fit")
        self.zoom_btn = QPushButton("Zoom +")
        for b in (self.shot_btn, self.load_btn, self.demo_btn):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(self.fit_btn)
        tools.addWidget(self.zoom_btn)
        cal.body.addLayout(tools)
        self.image_info = QLabel("No screenshot")
        self.image_info.setObjectName("Muted")
        cal.body.addWidget(self.image_info)

        split = QHBoxLayout()
        self.canvas = RegionCanvas()
        split.addWidget(self.canvas, 3)
        side = QVBoxLayout()
        self.region_group = QButtonGroup(self)
        self.region_group.setExclusive(True)
        self.rows: dict[str, RegionRow] = {}
        for kind in DISPLAY_ORDER:
            rr = RegionRow(kind, self)
            self.rows[kind] = rr
            self.region_group.addButton(rr.select_btn)
            rr.select_btn.clicked.connect(lambda _=False, k=kind: self._select_kind(k))
            side.addWidget(rr)
        self.test_btn = QPushButton("Test regions on this screenshot")
        side.addWidget(self.test_btn)
        side.addStretch(1)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setMinimumWidth(360)
        side_w.setMaximumWidth(420)
        split.addWidget(side_w, 2)
        cal.body.addLayout(split)
        self.cal_status = QLabel("")
        self.cal_status.setWordWrap(True)
        cal.body.addWidget(self.cal_status)
        self.content.addWidget(cal)

        # Name teaching -----------------------------------------------------------------
        teach = Card("Creature names")
        expl = QLabel(
            "Names are read by matching Tibia's pixel letters against letters you teach once. "
            "Draw the battle list region, then type the name shown in each row and press Teach. "
            "Every new letter only needs to be taught once.")
        expl.setWordWrap(True)
        expl.setObjectName("Dim")
        teach.body.addWidget(expl)
        hdr = QHBoxLayout()
        self.glyph_count = QLabel("")
        self.clear_glyphs_btn = QPushButton("Forget all letters")
        hdr.addWidget(self.glyph_count, 1)
        hdr.addWidget(self.clear_glyphs_btn)
        teach.body.addLayout(hdr)
        self.teach_rows = [TeachRow(self) for _ in range(MAX_TEACH_ROWS)]
        for t in self.teach_rows:
            t.setVisible(False)
            teach.body.addWidget(t)
        self.teach_empty = QLabel("No battle-list entries found on the current screenshot.")
        self.teach_empty.setObjectName("Muted")
        teach.body.addWidget(self.teach_empty)
        self.content.addWidget(teach)
        self.content.addStretch(1)

        # Wiring ------------------------------------------------------------------------
        self.shot_btn.clicked.connect(self.take_screenshot)
        self.load_btn.clicked.connect(self.load_image)
        self.demo_btn.clicked.connect(self.load_demo)
        self.fit_btn.clicked.connect(self.canvas.fit)
        self.zoom_btn.clicked.connect(lambda: self.canvas.zoom(1.5))
        self.test_btn.clicked.connect(self.test_regions)
        self.canvas.region_drawn.connect(self.save_region)
        self.clear_glyphs_btn.clicked.connect(self.clear_glyphs)
        self.toggle_btn.clicked.connect(self.toggle_recognition)
        if services is None:
            self.toggle_btn.setEnabled(False)
            self.shot_btn.setEnabled(False)
        ctx.bus.subscribe(Topic.RECOGNITION_STATUS, self._on_status)
        self.refresh()

    # ------------------------------------------------------------------ helpers
    @property
    def calibration(self):
        return self.services.recognition.calibration if self.services else None

    def _say(self, text: str, level: str = "ok") -> None:
        color = {"ok": C.GREEN, "warn": C.AMBER, "error": C.RED}.get(level, C.TEXT_DIM)
        self.cal_status.setStyleSheet(f"color: {color};")
        self.cal_status.setText(text)

    def _select_kind(self, kind: str) -> None:
        self.canvas.current_kind = kind
        self.canvas.setCursor(Qt.CrossCursor)
        self._say(f"Drag a rectangle around the {REGION_LABELS[kind].lower()} on the screenshot.", "info")

    def _calibrations(self) -> dict[str, dict]:
        from tdc.storage.repositories import CalibrationRepository

        return (self.calibration or CalibrationRepository(self.ctx.db)).all()

    def _glyphs(self):
        from tdc.storage.repositories import GlyphRepository

        return self.services.recognition.glyph_repo if self.services else GlyphRepository(self.ctx.db)

    def _changed(self, kind: str | None) -> None:
        self.ctx.bus.publish(Topic.REGIONS_CHANGED, kind)
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    # ------------------------------------------------------------------ screenshot sources
    def set_image(self, img: np.ndarray, description: str) -> None:
        self.image = img
        self.canvas.set_image(img)
        self.image_info.setText(f"{description} · {img.shape[1]}×{img.shape[0]} px")
        self.refresh()
        self.test_regions()

    def take_screenshot(self) -> None:
        try:
            img, _rect, desc = capture_reference(self.services.recognition)
        except CaptureUnavailable as exc:
            self._say(str(exc), "error")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Screenshot failed")
            self._say(f"Screenshot failed: {exc}", "error")
            return
        self.set_image(img, desc)
        self._say("Screenshot taken. Pick a region and drag a rectangle.", "ok")

    def load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Tibia screenshot", str(self.ctx.paths.screenshots),
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.load_image_file(path)

    def load_image_file(self, path: str) -> bool:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            self._say("That file could not be read as an image.", "error")
            return False
        self.set_image(img, path.replace("\\", "/").rsplit("/", 1)[-1])
        self._say("Image loaded. It should show only the inside of the Tibia window (no title bar).", "warn")
        return True

    def load_demo(self) -> None:
        img, _ = render(demo_scene())
        self.set_image(img, "Demo screenshot (synthetic, not real Tibia)")
        self._say("Demo loaded. Regions you draw are saved — clear them before using real Tibia.", "warn")

    # ------------------------------------------------------------------ regions
    def save_region(self, kind: str, r: Rect) -> None:
        if self.image is None:
            return
        h, w = self.image.shape[:2]
        self.ctx.regions.save(Region(kind, r.x, r.y, r.width, r.height, w, h))
        self.calibration_repo().delete(kind)   # an old bar calibration no longer fits
        log.info("Region %s set to %s on %dx%d", kind, r, w, h)
        msg = f"{REGION_LABELS[kind]} saved."
        if kind in ("health", "mana"):
            msg += " Now press “Learn bar” (with the bar full)."
        self._say(msg, "ok")
        self._changed(kind)
        self.test_regions()

    def calibration_repo(self):
        from tdc.storage.repositories import CalibrationRepository

        return self.calibration or CalibrationRepository(self.ctx.db)

    def clear_region(self, kind: str) -> None:
        self.ctx.regions.delete(kind)
        self.calibration_repo().delete(kind)
        self._say(f"{REGION_LABELS[kind]} cleared.", "ok")
        self._changed(kind)

    def learn_bar(self, kind: str) -> None:
        region = self.ctx.regions.get(kind)
        if self.image is None or region is None:
            self._say("Take a screenshot and draw the region first.", "error")
            return
        try:
            cal = calibrate_bar(crop(self.image, Rect(region.x, region.y, region.width, region.height)))
        except ValueError as exc:
            self._say(f"{REGION_LABELS[kind]}: {exc}", "error")
            return
        self.calibration_repo().save(kind, cal.to_dict())
        self._say(f"{REGION_LABELS[kind]} learned (bar is {cal.end - cal.start} px wide).", "ok")
        self._changed(kind)
        self.test_regions()

    def test_regions(self) -> dict[str, str]:
        """Run the analyzers on the current screenshot and show the results per region."""
        results: dict[str, str] = {}
        if self.image is None:
            return results
        regions = self.ctx.regions.all()
        cals = self._calibrations()
        lib = GlyphLibrary(self._glyphs().all())
        teach_entries = []
        for kind, row in self.rows.items():
            region = regions.get(kind)
            if region is None:
                row.result.setText("")
                row.preview.clear()
                continue
            r = Rect(region.x, region.y, region.width, region.height)
            img = crop(self.image, r)
            if img.size == 0:
                row.result.setText("Region is outside this screenshot")
                continue
            pm = bgr_to_pixmap(img, 2 if r.height <= 30 else 1)
            pm = pm.scaled(min(PREVIEW_MAX_W, pm.width()), min(PREVIEW_MAX_H, pm.height()),
                           Qt.KeepAspectRatio, Qt.FastTransformation)
            row.preview.setPixmap(pm)
            if kind in ("health", "mana"):
                m = analyze_bar(img, BarCalibration.from_dict(cals.get(kind)))
                text = (f"Reads {m.value:.0f}% · confidence {m.confidence:.0%}" if m.value is not None
                        else f"Not readable: {m.reason}")
            else:
                entries = find_entries(img)
                names = [lib.read(e.name_strip)[0] or "?" for e in entries] if len(lib) else []
                text = f"{len(entries)} {'entry' if len(entries) == 1 else 'entries'} found"
                if entries:
                    text += ": " + ", ".join(
                        f"{(names[i] if names else '?')} {e.health.value:.0f}%" for i, e in enumerate(entries[:5]))
                if kind == "battle_list" or (kind == "creatures" and "battle_list" not in regions):
                    teach_entries = entries
            row.result.setText(text)
            results[kind] = text
        self._fill_teach_rows(teach_entries, lib)
        return results

    def _fill_teach_rows(self, entries, lib: GlyphLibrary) -> None:
        for i, row in enumerate(self.teach_rows):
            if i < len(entries):
                e = entries[i]
                row.strip = e.name_strip
                if e.name_strip.size:
                    row.image.setPixmap(bgr_to_pixmap(e.name_strip, 2).scaledToWidth(196))
                text, conf = lib.read(e.name_strip) if len(lib) else ("", 0.0)
                row.read.setText(f"Reads: {text}" if text else "Reads: —")
                row.setVisible(True)
            else:
                row.setVisible(False)
        self.teach_empty.setVisible(not entries)

    def teach(self, row: TeachRow) -> bool:
        text = row.edit.text().strip()
        if row.strip is None or not text:
            self._say("Type the name shown in that row first.", "error")
            return False
        lib = GlyphLibrary(self._glyphs().all())
        try:
            new = lib.learn(row.strip, text)
        except ValueError as exc:
            self._say(f"Could not learn “{text}”: {exc}", "error")
            return False
        self._glyphs().save_many(new)
        if text.lower() not in {n.lower() for n in self.ctx.creatures.all()}:
            pass  # names are matched against the built-in list and creature priorities
        row.edit.clear()
        self._say(f"Learned {len(new)} new letter shapes from “{text}”.", "ok")
        self._changed(None)
        self.test_regions()
        return True

    def clear_glyphs(self) -> None:
        if QMessageBox.question(self, "Forget letters", "Forget all taught letters?") == QMessageBox.Yes:
            self._glyphs().clear()
            self._changed(None)
            self.test_regions()

    # ------------------------------------------------------------------ live recognition
    def toggle_recognition(self) -> None:
        if self.services.recognition.running:
            self.services.stop_recognition()
        else:
            self.services.start_recognition()
        self._update_toggle()     # status events from the worker update the rest

    def _on_status(self, st: RecognitionStatus) -> None:
        self.state = st.state
        self.state_label.setText({
            RecognitionState.RUNNING: "Live",
            RecognitionState.SIMULATED: "Simulation running",
            RecognitionState.WINDOW_NOT_FOUND: "Tibia not found",
            RecognitionState.MINIMIZED: "Tibia minimized",
            RecognitionState.NOT_CALIBRATED: "Not calibrated",
            RecognitionState.ERROR: "Error",
        }.get(st.state, "Not running"))
        color = {RecognitionState.RUNNING: C.GREEN, RecognitionState.SIMULATED: C.AMBER,
                 RecognitionState.ERROR: C.RED, RecognitionState.WINDOW_NOT_FOUND: C.RED,
                 RecognitionState.MINIMIZED: C.AMBER, RecognitionState.NOT_CALIBRATED: C.AMBER}.get(st.state, C.TEXT_MUTED)
        self.state_dot.setStyleSheet(f"color: {color}; font-size: 12pt;")
        detail = st.message or ""
        if st.state == RecognitionState.RUNNING and st.fps:
            detail += f" · {st.fps:.1f} readings/s"
        self.state_detail.setText(detail)
        self._update_toggle()

    def _update_toggle(self) -> None:
        running = bool(self.services and self.services.recognition.running)
        self.toggle_btn.setText("Stop recognition" if running else "Start recognition")

    def refresh(self) -> None:
        regions = self.ctx.regions.all()
        cals = self._calibrations()
        for kind, row in self.rows.items():
            r = regions.get(kind)
            if r is None:
                row.status.setText("not set")
            else:
                txt = f"{r.width}×{r.height} at {r.x},{r.y}"
                if kind in ("health", "mana"):
                    txt += " · bar learned ✓" if kind in cals else " · bar not learned"
                row.status.setText(txt)
            if row.learn_btn:
                row.learn_btn.setEnabled(r is not None and self.image is not None)
        self.canvas.set_regions({k: Rect(r.x, r.y, r.width, r.height) for k, r in regions.items()})
        n = self._glyphs().count()
        self.glyph_count.setText(f"{n} letter shapes learned")
        rs = self.ctx.config.get(RecognitionSettings)
        if not self.services or not self.services.recognition.running:
            if self.state in (RecognitionState.STOPPED, RecognitionState.SIMULATED):
                mode = ("follows the window titled “%s”" % rs.window_title) if rs.capture_mode == "window" \
                    else f"fixed positions on monitor {rs.screen_index}"
                self.state_detail.setText(f"Capture mode: {mode}. Interval {rs.interval_ms} ms.")
        self._update_toggle()
