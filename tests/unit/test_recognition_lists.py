import pytest

from tdc.recognition.analyzers.battle_list import find_entries
from tdc.recognition.creatures import NameMatcher, levenshtein, similarity
from tdc.recognition.ocr.glyphs import GlyphLibrary, bits_from_key, glyph_key, segment, text_mask
from tdc.simulation.synthetic_screen import Entry, Scene, crop, render

CREATURES = [Entry("Dragon Lord", 85, True), Entry("Dragon", 40), Entry("Hydra", 100),
             Entry("Frost Dragon", 12), Entry("Serpent Spawn", 0.9), Entry("Medusa", 57)]


def entries_for(creatures, **kw):
    img, t = render(Scene(creatures=creatures, **kw))
    return find_entries(crop(img, t.regions["battle_list"]))


def test_entries_found_in_order_with_health():
    es = entries_for(CREATURES)
    assert len(es) == len(CREATURES)
    for e, truth in zip(es, CREATURES):
        assert e.health.value == pytest.approx(truth.health, abs=1.5)
        assert e.health.confidence >= 0.9
    assert [e.slot for e in es] == list(range(len(CREATURES)))


def test_targeted_creature_detected_only_once():
    es = entries_for(CREATURES)
    assert [e.targeted for e in es] == [c.targeted for c in CREATURES]


def test_empty_list():
    assert entries_for([]) == []


def test_list_with_noise():
    es = entries_for(CREATURES[:3], noise=6)
    assert len(es) == 3
    assert es[1].health.value == pytest.approx(40, abs=2)


def test_party_list_uses_same_analyzer():
    img, t = render(Scene(party=[Entry("Knight Partner", 64), Entry("Paladin Friend", 22)]))
    es = find_entries(crop(img, t.regions["party"]))
    assert [round(e.health.value) for e in es] == [64, 22]


# ------------------------------------------------------------------ OCR
@pytest.fixture(scope="module")
def trained():
    lib = GlyphLibrary()
    es = entries_for(CREATURES)
    for e, c in zip(es, CREATURES):
        lib.learn(e.name_strip, c.name)
    return lib


def test_learned_names_read_back_exactly(trained):
    for e, c in zip(entries_for(CREATURES), CREATURES):
        text, conf = trained.read(e.name_strip)
        assert text == c.name and conf == 1.0


def test_new_combinations_of_known_letters(trained):
    es = entries_for([Entry("Sea Dragon", 50), Entry("Lord Hydra", 50)])
    assert [trained.read(e.name_strip)[0] for e in es] == ["Sea Dragon", "Lord Hydra"]


def test_unknown_letters_become_question_marks(trained):
    (e,) = entries_for([Entry("Wyvern", 50)])
    text, conf = trained.read(e.name_strip)
    assert "?" in text and conf < 0.9


def test_learn_rejects_mismatched_text():
    (e,) = entries_for([Entry("Hydra", 50)])
    with pytest.raises(ValueError):
        GlyphLibrary().learn(e.name_strip, "Hydras")


def test_glyph_key_roundtrip():
    (e,) = entries_for([Entry("Hydra", 50)])
    for g in segment(text_mask(e.name_strip)):
        assert (bits_from_key(glyph_key(g.bits)) == g.bits).all()


def test_empty_strip_reads_nothing():
    import numpy as np

    assert GlyphLibrary().read(np.zeros((14, 50, 3), np.uint8)) == ("", 0.0)


# ------------------------------------------------------------------ name matching
def test_levenshtein_and_wildcards():
    assert levenshtein("dragon", "dragon") == 0
    assert levenshtein("dragan", "dragon") == 1
    assert levenshtein("dr?gon", "dragon") == 0.5
    assert similarity("Dragon Lord", "dragon lord") == 1.0


def test_matcher_corrects_ocr_errors():
    m = NameMatcher()
    assert m.match("Dragon Lo?d")[0] == "Dragon Lord"
    assert m.match("Frost Dragan")[0] == "Frost Dragon"
    assert m.match("Serpent Spawm")[0] == "Serpent Spawn"
    name, sim = m.match("xqzt")
    assert name is None and sim < 0.75
    assert m.match("")[0] is None
