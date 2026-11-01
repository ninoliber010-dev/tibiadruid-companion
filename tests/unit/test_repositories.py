import pytest

from tdc.core.errors import ValidationError
from tdc.core.models import HuntMode
from tdc.storage.repositories import (
    CreaturePriorityRepository, HealingRule, HealingRuleRepository, HuntingProfile,
    ProfileRepository, Region, RegionRepository,
)


def test_profiles(mem_db):
    repo = ProfileRepository(mem_db)
    assert [p.mode for p in repo.list()] == [HuntMode.SOLO, HuntMode.DUO]
    p = repo.save(HuntingProfile(None, "  Gnome Duo  ", HuntMode.DUO))
    assert p.id and repo.get(p.id).name == "Gnome Duo"
    assert repo.by_mode(HuntMode.SOLO).name == "Solo"
    with pytest.raises(ValidationError):
        repo.save(HuntingProfile(None, "   ", HuntMode.SOLO))


def test_healing_rule_crud(mem_db):
    repo = HealingRuleRepository(mem_db)
    solo = ProfileRepository(mem_db).by_mode(HuntMode.SOLO)
    before = len(repo.for_profile(solo.id))
    rule = repo.save(HealingRule(None, solo.id, "self", "spell", "Exura", "health", 90, 0))
    assert len(repo.for_profile(solo.id)) == before + 1
    rule.threshold = 85
    repo.save(rule)
    assert [r for r in repo.for_profile(solo.id) if r.id == rule.id][0].threshold == 85
    repo.delete(rule.id)
    assert len(repo.for_profile(solo.id)) == before


@pytest.mark.parametrize("kwargs", [
    dict(threshold=101), dict(threshold=-1), dict(priority=3), dict(name=" "),
    dict(target="enemy"), dict(kind="attack"), dict(resource="soul"),
    dict(target="partner", resource="mana"),
])
def test_healing_rule_validation(mem_db, kwargs):
    base = dict(id=None, profile_id=1, target="self", kind="spell", name="Exura", resource="health",
                threshold=50, priority=1)
    base.update(kwargs)
    with pytest.raises(ValidationError):
        HealingRuleRepository(mem_db).save(HealingRule(**base))


def test_regions(mem_db):
    repo = RegionRepository(mem_db)
    repo.save(Region("health", 10, 20, 100, 8, 1920, 1080))
    repo.save(Region("health", 12, 22, 110, 9, 1920, 1080))  # upsert
    assert repo.get("health") == Region("health", 12, 22, 110, 9, 1920, 1080)
    assert len(repo.all()) == 1
    repo.delete("health")
    assert repo.get("health") is None


@pytest.mark.parametrize("region", [
    Region("minimap", 0, 0, 10, 10), Region("mana", -1, 0, 10, 10), Region("mana", 0, 0, 0, 10),
])
def test_region_validation(mem_db, region):
    with pytest.raises(ValidationError):
        RegionRepository(mem_db).save(region)


def test_creature_priorities(mem_db):
    repo = CreaturePriorityRepository(mem_db)
    repo.set("Dragon Lord", 5)
    repo.set("dragon lord", 7)  # case-insensitive key
    assert repo.all() == {"Dragon Lord": 7}
    with pytest.raises(ValidationError):
        repo.set("Hydra", 99)
    repo.delete("DRAGON LORD")
    assert repo.all() == {}
