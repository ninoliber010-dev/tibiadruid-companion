"""Painted building blocks of the HUD."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from tdc.ui.theme import C

LEVEL_COLORS = {
    "ok": C.GREEN, "low": C.BLUE, "warn": C.AMBER, "critical": C.RED, "unknown": C.TEXT_MUTED,
}


def level_color(level: str, ok_color: str = C.GREEN) -> QColor:
    return QColor(ok_color if level == "ok" else LEVEL_COLORS.get(level, C.TEXT_MUTED))


class ResourceBar(QWidget):
    """Label + value on one line, a slim bar below; grey with an explanation when unavailable."""

    def __init__(self, label: str, ok_color: str = C.GREEN, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.ok_color = ok_color
        self.value: float | None = None
        self.text = "—"
        self.level = "unknown"
        self.note = ""
        self.confidence: float | None = None
        self.scale = 1.0
        self.compact = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, label: str, value: float | None, text: str, level: str, note: str,
                  confidence: float | None) -> None:
        changed = (label, value, text, level, note, confidence) != (
            self.label, self.value, self.text, self.level, self.note, self.confidence)
        self.label, self.value, self.text, self.level, self.note, self.confidence = (
            label, value, text, level, note, confidence)
        if changed:
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, int((30 if self.compact else 36) * self.scale))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self.scale
        f = QFont(self.font())
        f.setPointSizeF(8.5 * s)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        top = int(15 * s)
        p.setPen(QColor(C.TEXT_DIM))
        p.drawText(QRectF(0, 0, w * 0.6, top), Qt.AlignLeft | Qt.AlignVCenter, self.label.upper())

        if self.value is None:
            f.setWeight(QFont.Normal)
            f.setItalic(True)
            p.setFont(f)
            p.setPen(QColor(C.TEXT_MUTED))
            p.drawText(QRectF(w * 0.3, 0, w * 0.7, top), Qt.AlignRight | Qt.AlignVCenter, self.note or "unavailable")
        else:
            f.setPointSizeF(10.5 * s)
            f.setWeight(QFont.Bold)
            p.setFont(f)
            p.setPen(level_color(self.level, self.ok_color) if self.level != "ok" else QColor(C.TEXT))
            p.drawText(QRectF(w * 0.4, 0, w * 0.6, top), Qt.AlignRight | Qt.AlignVCenter, self.text)

        bar_h = max(5.0, 7 * s)
        y = top + 5 * s
        track = QRectF(0, y, w, bar_h)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#2b3036")))
        p.drawRoundedRect(track, bar_h / 2, bar_h / 2)
        if self.value is not None:
            frac = max(0.0, min(1.0, self.value / 100.0))
            if frac > 0:
                fill = QRectF(0, y, max(bar_h, w * frac), bar_h)
                p.setBrush(QBrush(level_color(self.level, self.ok_color)))
                p.drawRoundedRect(fill, bar_h / 2, bar_h / 2)
        else:
            # Dashed track = "no data", clearly different from an empty (0 %) bar.
            pen = QPen(QColor(C.TEXT_MUTED), 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), bar_h / 2, bar_h / 2)
        p.end()


class CreatureRowWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = ""
        self.health: float | None = None
        self.health_text = "—"
        self.trend = ""
        self.targeted = False
        self.priority = 0
        self.scale = 1.0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_row(self, name: str, health: float | None, health_text: str, trend: str,
                targeted: bool = False, priority: int = 0) -> None:
        new = (name, health, health_text, trend, targeted, priority)
        if new != (self.name, self.health, self.health_text, self.trend, self.targeted, self.priority):
            self.name, self.health, self.health_text, self.trend, self.targeted, self.priority = new
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, int(20 * self.scale))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self.scale
        f = QFont(self.font())
        f.setPointSizeF(9 * s)
        p.setFont(f)
        name_w = w * 0.52
        indent = 0.0
        if self.targeted:
            # Small red marker: the creature you are attacking (from the battle list's red frame).
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C.RED))
            p.drawRoundedRect(QRectF(0, h * 0.25, 3, h * 0.5), 1.5, 1.5)
            indent = 7.0
        label = f"★ {self.name}" if self.priority > 0 else self.name
        color = C.AMBER if self.priority > 0 else (C.TEXT if self.name != "Unrecognized" else C.TEXT_MUTED)
        p.setPen(QColor(color))
        p.drawText(QRectF(indent, 0, name_w - indent, h), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(label, Qt.ElideRight, int(name_w - indent - 4)))
        bar_x, bar_w, bar_h = name_w, w * 0.30, 5 * s
        y = (h - bar_h) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2b3036"))
        p.drawRoundedRect(QRectF(bar_x, y, bar_w, bar_h), bar_h / 2, bar_h / 2)
        if self.health is not None:
            hp = self.health
            col = C.GREEN if hp > 60 else C.AMBER if hp > 25 else C.RED
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(bar_x, y, max(bar_h, bar_w * hp / 100), bar_h), bar_h / 2, bar_h / 2)
        p.setPen(QColor(C.TEXT_DIM))
        p.drawText(QRectF(bar_x + bar_w, 0, w - bar_x - bar_w, h), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.trend} {self.health_text}".strip())
        p.end()


class RecommendationWidget(QWidget):
    """One recommendation: coloured stripe, bold action, dim reason."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.priority = 0
        self.text = ""
        self.reason = ""
        self.scale = 1.0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_rec(self, priority: int, text: str, reason: str) -> None:
        if (priority, text, reason) != (self.priority, self.text, self.reason):
            self.priority, self.text, self.reason = priority, text, reason
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, int(38 * self.scale))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self.scale
        color = QColor(C.for_priority(self.priority))
        bg = QColor(color)
        bg.setAlpha(34)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 1, w, h - 2), 6, 6)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(0, 1, 3.5, h - 2), 2, 2)
        f = QFont(self.font())
        f.setPointSizeF(9.5 * s)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(C.TEXT))
        fm = p.fontMetrics()
        p.drawText(QRectF(11, 3, w - 16, h / 2), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.text, Qt.ElideRight, int(w - 18)))
        f.setPointSizeF(8 * s)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(QColor(C.TEXT_DIM))
        p.drawText(QRectF(11, h / 2, w - 16, h / 2 - 3), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.reason, Qt.ElideRight, int(w - 18)))
        p.end()
