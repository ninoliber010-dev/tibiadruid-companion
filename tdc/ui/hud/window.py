"""The floating HUD window.

A separate, frameless, always-on-top desktop window. It never touches the Tibia process; it is
an ordinary window that happens to sit above other windows.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QSizeGrip, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from tdc.config.settings import HudSettings
from tdc.core.models import HuntMode, Notification, Priority
from tdc.ui.hud.viewmodel import HudState
from tdc.ui.hud.widgets import LEVEL_COLORS, CreatureRowWidget, RecommendationWidget, ResourceBar
from tdc.ui.icons import app_icon
from tdc.ui.theme import C

MAX_CREATURES = 8
MAX_RECS = 4

HUD_QSS = f"""
QWidget#HudRoot {{ background: transparent; }}
QLabel {{ color: {C.TEXT}; background: transparent; }}
QLabel#HudTitle {{ font-weight: 700; letter-spacing: 1px; color: {C.TEXT}; }}
QLabel#HudSection {{ color: {C.TEXT_MUTED}; font-weight: 700; letter-spacing: 1px; }}
QLabel#HudDim {{ color: {C.TEXT_DIM}; }}
QLabel#HudMuted {{ color: {C.TEXT_MUTED}; font-style: italic; }}
QLabel#HudBadge {{ border-radius: 4px; padding: 1px 6px; font-weight: 700; }}
QToolButton {{ background: transparent; border: none; color: {C.TEXT_DIM}; border-radius: 4px; padding: 0 4px; }}
QToolButton:hover {{ background: {C.SURFACE_HI}; color: {C.TEXT}; }}
QSizeGrip {{ background: transparent; width: 12px; height: 12px; }}
"""


class ElidedLabel(QLabel):
    """Label that shortens its text with "…" instead of clipping it."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width())
        p.drawText(self.rect(), int(Qt.AlignLeft | Qt.AlignVCenter), text)
        p.end()


class Section(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.title = QLabel(title.upper())
        self.title.setObjectName("HudSection")
        self.aside = QLabel("")
        self.aside.setObjectName("HudDim")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.aside)
        self.v.addLayout(head)


