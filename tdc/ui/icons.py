"""Application icon drawn in code (no binary assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _leaf_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    p.setBrush(QBrush(QColor("#1b1e22")))
    p.setPen(QPen(QColor("#3fbf7f"), max(1.0, s / 24)))
    p.drawRoundedRect(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92), s * 0.22, s * 0.22)
    leaf = QPainterPath(QPointF(s * 0.28, s * 0.74))
    leaf.cubicTo(QPointF(s * 0.22, s * 0.38), QPointF(s * 0.5, s * 0.2), QPointF(s * 0.76, s * 0.24))
    leaf.cubicTo(QPointF(s * 0.78, s * 0.52), QPointF(s * 0.6, s * 0.78), QPointF(s * 0.28, s * 0.74))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#3fbf7f")))
    p.drawPath(leaf)
    p.setPen(QPen(QColor("#1b1e22"), max(1.0, s / 28)))
    p.drawLine(QPointF(s * 0.3, s * 0.72), QPointF(s * 0.68, s * 0.32))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_leaf_pixmap(size))
    return icon
