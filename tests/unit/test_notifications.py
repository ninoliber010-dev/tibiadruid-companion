import pytest

from tdc.config.settings import NotificationSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import Priority, Recommendation
from tdc.notifications.manager import NotificationManager
from tdc.notifications.sounds import SOUNDS, synthesize, write_sound_files


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    bus = EventBus()
    settings = NotificationSettings(cooldown_s=5.0)
    clock = Clock()
    sent = []
    bus.subscribe(Topic.NOTIFICATION, sent.append)
    mgr = NotificationManager(bus, lambda: settings, clock)
    return bus, settings, clock, sent, mgr


def rec(key="heal.self", prio=Priority.ELEVATED, cat="healing"):
    return Recommendation(key, prio, "Cast Exura Vita", "Health 55% < 60%", cat)


def test_new_recommendation_notifies_once(env):
    bus, s, clock, sent, _ = env
    for _ in range(20):
        bus.publish(Topic.RECOMMENDATIONS, [rec()])
        clock.t += 0.25
    assert len(sent) == 1
    assert sent[0].priority == Priority.ELEVATED and sent[0].sound == "chime"


def test_escalation_notifies_immediately(env):
    bus, s, clock, sent, _ = env
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.ELEVATED)])
    clock.t += 0.2
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.CRITICAL)])
    assert [n.priority for n in sent] == [Priority.ELEVATED, Priority.CRITICAL]


def test_flicker_suppressed_within_cooldown(env):
    bus, s, clock, sent, _ = env
    bus.publish(Topic.RECOMMENDATIONS, [rec()])
    clock.t += 1
    bus.publish(Topic.RECOMMENDATIONS, [])
    clock.t += 1
    bus.publish(Topic.RECOMMENDATIONS, [rec()])
    assert len(sent) == 1
    bus.publish(Topic.RECOMMENDATIONS, [])
    clock.t += 10
    bus.publish(Topic.RECOMMENDATIONS, [rec()])
    assert len(sent) == 2


def test_critical_reminder_after_cooldown(env):
    bus, s, clock, sent, _ = env
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.CRITICAL)])
    clock.t += 3
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.CRITICAL)])
    assert len(sent) == 1
    clock.t += 3
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.CRITICAL)])
    assert len(sent) == 2


def test_elevated_is_not_repeated_while_active(env):
    bus, s, clock, sent, _ = env
    for _ in range(10):
        bus.publish(Topic.RECOMMENDATIONS, [rec()])
        clock.t += 10
    assert len(sent) == 1


def test_quiet_mode(env):
    bus, s, clock, sent, mgr = env
    s.quiet_mode = True
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.ELEVATED)])
    assert sent == []
    bus.publish(Topic.RECOMMENDATIONS, [rec(prio=Priority.CRITICAL)])
    assert len(sent) == 1 and sent[0].sound == "alarm"
    s.critical_ignores_quiet = False
    assert mgr.notify("x", Priority.CRITICAL, "boom") is None


def test_disabled_categories_and_priorities(env):
    bus, s, clock, sent, mgr = env
    s.cat_mana = False
    s.show_normal = False
    bus.publish(Topic.RECOMMENDATIONS, [rec("mana.self", Priority.ELEVATED, "mana")])
    assert mgr.notify("session.start", Priority.NORMAL, "Session started") is None
    assert sent == []
    s.enabled = False
    assert mgr.notify("a", Priority.CRITICAL, "x", category="recognition") is None


def test_sound_settings(env):
    bus, s, clock, sent, mgr = env
    s.sound_enabled = False
    assert mgr.notify("a", Priority.CRITICAL, "x").sound == "none"
    s.sound_enabled, s.volume = True, 0
    assert mgr.notify("b", Priority.CRITICAL, "x").sound == "none"
    s.volume, s.sound_elevated = 40, "soft"
    n = mgr.notify("c", Priority.ELEVATED, "x")
    assert n.sound == "soft" and n.volume == 40 and n.duration_ms == s.duration_ms


def test_one_off_notify_cooldown(env):
    _, s, clock, sent, mgr = env
    assert mgr.notify("route.wp", Priority.NORMAL, "Waypoint reached")
    assert mgr.notify("route.wp", Priority.NORMAL, "Waypoint reached") is None
    clock.t += 6
    assert mgr.notify("route.wp", Priority.NORMAL, "Waypoint reached")
    assert len(mgr.history) == 2


def test_sounds_are_valid_wav(tmp_path):
    import wave

    files = write_sound_files(tmp_path)
    assert set(files) == set(SOUNDS)
    for name, path in files.items():
        with wave.open(str(path)) as w:
            assert w.getframerate() == 22050 and w.getnframes() > 1000
        assert len(synthesize(name)) % 2 == 0
