import pytest

from tdc.assistants.combat import CombatAnalyzer, CombatAssistant, priority_of
from tdc.assistants.hub import RecommendationHub
from tdc.assistants.healing import HealingContext
from tdc.config.settings import CombatSettings
from tdc.core.errors import ConfigValidationError
from tdc.core.events import EventBus, Topic
from tdc.core.models import CreatureReading, FrameReading, HuntMode, Measurement, Priority
from tdc.storage.repositories import HealingRule


def creature(name, hp, slot, targeted=False, conf=0.95, name_conf=0.95):
    return CreatureReading(name, Measurement(hp, conf), name_conf, slot, targeted)


def reading(creatures, ts=0.0, conf=0.95):
    return FrameReading(Measurement(90, 0.95), Measurement(90, 0.95), creatures=tuple(creatures),
                        creatures_confidence=conf, timestamp=ts)


def analyzer(settings=None, prios=None):
    s = settings or CombatSettings()
    return CombatAnalyzer(lambda: s, lambda: prios or {}, lambda: 0.8)


def test_crowd_levels():
    a = analyzer()
    _, recs = a.update(reading([creature("Dragon", 90, i) for i in range(4)]))
    assert recs == []
    _, recs = a.update(reading([creature("Dragon", 90, i) for i in range(5)]))
    assert recs[0].key == "combat.crowd" and recs[0].priority == Priority.ELEVATED
    _, recs = a.update(reading([creature("Dragon", 90, i) for i in range(8)]))
    assert recs[0].priority == Priority.CRITICAL and recs[0].category == "combat"


def test_priority_creatures_sorted_and_announced():
    a = analyzer(prios={"Dragon Lord": 7, "Hydra": 3})
    snap, recs = a.update(reading([creature("Dragon", 90, 0), creature("Hydra", 50, 1),
                                   creature("Dragon Lord", 70, 2, targeted=True)]))
    assert [c.name for c in snap.creatures] == ["Dragon Lord", "Hydra", "Dragon"]
    assert snap.targeted.name == "Dragon Lord"
    pr = [r for r in recs if r.key.startswith("combat.priority")]
    assert pr and "Dragon Lord" in pr[0].text and "your target" in pr[0].text
    # Hydra (3) is below the default announce level (5)
    a2 = analyzer(prios={"Hydra": 3})
    assert not [r for r in a2.update(reading([creature("Hydra", 50, 0)]))[1] if r.key.startswith("combat.priority")]


def test_priority_alerts_can_be_disabled():
    a = analyzer(CombatSettings(alert_priority_creatures=False), {"Dragon Lord": 9})
    assert a.update(reading([creature("Dragon Lord", 70, 0)]))[1] == []


def test_health_trend_and_eta():
    a = analyzer()
    for i, hp in enumerate((80, 70, 60, 50)):
        snap, _ = a.update(reading([creature("Hydra", hp, 0)], ts=i * 0.5))
    c = snap.creatures[0]
    assert c.hp_per_s == pytest.approx(-20, abs=0.5)
    assert c.eta_s == pytest.approx(2.5, abs=0.2)


def test_trend_resets_when_creature_leaves():
    a = analyzer()
    a.update(reading([creature("Hydra", 80, 0)], ts=0))
    a.update(reading([], ts=1))
    snap, _ = a.update(reading([creature("Hydra", 40, 0)], ts=2))
    assert snap.creatures[0].hp_per_s is None


def test_low_confidence_gives_nothing():
    a = analyzer()
    snap, recs = a.update(reading([creature("Dragon", 90, i) for i in range(9)], conf=0.4))
    assert not snap.available and recs == [] and "confidence" in snap.reason


def test_unreliable_names_and_health_hidden():
    a = analyzer(prios={"Dragon Lord": 9})
    snap, recs = a.update(reading([creature("Dragon Lord", 50, 0, name_conf=0.3, conf=0.3)]))
    c = snap.creatures[0]
    assert c.name is None and c.health is None and c.priority == 0
    assert not [r for r in recs if r.key.startswith("combat.priority")]


def test_priority_lookup_case_insensitive():
    assert priority_of("dragon lord", {"Dragon Lord": 4}) == 4
    assert priority_of(None, {"x": 1}) == 0


def test_crowd_settings_validation():
    assert CombatSettings(crowd_elevated=5, crowd_critical=5).validate()
    assert CombatSettings().validate() == {}


def test_hub_combines_healing_and_combat():
    bus = EventBus()
    out = []
    bus.subscribe(Topic.RECOMMENDATIONS, out.append)
    rules = [HealingRule(None, 1, "self", "spell", "Exura Vita", "health", 60, 1)]
    hub = RecommendationHub(bus, lambda: HealingContext(rules, HuntMode.SOLO, 0.8),
                            CombatAssistant(bus, analyzer()))
    r = FrameReading(Measurement(50, 0.95), Measurement(90, 0.95),
                     creatures=tuple(creature("Dragon", 90, i) for i in range(8)), creatures_confidence=0.95)
    bus.publish(Topic.READING_VALIDATED, r)
    keys = [x.key for x in out[-1]]
    assert keys[0] == "combat.crowd" and "heal.self" in keys          # critical first
    assert [x.key for x in hub.last_healing] == ["heal.self"]
