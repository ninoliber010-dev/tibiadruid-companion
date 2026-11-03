"""Screenshot canvas on which the user draws recognition regions."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

from tdc.recognition.geometry import Rect
from tdc.ui.theme import C

REGION_LABELS = {
    "health": "Health bar",
    "mana": "Mana bar",
    "battle_list": "Battle list",
    "party": "Party list",
    "creatures": "Game view (creatures)",
}
REGION_COLORS = {
    "health": C.RED, "mana": C.BLUE, "battle_list": C.AMBER, "party": C.GREEN, "creatures": "#b07cf0",
}


def bgr_to_qimage(img: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(img[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def bgr_to_pixmap(img: np.ndarray, scale: int = 1) -> QPixmap:
    pm = QPixmap.fromImage(bgr_to_qimage(img))
    if scale != 1:
        pm = pm.scaled(pm.width() * scale, pm.height() * scale, Qt.KeepAspectRatio, Qt.FastTransformation)
    return pm


class RegionCanvas(QGraphicsView):
    region_drawn = Signal(str, object)    # kind, Rect (image coordinates)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(C.BG)))
        self.setMinimumHeight(360)
        self.setMaximumHeight(560)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._pixmap: QGraphicsPixmapItem | None = None
        self._items: dict[str, tuple[QGraphicsRectItem, QGraphicsSimpleTextItem]] = {}
        self._drag_start: QPointF | None = None
        self._rubber: QGraphicsRectItem | None = None
        self.current_kind: str | None = None
        self.image_size: tuple[int, int] | None = None
        self.placeholder = self.scene().addSimpleText("Take or load a screenshot to start calibrating.")
        self.placeholder.setBrush(QColor(C.TEXT_DIM))

    # ------------------------------------------------------------------ content
    def set_image(self, img: np.ndarray) -> None:
        self.scene().clear()
        self._items.clear()
        self.placeholder = None
        self._pixmap = self.scene().addPixmap(bgr_to_pixmap(img))
        self.image_size = (img.shape[1], img.shape[0])
        self.scene().setSceneRect(QRectF(0, 0, img.shape[1], img.shape[0]))
        self.fit()

    def set_regions(self, regions: dict[str, Rect]) -> None:
        for rect_item, label in self._items.values():
            self.scene().removeItem(rect_item)
            self.scene().removeItem(label)
        self._items.clear()
        if self._pixmap is None:
            return
        for kind, r in regions.items():
            col = QColor(REGION_COLORS.get(kind, C.TEXT))
            fill = QColor(col)
            fill.setAlpha(40)
            item = self.scene().addRect(QRectF(r.x, r.y, r.width, r.height), QPen(col, 0), QBrush(fill))
            label = self.scene().addSimpleText(REGION_LABELS.get(kind, kind))
            f = QFont()
            f.setPointSizeF(8)
            f.setBold(True)
            label.setFont(f)
            label.setBrush(col)
            label.setPos(r.x, max(0, r.y - 14))
            item.setZValue(2)
            label.setZValue(3)
            self._items[kind] = (item, label)

    def fit(self) -> None:
        if self._pixmap is not None:
            self.fitInView(self._pixmap, Qt.KeepAspectRatio)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self.fit()

    def zoom(self, factor: float) -> None:
        self.scale(factor, factor)

    # ------------------------------------------------------------------ drawing
    def wheelEvent(self, e) -> None:  # noqa: N802
        if e.modifiers() & Qt.ControlModifier:
            self.zoom(1.25 if e.angleDelta().y() > 0 else 0.8)
        else:
            super().wheelEvent(e)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton and self.current_kind and self._pixmap is not None:
            self._drag_start = self.mapToScene(e.position().toPoint())
            col = QColor(REGION_COLORS.get(self.current_kind, C.TEXT))
            self._rubber = self.scene().addRect(QRectF(self._drag_start, self._drag_start), QPen(col, 0, Qt.DashLine))
            self._rubber.setZValue(5)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag_start is not None and self._rubber is not None:
            self._rubber.setRect(QRectF(self._drag_start, self.mapToScene(e.position().toPoint())).normalized())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag_start is not None and self._rubber is not None:
            rect = self._rubber.rect()
            self.scene().removeItem(self._rubber)
            self._rubber, self._drag_start = None, None
            r = self.clamp(rect)
            if r is not None and self.current_kind:
                self.region_drawn.emit(self.current_kind, r)
            return
        super().mouseReleaseEvent(e)

    def clamp(self, rect: QRectF) -> Rect | None:
        if self.image_size is None:
            return None
        w, h = self.image_size
        x0, y0 = max(0, int(rect.left())), max(0, int(rect.top()))
        x1, y1 = min(w, int(round(rect.right()))), min(h, int(round(rect.bottom())))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        return Rect(x0, y0, x1 - x0, y1 - y0)
