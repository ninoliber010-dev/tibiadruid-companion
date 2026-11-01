import pytest

from tdc.config.manager import ConfigManager
from tdc.config.settings import (
    ALL_SECTIONS, GeneralSettings, HudSettings, NotificationSettings, RecognitionSettings,
)
from tdc.core.errors import ConfigValidationError
from tdc.core.events import EventBus, Topic
from tdc.storage.database import Database
from tdc.storage.repositories import SettingsStore


@pytest.fixture
def manager(db):
    return ConfigManager(SettingsStore(db), EventBus())


def test_defaults_are_valid():
    for cls in ALL_SECTIONS:
        assert cls().validate() == {}, cls.SECTION


def test_defaults_written_on_first_start(manager, db):
    assert set(SettingsStore(db).sections()) == {c.SECTION for c in ALL_SECTIONS}


def test_settings_persist_across_restart(paths):
    db = Database(paths.database)
    ConfigManager(SettingsStore(db)).update(HudSettings, opacity=0.55, mode="compact", x=1234)
    db.close()
    db2 = Database(paths.database)
    hud = ConfigManager(SettingsStore(db2)).get(HudSettings)
    assert (hud.opacity, hud.mode, hud.x) == (0.55, "compact", 1234)
    db2.close()


@pytest.mark.parametrize("changes,field", [
    ({"opacity": 0.1}, "opacity"),
    ({"opacity": 1.5}, "opacity"),
    ({"mode": "huge"}, "mode"),
    ({"width": 50}, "width"),
])
def test_invalid_hud_values_rejected(manager, changes, field):
    with pytest.raises(ConfigValidationError) as exc:
        manager.update(HudSettings, **changes)
    assert field in exc.value.errors
    assert manager.get(HudSettings) == HudSettings()  # nothing applied


def test_wrong_type_rejected(manager):
    with pytest.raises(ConfigValidationError):
        manager.update(NotificationSettings, volume="loud")
    with pytest.raises(ConfigValidationError):
        manager.update(NotificationSettings, enabled=1)  # strict bool on save


def test_cross_field_validation(manager):
    with pytest.raises(ConfigValidationError) as exc:
        manager.update(RecognitionSettings, interval_ms=1500, idle_interval_ms=1000)
    assert "idle_interval_ms" in exc.value.errors


def test_unknown_setting_rejected(manager):
    with pytest.raises(ConfigValidationError):
        manager.update(GeneralSettings, auto_attack=True)


def test_get_returns_copy(manager):
    hud = manager.get(HudSettings)
    hud.opacity = 0.4
    assert manager.get(HudSettings).opacity == HudSettings().opacity


def test_corrupt_stored_values_are_repaired(db):
    store = SettingsStore(db)
    store.save("hud", {"opacity": "abc", "width": 9999, "mode": "compact", "unknown": 1, "x": 5.0})
    db.execute("INSERT OR REPLACE INTO settings(section, data) VALUES ('general', '{not json')")
    mgr = ConfigManager(store)
    hud = mgr.get(HudSettings)
    assert hud.opacity == HudSettings().opacity
    assert hud.width == HudSettings().width
    assert hud.mode == "compact" and hud.x == 5
    assert mgr.get(GeneralSettings) == GeneralSettings()
    assert any("hud.opacity" in w for w in mgr.load_warnings)
    # repaired values were written back
    assert store.load("hud")["opacity"] == HudSettings().opacity


def test_inconsistent_section_reset(db):
    SettingsStore(db).save("recognition", {"interval_ms": 2000, "idle_interval_ms": 500})
    mgr = ConfigManager(SettingsStore(db))
    assert mgr.get(RecognitionSettings) == RecognitionSettings()


def test_change_event_published(db):
    bus = EventBus()
    seen = []
    bus.subscribe(Topic.CONFIG_CHANGED, seen.append)
    ConfigManager(SettingsStore(db), bus).update(NotificationSettings, volume=10)
    assert seen == ["notifications"]


def test_reset_restores_defaults(manager):
    manager.update(NotificationSettings, volume=5, quiet_mode=True)
    manager.reset(NotificationSettings)
    assert manager.get(NotificationSettings) == NotificationSettings()
