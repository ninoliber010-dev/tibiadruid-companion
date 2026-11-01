"""Dark theme: colour tokens and the application style sheet."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


class C:
    BG = "#15171a"          # window background (charcoal)
    BG_ALT = "#1b1e22"      # sidebar / cards
    SURFACE = "#22262b"     # inputs, raised surfaces
    SURFACE_HI = "#2a2f35"  # hover
    BORDER = "#2f343b"
    BORDER_HI = "#3c434b"
    TEXT = "#e6e8eb"
    TEXT_DIM = "#9aa3ad"
    TEXT_MUTED = "#6b737c"
    GREEN = "#3fbf7f"
    BLUE = "#4c9be8"
    AMBER = "#e0a83a"
    RED = "#e5534b"
    ACCENT = "#3fbf7f"      # druid green

    @staticmethod
    def for_priority(priority: int) -> str:
        return {0: C.BLUE, 1: C.AMBER, 2: C.RED}.get(priority, C.TEXT_DIM)


FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif'

STYLE_SHEET = f"""
* {{ font-family: {FONT_STACK}; font-size: 10pt; color: {C.TEXT}; }}
QMainWindow, QWidget#Page, QStackedWidget {{ background: {C.BG}; }}
QWidget#Sidebar {{ background: {C.BG_ALT}; border-right: 1px solid {C.BORDER}; }}
QLabel#AppTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#AppSubtitle {{ color: {C.TEXT_MUTED}; font-size: 8.5pt; }}
QPushButton#NavButton {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 6px;
    background: transparent; color: {C.TEXT_DIM}; font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {C.SURFACE}; color: {C.TEXT}; }}
QPushButton#NavButton:checked {{ background: {C.SURFACE_HI}; color: {C.TEXT}; border-left: 3px solid {C.ACCENT}; }}

QLabel#PageTitle {{ font-size: 17pt; font-weight: 600; }}
QLabel#PageSubtitle {{ color: {C.TEXT_DIM}; }}
QLabel#Muted {{ color: {C.TEXT_MUTED}; }}
QLabel#Dim {{ color: {C.TEXT_DIM}; }}
QLabel#CardTitle {{ color: {C.TEXT_DIM}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#CardValue {{ font-size: 15pt; font-weight: 600; }}
QLabel#Error {{ color: {C.RED}; }}
QFrame#Card {{ background: {C.BG_ALT}; border: 1px solid {C.BORDER}; border-radius: 10px; }}

QPushButton {{
    background: {C.SURFACE}; border: 1px solid {C.BORDER_HI}; border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ background: {C.SURFACE_HI}; }}
QPushButton:pressed {{ background: {C.BORDER}; }}
QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BORDER}; }}
QPushButton#Primary {{ background: #2c7a55; border-color: #35946a; }}
QPushButton#Primary:hover {{ background: #33895f; }}
QPushButton#Danger {{ background: #6e2b28; border-color: #8a3631; }}
QPushButton#Segment {{ border-radius: 0; padding: 6px 18px; }}
QPushButton#Segment:checked {{ background: #2c7a55; border-color: #35946a; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QListWidget, QTableWidget, QTreeWidget {{
    background: {C.SURFACE}; border: 1px solid {C.BORDER_HI}; border-radius: 6px; padding: 4px 6px;
    selection-background-color: #2c7a55;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {C.ACCENT}; }}
QComboBox QAbstractItemView {{ background: {C.SURFACE}; border: 1px solid {C.BORDER_HI}; }}
QPlainTextEdit#LogView {{ font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 9pt; }}
QHeaderView::section {{ background: {C.BG_ALT}; color: {C.TEXT_DIM}; border: none; border-bottom: 1px solid {C.BORDER}; padding: 5px; }}
QTableWidget {{ gridline-color: {C.BORDER}; }}

QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {C.BORDER_HI}; background: {C.SURFACE}; }}
QCheckBox::indicator:checked {{ background: {C.ACCENT}; border-color: {C.ACCENT}; }}

QTabWidget::pane {{ border: 1px solid {C.BORDER}; border-radius: 8px; top: -1px; background: {C.BG_ALT}; }}
QTabBar::tab {{ background: transparent; color: {C.TEXT_DIM}; padding: 8px 16px; border: none; }}
QTabBar::tab:selected {{ color: {C.TEXT}; border-bottom: 2px solid {C.ACCENT}; }}
QTabBar::tab:hover {{ color: {C.TEXT}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {C.BORDER_HI}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {C.BORDER_HI}; border-radius: 5px; min-width: 30px; }}

QStatusBar {{ background: {C.BG_ALT}; border-top: 1px solid {C.BORDER}; color: {C.TEXT_DIM}; }}
QStatusBar QLabel {{ padding: 0 10px; color: {C.TEXT_DIM}; }}
QToolTip {{ background: {C.SURFACE_HI}; color: {C.TEXT}; border: 1px solid {C.BORDER_HI}; padding: 4px; }}
QMenu {{ background: {C.BG_ALT}; border: 1px solid {C.BORDER_HI}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C.SURFACE_HI}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C.BG))
    pal.setColor(QPalette.WindowText, QColor(C.TEXT))
    pal.setColor(QPalette.Base, QColor(C.SURFACE))
    pal.setColor(QPalette.AlternateBase, QColor(C.BG_ALT))
    pal.setColor(QPalette.Text, QColor(C.TEXT))
    pal.setColor(QPalette.Button, QColor(C.SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(C.TEXT))
    pal.setColor(QPalette.Highlight, QColor("#2c7a55"))
    pal.setColor(QPalette.HighlightedText, QColor(C.TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(C.SURFACE_HI))
    pal.setColor(QPalette.ToolTipText, QColor(C.TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(C.TEXT_MUTED))
    app.setPalette(pal)
    app.setStyleSheet(STYLE_SHEET)
