import pytest

from tdc.assistants.healing import HealingAssistant, HealingContext, evaluate
from tdc.core.events import EventBus, Topic
from tdc.core.models import FrameReading, HuntMode, Measurement, Priority
from tdc.storage.repositories import HealingRule


def rule(target, kind, name, resource, threshold, priority, enabled=True, order=0):
    return HealingRule(None, 1, target, kind, name, resource, threshold, priority, enabled, order)


RULES = [
    rule("self", "spell", "Exura Gran", "health", 80, 0),
    rule("self", "spell", "Exura Vita", "health", 60, 1),
    rule("self", "warning", "Critical health", "health", 35, 2),
    rule("self", "potion", "Ultimate Mana Potion", "mana", 50, 0),
    rule("self", "warning", "Low mana", "mana", 25, 1),
    rule("partner", "spell", "Exura Sio", "health", 70, 1),
    rule("partner", "warning", "Partner critical", "health", 35, 2),
]


def ctx(mode=HuntMode.SOLO, rules=RULES, **kw):
    return HealingContext(rules=rules, mode=mode, min_confidence=0.8, **kw)


def reading(hp=100, mp=100, partner=None, conf=0.95):
    return FrameReading(Measurement(hp, conf), Measurement(mp, conf),
                        Measurement(partner, conf) if partner is not None else Measurement.unavailable("x"))


def by_key(recs):
    return {r.key: r for r in recs}


@pytest.mark.parametrize("hp,text,prio", [
    (90, None, None),
    (80, None, None),                       # threshold is "below", not "at"
    (79.9, "Cast Exura Gran", Priority.NORMAL),
    (59, "Cast Exura Vita", Priority.ELEVATED),
    (34, "Cast Exura Vita", Priority.CRITICAL),  # critical warning escalates the spell
    (0, "Cast Exura Vita", Priority.CRITICAL),
])
def test_health_thresholds(hp, text, prio):
    r = by_key(evaluate(reading(hp=hp), ctx())).get("heal.self")
    assert (r.text if r else None) == text
    assert (r.priority if r else None) == prio


def test_reason_never_contradicts_threshold():
    r = by_key(evaluate(reading(hp=59.7), ctx()))["heal.self"]
    assert r.reason == "Health 59% < 60%"


@pytest.mark.parametrize("mp,text,prio", [
    (60, None, None),
    (45, "Use Ultimate Mana Potion", Priority.NORMAL),
    (20, "Use Ultimate Mana Potion", Priority.ELEVATED),
])
def test_mana_thresholds(mp, text, prio):
    r = by_key(evaluate(reading(mp=mp), ctx())).get("mana.self")
    assert (r.text if r else None) == text
    assert (r.priority if r else None) == prio


def test_warning_only_when_no_action_rule():
    rules = [rule("self", "warning", "Low mana", "mana", 25, 1)]
    r = by_key(evaluate(reading(mp=10), ctx(rules=rules)))["mana.self"]
    assert r.text == "Low mana" and r.priority == Priority.ELEVATED


def test_low_confidence_gives_no_advice():
    assert evaluate(reading(hp=10, mp=10, conf=0.5), ctx()) == []


def test_unavailable_gives_no_advice():
    r = FrameReading(Measurement.unavailable("not calibrated"), Measurement.unavailable("not calibrated"))
    assert evaluate(r, ctx()) == []


def test_disabled_rules_ignored():
    rules = [rule("self", "spell", "Exura Gran", "health", 80, 0, enabled=False)]
    assert evaluate(reading(hp=50), ctx(rules=rules)) == []


def test_partner_only_in_duo():
    assert "heal.partner" not in by_key(evaluate(reading(partner=20), ctx(HuntMode.SOLO)))
    r = by_key(evaluate(reading(partner=20), ctx(HuntMode.DUO, partner_name="Knighty")))["heal.partner"]
    assert r.text == "Cast Exura Sio" and r.priority == Priority.CRITICAL
    assert r.reason.startswith("Knighty health 20%") and r.category == "party"


def test_partner_monitoring_can_be_disabled():
    assert evaluate(reading(partner=20), ctx(HuntMode.DUO, monitor_partner=False)) == []


def test_results_sorted_by_priority():
    recs = evaluate(reading(hp=70, mp=10, partner=30), ctx(HuntMode.DUO))
    assert [r.priority for r in recs] == sorted([r.priority for r in recs], reverse=True)


def test_assistant_publishes_recommendations():
    bus = EventBus()
    out = []
    bus.subscribe(Topic.RECOMMENDATIONS, out.append)
    HealingAssistant(bus, lambda: ctx())
    bus.publish(Topic.READING_VALIDATED, reading(hp=50))
    assert out and out[-1][0].text == "Cast Exura Vita"


def test_default_seeded_rules_work_with_engine(mem_db):
    from tdc.storage.repositories import HealingRuleRepository, ProfileRepository

    duo = ProfileRepository(mem_db).by_mode(HuntMode.DUO)
    rules = HealingRuleRepository(mem_db).for_profile(duo.id)
    recs = by_key(evaluate(reading(hp=30, mp=20, partner=30), ctx(HuntMode.DUO, rules=rules)))
    assert set(recs) == {"heal.self", "mana.self", "heal.partner"}
    assert recs["heal.self"].priority == Priority.CRITICAL
