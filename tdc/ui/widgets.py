"""Small reusable widgets shared by pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from tdc.ui.theme import C


class Card(QFrame):
    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)
        if title:
            t = QLabel(title.upper())
            t.setObjectName("CardTitle")
            self.body.addWidget(t)


class StatCard(Card):
    """Card with a big value, a status dot and a caption."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.dot = QLabel("●")
        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        row.addWidget(self.dot)
        row.addWidget(self.value, 1)
        self.body.addLayout(row)
        self.caption = QLabel("")
        self.caption.setObjectName("Dim")
        self.caption.setWordWrap(True)
        self.body.addWidget(self.caption)
        self.body.addStretch(1)
        self.set("—", "", C.TEXT_MUTED)

    def set(self, value: str, caption: str = "", color: str = C.TEXT_MUTED) -> None:
        self.value.setText(value)
        self.caption.setText(caption)
        self.dot.setStyleSheet(f"color: {color}; font-size: 12pt;")


class Page(QWidget):
    """Base page: title, subtitle and a scrollable content column."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        outer.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            s.setWordWrap(True)
            outer.addWidget(s)
        outer.addSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("Page")
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(0, 0, 4, 0)
        self.content.setSpacing(14)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def on_shown(self) -> None:
        """Called when the page becomes visible (refresh hook)."""


class PlaceholderPage(Page):
    """Shown for modules scheduled for a later phase. States plainly that nothing works yet."""

    def __init__(self, title: str, subtitle: str, phase: int, planned: list[str]) -> None:
        super().__init__(title, subtitle)
        card = Card(f"Planned for Phase {phase}")
        note = QLabel(
            "This module is not implemented yet. Nothing on this page is active — "
            "the features below are scheduled in the development roadmap."
        )
        note.setWordWrap(True)
        note.setObjectName("Dim")
        card.body.addWidget(note)
        for item in planned:
            lbl = QLabel(f"•  {item}")
            lbl.setWordWrap(True)
            card.body.addWidget(lbl)
        self.content.addWidget(card)
        self.content.addStretch(1)
        self.phase = phase


def h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {C.BORDER};")
    line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return line
