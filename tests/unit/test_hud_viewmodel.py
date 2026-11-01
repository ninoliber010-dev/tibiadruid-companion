from tdc.core.models import (
    CreatureReading, FrameReading, HuntMode, Measurement, Priority, RecognitionState, RecognitionStatus,
    Recommendation,
)
from tdc.storage.repositories import HealingRule
from tdc.ui.hud.viewmodel import HudViewModel, pct

RULES = [
    HealingRule(None, 1, "self", "spell", "Exura Gran", "health", 80, 0),
    HealingRule(None, 1, "self", "spell", "Exura Vita", "health", 60, 1),
    HealingRule(None, 1, "self", "warning", "Critical", "health", 35, 2),
    HealingRule(None, 1, "partner", "warning", "Partner critical", "health", 35, 2),
]


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def make(mode=HuntMode.SOLO):
    clock = Clock()
    vm = HudViewModel(lambda: 0.8, lambda: RULES, lambda: mode, lambda: "Solo",
                      partner_name=lambda: "Knighty", stale_after=lambda: 2.0, clock=clock)
    return vm, clock


def fr(hp=90, mp=80, conf=0.95, partner=None, creatures=()):
    return FrameReading(Measurement(hp, conf), Measurement(mp, conf),
                        Measurement(partner, conf) if partner is not None else Measurement.unavailable("not visible"),
                        creatures=creatures, creatures_confidence=0.9)


def test_initial_state_shows_nothing_as_fact():
    vm, _ = make()
    st = vm.state()
    assert st.stale and st.health.value is None and st.health.text == "—"
    assert st.source == "Not running" and st.advice_note == "Waiting for readings"
    assert st.partner is None


def test_levels_follow_user_thresholds():
    vm, _ = make()
    for hp, level in ((90, "ok"), (70, "low"), (50, "warn"), (20, "critical")):
        vm.on_reading(fr(hp=hp))
        assert vm.state().health.level == level, hp


def test_low_confidence_is_unavailable():
    vm, _ = make()
    vm.on_reading(fr(conf=0.5))
    st = vm.state()
    assert st.health.value is None and "low confidence" in st.health.note
    assert "unreliable" in st.advice_note


def test_stale_data_is_hidden():
    vm, clock = make()
    vm.on_reading(fr(hp=55))
    vm.on_recommendations([Recommendation("heal.self", Priority.ELEVATED, "Cast Exura Vita")])
    assert vm.state().health.value == 55 and vm.state().recommendations
    clock.t += 3
    st = vm.state()
    assert st.stale and st.health.value is None and st.recommendations == []


def test_partner_shown_in_duo():
    vm, _ = make(HuntMode.DUO)
    vm.on_reading(fr(partner=30))
    p = vm.state().partner
    assert p.label == "Knighty" and p.value == 30 and p.level == "critical"


def test_partner_unavailable_reason():
    vm, _ = make(HuntMode.DUO)
    vm.on_reading(fr())
    assert vm.state().partner.note == "not visible"


def test_creatures_and_trend():
    vm, _ = make()
    c1 = (CreatureReading("Dragon", Measurement(90, 0.95), 0.95, 0),
          CreatureReading("Hydra", Measurement(50, 0.95), 0.4, 1))
    c2 = (CreatureReading("Dragon", Measurement(70, 0.95), 0.95, 0),)
    vm.on_reading(fr(creatures=c1))
    st = vm.state()
    assert st.creature_summary == "2" and st.creatures[1].name == "Unrecognized"
    vm.on_reading(fr(creatures=c2))
    st = vm.state()
    assert st.creatures[0].trend == "↓" and st.creatures[0].health_text == "70%"


def test_monitoring_timer_and_stop_resets():
    vm, clock = make()
    vm.on_status(RecognitionStatus(RecognitionState.SIMULATED, "Simulation"))
    vm.on_reading(fr())
    clock.t += 65
    vm.on_reading(fr())
    st = vm.state()
    assert st.monitoring_time == "01:05" and st.source == "Simulation"
    vm.on_status(RecognitionStatus(RecognitionState.STOPPED))
    assert vm.state().monitoring_time == "—"


def test_window_problems_shown_as_critical_source():
    vm, _ = make()
    vm.on_status(RecognitionStatus(RecognitionState.WINDOW_NOT_FOUND, "Tibia window not found"))
    st = vm.state()
    assert st.source == "Tibia window not found" and st.source_level == "critical"


def test_pct_rounds_down():
    assert pct(59.99) == "59%" and pct(60.0) == "60%" and pct(0.4) == "0%"
