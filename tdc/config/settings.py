"""Typed configuration sections.

Each section is a dataclass. Field ``metadata`` carries the label, help text and limits;
validation and the auto-generated settings forms both read it, so limits live in one place.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from typing import Any, ClassVar


def setting(default: Any, label: str, help: str = "", *, min: float | None = None,
            max: float | None = None, choices: tuple | None = None, step: float | None = None,
            suffix: str = "", hidden: bool = False, max_len: int = 200):
    return field(
        default=default,
        metadata=dict(label=label, help=help, min=min, max=max, choices=choices, step=step,
                      suffix=suffix, hidden=hidden, max_len=max_len),
    )


@dataclass
class SettingsSection:
    SECTION: ClassVar[str] = ""
    TITLE: ClassVar[str] = ""

    # ------------------------------------------------------------------ validation
    def validate(self) -> dict[str, str]:
        """Return {field: error}. Empty dict means valid."""
        errors: dict[str, str] = {}
        for f in fields(self):
            err = _check_value(f, getattr(self, f.name))
            if err:
                errors[f.name] = err
        errors.update(self._extra_validation())
        return errors

    def _extra_validation(self) -> dict[str, str]:
        return {}

    # ------------------------------------------------------------------ (de)serialisation
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> tuple["SettingsSection", list[str]]:
        """Build a section tolerantly. Unknown keys are ignored; invalid values fall back to
        defaults. Returns (section, warnings) so the caller can log what was repaired."""
        data = data or {}
        inst = cls()
        warnings: list[str] = []
        for f in fields(cls):
            if f.name not in data:
                continue
            default = getattr(inst, f.name)
            value = _coerce(data[f.name], type(default))
            if value is _INVALID or _check_value(f, value):
                warnings.append(f"{cls.SECTION}.{f.name}: invalid value {data[f.name]!r}, using default {default!r}")
                continue
            setattr(inst, f.name, value)
        if inst._extra_validation():
            warnings.append(f"{cls.SECTION}: inconsistent values, section reset to defaults")
            inst = cls()
        return inst, warnings


_INVALID = object()


def _coerce(value: Any, target: type) -> Any:
    try:
        if target is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            return _INVALID
        if target is int:
            if isinstance(value, bool):
                return _INVALID
            if isinstance(value, float) and not value.is_integer():
                return _INVALID
            return int(value)
        if target is float:
            if isinstance(value, bool):
                return _INVALID
            return float(value)
        if target is str:
            return value if isinstance(value, str) else _INVALID
        if target is list:
            return list(value) if isinstance(value, (list, tuple)) else _INVALID
    except (TypeError, ValueError):
        return _INVALID
    return value


def _check_value(f, value: Any) -> str:
    m = f.metadata
    expected = type(f.default) if f.default is not MISSING else None
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if expected is not None and not isinstance(value, expected):
        return f"expected {expected.__name__}"
    if expected is not bool and isinstance(value, (int, float)) and not isinstance(value, bool):
        if m.get("min") is not None and value < m["min"]:
            return f"must be at least {m['min']}"
        if m.get("max") is not None and value > m["max"]:
            return f"must be at most {m['max']}"
    if m.get("choices") and value not in m["choices"]:
        return f"must be one of {', '.join(map(str, m['choices']))}"
    if isinstance(value, str) and len(value) > m.get("max_len", 200):
        return f"must be at most {m.get('max_len', 200)} characters"
    return ""


# =========================================================================== sections
@dataclass
class GeneralSettings(SettingsSection):
    SECTION: ClassVar[str] = "general"
    TITLE: ClassVar[str] = "General"

    active_mode: str = setting("solo", "Hunting mode", "Solo or duo profile", choices=("solo", "duo"))
    show_hud_on_launch: bool = setting(True, "Show HUD on launch")
    minimize_to_tray: bool = setting(True, "Minimize to system tray", "Closing the main window keeps the app in the tray")
    backup_on_exit: bool = setting(True, "Back up database on exit")
    backups_to_keep: int = setting(10, "Backups to keep", min=1, max=100)
    log_level: str = setting("INFO", "Log level", choices=("DEBUG", "INFO", "WARNING", "ERROR"))


@dataclass
class HudSettings(SettingsSection):
    SECTION: ClassVar[str] = "hud"
    TITLE: ClassVar[str] = "Floating HUD"

    x: int = setting(40, "X position", min=-10000, max=20000, hidden=True)
    y: int = setting(40, "Y position", min=-10000, max=20000, hidden=True)
    width: int = setting(300, "Width", min=220, max=900, suffix=" px")
    height: int = setting(420, "Height (expanded)", min=120, max=1400, suffix=" px")
    opacity: float = setting(0.92, "Opacity", min=0.3, max=1.0, step=0.05)
    mode: str = setting("expanded", "Layout", choices=("compact", "expanded"))
    always_on_top: bool = setting(True, "Always on top")
    click_through: bool = setting(False, "Click-through", "Mouse clicks pass through the HUD. Disable from the tray menu or main window.")
    show_player: bool = setting(True, "Show player status")
    show_party: bool = setting(True, "Show party status")
    show_combat: bool = setting(True, "Show combat")
    show_recommendations: bool = setting(True, "Show recommendations")
    show_session: bool = setting(True, "Show session")
    font_scale: float = setting(1.0, "Text size", min=0.8, max=1.6, step=0.05)
    exclude_from_capture: bool = setting(True, "Hide HUD from screen capture",
                                         "Windows 10 2004+: stops the HUD itself being read as game pixels when it overlaps a region. Also hides it from recordings.")


@dataclass
class RecognitionSettings(SettingsSection):
    SECTION: ClassVar[str] = "recognition"
    TITLE: ClassVar[str] = "Visual Recognition"

    capture_mode: str = setting("window", "Capture mode",
                                "window: regions follow the Tibia window. screen: regions are fixed screen positions",
                                choices=("window", "screen"))
    screen_index: int = setting(1, "Monitor (screen mode)", min=1, max=8)
    window_title: str = setting("Tibia", "Tibia window title starts with", max_len=80)
    interval_ms: int = setting(250, "Recognition interval", "Lower is faster but uses more CPU", min=100, max=2000, step=50, suffix=" ms")
    min_confidence: float = setting(0.80, "Minimum confidence", "Readings below this are treated as unavailable", min=0.5, max=0.99, step=0.01)
    smoothing_frames: int = setting(3, "Smoothing frames", "Median over the last N readings", min=1, max=10)
    idle_interval_ms: int = setting(2000, "Interval when Tibia is not visible", min=500, max=10000, step=100, suffix=" ms")
    ocr_backend: str = setting("template", "Name OCR backend", choices=("template", "tesseract", "off"))
    tesseract_path: str = setting("", "Tesseract executable (optional)", max_len=260)
    low_confidence_alert_s: float = setting(4.0, "Warn when health is unreadable for", min=1.0, max=60.0, step=0.5, suffix=" s")

    def _extra_validation(self) -> dict[str, str]:
        if self.idle_interval_ms < self.interval_ms:
            return {"idle_interval_ms": "must be at least the recognition interval"}
        return {}


@dataclass
class NotificationSettings(SettingsSection):
    SECTION: ClassVar[str] = "notifications"
    TITLE: ClassVar[str] = "Notifications"

    enabled: bool = setting(True, "Notifications enabled")
    quiet_mode: bool = setting(False, "Quiet mode", "Mute sounds and hide normal/elevated toasts")
    critical_ignores_quiet: bool = setting(True, "Critical alerts ignore quiet mode")
    sound_enabled: bool = setting(True, "Play sounds")
    volume: int = setting(70, "Volume", min=0, max=100, suffix=" %")
    duration_ms: int = setting(4000, "Toast duration", min=1000, max=30000, step=500, suffix=" ms")
    cooldown_s: float = setting(6.0, "Repeat cooldown", "Minimum time before the same alert repeats", min=0.0, max=300.0, step=0.5, suffix=" s")
    show_normal: bool = setting(True, "Show normal notifications")
    show_elevated: bool = setting(True, "Show elevated notifications")
    show_critical: bool = setting(True, "Show critical notifications")
    sound_normal: str = setting("soft", "Normal sound", choices=("none", "soft", "chime", "alarm"))
    sound_elevated: str = setting("chime", "Elevated sound", choices=("none", "soft", "chime", "alarm"))
    sound_critical: str = setting("alarm", "Critical sound", choices=("none", "soft", "chime", "alarm"))
    cat_healing: bool = setting(True, "Category: healing")
    cat_mana: bool = setting(True, "Category: mana")
    cat_party: bool = setting(True, "Category: party")
    cat_combat: bool = setting(True, "Category: combat")
    cat_session: bool = setting(True, "Category: session & routes")
    cat_recognition: bool = setting(True, "Category: recognition")


@dataclass
class PartySettings(SettingsSection):
    SECTION: ClassVar[str] = "party"
    TITLE: ClassVar[str] = "Party"

    partner_name: str = setting("", "Partner character name", max_len=40)
    monitor_partner: bool = setting(True, "Monitor partner health (duo mode)")
    partner_slot: int = setting(1, "Partner position in party list", min=1, max=10)


@dataclass
class CombatSettings(SettingsSection):
    SECTION: ClassVar[str] = "combat"
    TITLE: ClassVar[str] = "Combat"

    crowd_elevated: int = setting(5, "Crowd warning at", "Number of creatures in the battle list for an elevated warning",
                                  min=2, max=30, suffix=" creatures")
    crowd_critical: int = setting(8, "Crowd critical at", min=2, max=40, suffix=" creatures")
    alert_priority_creatures: bool = setting(True, "Announce priority creatures",
                                             "Tell me when a creature with a priority of at least the value below appears")
    priority_alert_min: int = setting(5, "Announce from priority", min=1, max=10)
    sort_by_priority: bool = setting(True, "Sort creatures by priority in the HUD")
    trend_window_s: float = setting(3.0, "Health trend window", "Time span used for creature health trends",
                                    min=1.0, max=15.0, step=0.5, suffix=" s")

    def _extra_validation(self) -> dict[str, str]:
        if self.crowd_critical <= self.crowd_elevated:
            return {"crowd_critical": "must be greater than the crowd warning"}
        return {}


ALL_SECTIONS: tuple[type[SettingsSection], ...] = (
    GeneralSettings, HudSettings, RecognitionSettings, NotificationSettings, PartySettings, CombatSettings,
)
