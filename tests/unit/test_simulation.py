import pytest

from tdc.simulation.scenarios import SCENARIOS, Simulator


@pytest.mark.parametrize("key", [s.key for s in SCENARIOS])
def test_values_stay_in_range(key):
    sim = Simulator(key)
    for _ in range(400):
        r = sim.step(0.25)
        for m in (r.health, r.mana, r.partner_health):
            if m.value is not None:
                assert 0 <= m.value <= 100
            assert 0 <= m.confidence <= 1
        assert r.source == "simulation"


def test_deterministic():
    a, b = Simulator("danger", seed=3), Simulator("danger", seed=3)
    assert [a.step(0.25) for _ in range(50)][-1].health == [b.step(0.25) for _ in range(50)][-1].health


def test_danger_reaches_critical_health():
    sim = Simulator("danger")
    assert min(sim.step(0.25).health.value for _ in range(200)) < 35


def test_duo_has_partner_and_dips():
    sim = Simulator("duo")
    values = [sim.step(0.25).partner_health.value for _ in range(200)]
    assert all(v is not None for v in values) and min(values) < 35


def test_dropout_has_low_confidence_and_missing_values():
    sim = Simulator("dropout")
    frames = [sim.step(0.25) for _ in range(100)]
    assert any(f.health.value is None for f in frames)
    assert any(f.health.value is not None and f.health.confidence < 0.6 for f in frames)


def test_unknown_scenario():
    with pytest.raises(ValueError):
        Simulator("nope")
