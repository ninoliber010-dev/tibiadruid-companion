"""Known creature names and fuzzy matching of OCR output against them."""

from __future__ import annotations

# Creatures commonly hunted by druids around level 200-400. The list only helps correct OCR
# mistakes; names you add as creature priorities are matched too.
KNOWN_CREATURES = [
    "Dragon", "Dragon Lord", "Frost Dragon", "Ghastly Dragon", "Undead Dragon", "Hydra",
    "Serpent Spawn", "Medusa", "Sea Serpent", "Young Sea Serpent", "Wyrm", "Elder Wyrm",
    "Behemoth", "Giant Spider", "Grim Reaper", "Lost Soul", "Nightmare", "Hellhound",
    "Juggernaut", "Demon", "Destroyer", "Dark Torturer", "Hellspawn", "Hellfire Fighter",
    "Werewolf", "Werebear", "Wereboar", "Werebadger", "Werefox", "Werehyaena", "Werehyaena Shaman",
    "Werelion", "Werelioness", "White Lion", "Asura", "Dawnfire Asura", "Midnight Asura",
    "Frost Flower Asura", "True Dawnfire Asura", "True Midnight Asura", "True Frost Flower Asura",
    "Lizard Chosen", "Lizard High Guard", "Lizard Legionnaire", "Lizard Dragon Priest",
    "Lizard Zaogun", "Draken Warmaster", "Draken Spellweaver", "Draken Elite", "Draken Abomination",
    "Lizard Magistratus", "Lizard Noble", "Souleater", "Choking Fear", "Retching Horror",
    "Silencer", "Vexclaw", "Hand of Cursed Fate", "Gargoyle", "Stone Golem", "Glooth Golem",
    "Metal Gargoyle", "Rustheap Golem", "Glooth Bandit", "Glooth Brigand", "Mooh'Tah Warrior",
    "Minotaur Hunter", "Worm Priestess", "Moohtant", "Minotaur Amazon", "Feral Sphinx",
    "Sphinx", "Lamassu", "Manticore", "Crypt Warden", "Burning Gladiator", "Priestess of the Wild Sun",
    "Black Sphinx Acolyte", "Cobra Assassin", "Cobra Vizier", "Cobra Scout", "Falcon Knight",
    "Falcon Paladin", "Mercurial Menace", "Gore Horn", "Sulphider", "Bashmu", "Girtablilu Warrior",
    "Gorerilla", "Hulking Prehemoth", "Sabretooth", "Stalking Stalk", "Undertaker",
    "Orc Warlord", "Orc Berserker", "Cyclops", "Ancient Scarab", "Bonebeast", "Vampire",
    "Vampire Viscount", "Vampire Bride", "Banshee", "Lich", "Ghoul", "Necromancer",
    "Quara Constrictor", "Quara Hydromancer", "Quara Mantassin", "Quara Pincher", "Quara Predator",
    "Deepling Warrior", "Deepling Guard", "Deepling Spellsinger", "Deepling Elite",
    "Hero", "Vicious Squire", "Renegade Knight", "Vile Grandmaster", "Nightstalker",
    "Fury", "Hellflayer", "Infernal Demon", "Spiderling", "Werecrocodile",
]


def levenshtein(a: str, b: str) -> float:
    """Edit distance where '?' (unknown OCR glyph) matches anything at half cost."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            sub = 0.0 if ca == cb else (0.5 if ca == "?" else 1.0)
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + sub))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


class NameMatcher:
    def __init__(self, names: list[str] | None = None, min_similarity: float = 0.75) -> None:
        seen, ordered = set(), []
        for n in (names if names is not None else KNOWN_CREATURES):
            if n.lower() not in seen:
                seen.add(n.lower())
                ordered.append(n)
        self.names = ordered
        self.min_similarity = min_similarity

    def match(self, text: str) -> tuple[str | None, float]:
        """Best known name for ``text`` and its similarity (0 if nothing is close enough)."""
        text = text.strip()
        if not text:
            return None, 0.0
        best, best_s = None, 0.0
        for n in self.names:
            s = similarity(text, n)
            if s > best_s:
                best, best_s = n, s
        if best_s < self.min_similarity:
            return None, best_s
        return best, best_s