class HudWindow(QWidget):
    geometry_changed = Signal(int, int, int, int)   # x, y, width, height (debounced)
    compact_toggled = Signal(bool)
    menu_requested = Signal(QPoint)
    hide_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HudRoot")
        self.setWindowTitle("Druid Companion HUD")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet(HUD_QSS)
        self.settings = HudSettings()
        self._flags_key: tuple | None = None
        self._applying = False
        self._drag_offset: QPoint | None = None
        self._border_color = QColor(C.BORDER_HI)
        self._flash_left = 0
        self._expanded_height = self.settings.height

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # Header ------------------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(4)
        self.title = QLabel()
        self.title.setPixmap(app_icon().pixmap(18, 18))
        self.title.setToolTip("Druid Companion")
        self.mode_badge = QLabel("SOLO")
        self.mode_badge.setObjectName("HudBadge")
        self.mode_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.source_dot = QLabel("●")
        self.source_label = ElidedLabel("Not running")
        self.source_label.setObjectName("HudDim")
        self.source_label.setMinimumWidth(10)
        self.source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.compact_btn = QToolButton()
        self.compact_btn.setToolTip("Compact / expanded")
        self.menu_btn = QToolButton()
        self.menu_btn.setText("⋯")
        self.menu_btn.setToolTip("HUD options")
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("Hide HUD (show again from the tray or main window)")
        header.addWidget(self.title)
        header.addWidget(self.mode_badge)
        header.addSpacing(4)
        header.addWidget(self.source_dot)
        header.addWidget(self.source_label, 1)
        header.addWidget(self.compact_btn)
        header.addWidget(self.menu_btn)
        header.addWidget(self.close_btn)
        root.addLayout(header)

        self.click_badge = QLabel("CLICK-THROUGH ON · turn off from the tray icon")
        self.click_badge.setObjectName("HudBadge")
        self.click_badge.setStyleSheet(f"background: {C.AMBER}; color: #1b1e22;")
        self.click_badge.setVisible(False)
        root.addWidget(self.click_badge)

        self.toast = QLabel("")
        self.toast.setWordWrap(True)
        self.toast.setVisible(False)
        root.addWidget(self.toast)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self.toast.setVisible(False) or self._fit_compact())

        # Player ------------------------------------------------------------------
        self.player = Section("Player")
        self.health_bar = ResourceBar("Health", C.GREEN)
        self.mana_bar = ResourceBar("Mana", C.BLUE)
        self.player.v.addWidget(self.health_bar)
        self.player.v.addWidget(self.mana_bar)
        root.addWidget(self.player)

        # Party -------------------------------------------------------------------
        self.party = Section("Party")
        self.partner_bar = ResourceBar("Partner", C.GREEN)
        self.party.v.addWidget(self.partner_bar)
        root.addWidget(self.party)

        # Recommendations ---------------------------------------------------------
        self.recs = Section("Recommendations")
        self.rec_widgets = [RecommendationWidget() for _ in range(MAX_RECS)]
        for w in self.rec_widgets:
            self.recs.v.addWidget(w)
            w.setVisible(False)
        self.rec_empty = QLabel("No action needed")
        self.rec_empty.setObjectName("HudMuted")
        self.recs.v.addWidget(self.rec_empty)
        root.addWidget(self.recs)

        # Combat ------------------------------------------------------------------
        self.combat = Section("Creatures")
        self.creature_rows = [CreatureRowWidget() for _ in range(MAX_CREATURES)]
        for w in self.creature_rows:
            self.combat.v.addWidget(w)
            w.setVisible(False)
        self.creature_note = QLabel("")
        self.creature_note.setObjectName("HudMuted")
        self.combat.v.addWidget(self.creature_note)
        root.addWidget(self.combat)

        # Session -----------------------------------------------------------------
        self.session = Section("Session")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        self.session_values: dict[str, QLabel] = {}
        for i, key in enumerate(("Monitoring", "XP/hour", "Profile", "Route")):
            k = QLabel(key)
            k.setObjectName("HudDim")
            v = QLabel("—")
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(k, i // 2, (i % 2) * 2)
            grid.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self.session_values[key] = v
        self.session.v.addLayout(grid)
        root.addWidget(self.session)

        root.addStretch(1)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self.grip = QSizeGrip(self)
        grip_row.addWidget(self.grip, 0, Qt.AlignRight | Qt.AlignBottom)
        root.addLayout(grip_row)

        self.compact_btn.clicked.connect(lambda: self.compact_toggled.emit(self.settings.mode != "compact"))
        self.menu_btn.clicked.connect(
            lambda: self.menu_requested.emit(self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))))
        self.close_btn.clicked.connect(self.hide_requested)

        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.setInterval(500)
        self._geom_timer.timeout.connect(self._emit_geometry)
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(180)
        self._flash_timer.timeout.connect(self._flash_step)
        self.last_state: HudState | None = None

    # ------------------------------------------------------------------ settings
    def apply_settings(self, s: HudSettings) -> None:
        self._applying = True
        try:
            self.settings = s
            flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
            if s.always_on_top:
                flags |= Qt.WindowStaysOnTopHint
            if s.click_through:
                flags |= Qt.WindowTransparentForInput
            key = (s.always_on_top, s.click_through)
            if key != self._flags_key:
                was_visible = self.isVisible()
                self.setWindowFlags(flags)
                self._flags_key = key
                if was_visible:
                    self.show()
            self.setWindowOpacity(s.opacity)
            self.click_badge.setVisible(s.click_through)
            self.grip.setVisible(not s.click_through)
            self._apply_scale(s.font_scale)
            compact = s.mode == "compact"
            self.compact_btn.setText("▾" if compact else "▴")
            self.player.setVisible(s.show_player)
            self.recs.setVisible(s.show_recommendations)
            self.combat.setVisible(s.show_combat and not compact)
            self.session.setVisible(s.show_session and not compact)
            self._update_party_visibility()
            self._expanded_height = s.height
            target = QRect(s.x, s.y, s.width, s.height)
            target = self.ensure_on_screen(target)
            self.setMinimumWidth(220)
            self.move(target.topLeft())
            if compact:
                self._fit_compact(target.width())
            else:
                self.setMinimumHeight(0)
                self.setMaximumHeight(16777215)
                self.resize(target.width(), max(target.height(), self.minimumSizeHint().height()))
        finally:
            self._applying = False

    def _apply_scale(self, scale: float) -> None:
        f = QFont(self.font())
        f.setPointSizeF(9.0 * scale)
        for lbl in self.findChildren(QLabel):
            lf = QFont(lbl.font())
            lf.setPointSizeF((8.0 if lbl.objectName() in ("HudSection", "HudBadge") else 9.0) * scale)
            lbl.setFont(lf)
        for w in [self.health_bar, self.mana_bar, self.partner_bar, *self.creature_rows, *self.rec_widgets]:
            w.scale = scale
            w.compact = self.settings.mode == "compact"
            w.updateGeometry()

    def _fit_compact(self, width: int | None = None) -> None:
        if self.settings.mode != "compact":
            return
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        lay = self.layout()
        lay.activate()
        w = width or self.width()
        h = lay.totalHeightForWidth(w) if lay.hasHeightForWidth() else lay.sizeHint().height()
        self.resize(w, max(h, lay.totalMinimumSize().height()))

    @staticmethod
    def ensure_on_screen(rect: QRect) -> QRect:
        """Keep a saved position usable when monitors were rearranged or removed."""
        screens = QGuiApplication.screens()
        if not screens:
            return rect
        for sc in screens:
            visible = sc.availableGeometry().intersected(rect)
            if visible.width() >= 80 and visible.height() >= 40:
                return rect
        avail = QGuiApplication.primaryScreen().availableGeometry()
        w, h = min(rect.width(), avail.width()), min(rect.height(), avail.height())
        return QRect(avail.x() + 40, avail.y() + 40, w, h)

    # ------------------------------------------------------------------ rendering
    def _update_party_visibility(self) -> None:
        duo = self.last_state is not None and self.last_state.mode == HuntMode.DUO
        self.party.setVisible(self.settings.show_party and duo)

    def update_state(self, st: HudState) -> None:
        prev_mode = self.last_state.mode if self.last_state else None
        self.last_state = st
        compact = self.settings.mode == "compact"
        self.mode_badge.setText(st.mode.value.upper())
        badge_col = C.BLUE if st.mode == HuntMode.DUO else C.ACCENT
        self.mode_badge.setStyleSheet(f"background: {badge_col}; color: #111;")
        self.source_label.setText(st.source)
        self.source_label.setToolTip(st.source)
        self.source_dot.setStyleSheet(f"color: {LEVEL_COLORS.get(st.source_level, C.TEXT_MUTED)};")

        for bar, b in ((self.health_bar, st.health), (self.mana_bar, st.mana)):
            bar.set_state(b.label, b.value, b.text, b.level, b.note, b.confidence)
        if st.partner is not None:
            p = st.partner
            self.partner_bar.set_state(p.label, p.value, p.text, p.level, p.note, p.confidence)
        if st.mode != prev_mode:
            self._update_party_visibility()

        max_recs = 1 if compact else MAX_RECS
        for i, w in enumerate(self.rec_widgets):
            if i < min(len(st.recommendations), max_recs):
                r = st.recommendations[i]
                w.set_rec(int(r.priority), r.text, r.reason)
                w.setVisible(True)
            else:
                w.setVisible(False)
        self.rec_empty.setVisible(not st.recommendations)
        self.rec_empty.setText(st.advice_note)

        self.combat.aside.setText(st.creature_summary)
        for i, w in enumerate(self.creature_rows):
            if i < len(st.creatures):
                c = st.creatures[i]
                w.set_row(c.name, c.health, c.health_text, c.trend)
                w.setVisible(True)
            else:
                w.setVisible(False)
        extra = len(st.creatures) - MAX_CREATURES
        note = st.creature_note or (f"+{extra} more" if extra > 0 else ("None visible" if not st.creatures else ""))
        self.creature_note.setText(note)
        self.creature_note.setVisible(bool(note))

        self.session_values["Monitoring"].setText(st.monitoring_time)
        self.session_values["XP/hour"].setText(st.xp_per_hour)
        self.session_values["XP/hour"].setToolTip(st.xp_note)
        self.session_values["Profile"].setText(st.profile_name)
        self.session_values["Route"].setText(st.route)
        if compact:
            self._fit_compact()

    # ------------------------------------------------------------------ notifications
    def clear_notification(self) -> None:
        self._toast_timer.stop()
        self.toast.setVisible(False)
        self._fit_compact()

    def show_notification(self, n: Notification) -> None:
        col = C.for_priority(int(n.priority))
        self.toast.setText(f"<b>{n.title}:</b> {n.message}")
        self.toast.setStyleSheet(
            f"background: {col}; color: #111; border-radius: 6px; padding: 5px 8px; font-weight: 500;")
        self.toast.setVisible(True)
        self._toast_timer.start(n.duration_ms)
        if n.priority == Priority.CRITICAL:
            self._flash_left = 8
            self._flash_timer.start()
        self._fit_compact()

    def _flash_step(self) -> None:
        self._flash_left -= 1
        self._border_color = QColor(C.RED if self._flash_left % 2 else C.BORDER_HI)
        if self._flash_left <= 0:
            self._flash_timer.stop()
            self._border_color = QColor(C.BORDER_HI)
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QColor(C.BG)
        bg.setAlpha(242)
        p.setBrush(bg)
        p.setPen(QPen(self._border_color, 1.5 if self._flash_left else 1))
        p.drawRoundedRect(rect, 12, 12)
        p.end()

    # ------------------------------------------------------------------ moving / resizing
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self.menu_requested.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        self._drag_offset = None

    def moveEvent(self, e) -> None:  # noqa: N802
        super().moveEvent(e)
        if not self._applying:
            self._geom_timer.start()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if not self._applying:
            self._geom_timer.start()

    def _emit_geometry(self) -> None:
        g = self.geometry()
        # In compact mode the height is automatic; keep the stored expanded height.
        h = self._expanded_height if self.settings.mode == "compact" else g.height()
        self.geometry_changed.emit(g.x(), g.y(), g.width(), h)
