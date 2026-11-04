"""Example Elder Druid rules and name suggestions. Starting points only — every value is editable.

(The first-start database seed in ``storage/migrations.py`` holds its own frozen copy, because a
shipped migration must never change.)
"""

from __future__ import annotations

# target, kind, name, resource, threshold, priority
SELF_RULES = [
    ("self", "spell", "Exura Gran", "health", 80, 0),
    ("self", "spell", "Exura Vita", "health", 60, 1),
    ("self", "warning", "Critical health", "health", 35, 2),
    ("self", "potion", "Ultimate Mana Potion", "mana", 50, 0),
    ("self", "warning", "Low mana", "mana", 25, 1),
]
PARTNER_RULES = [
    ("partner", "spell", "Exura Sio", "health", 70, 1),
    ("partner", "warning", "Partner critical", "health", 35, 2),
]


def default_rules(mode: str) -> list[tuple]:
    return SELF_RULES + (PARTNER_RULES if mode == "duo" else [])


# Suggestions for the rule editor's name box (you can type anything).
SPELL_SUGGESTIONS = [
    "Exura", "Exura Gran", "Exura Vita", "Exura Sio", "Exura Gran Sio", "Exura Gran Mas Res",
]
POTION_SUGGESTIONS = [
    "Mana Potion", "Strong Mana Potion", "Great Mana Potion", "Ultimate Mana Potion",
    "Health Potion", "Small Health Potion",
]
WARNING_SUGGESTIONS = ["Critical health", "Low health", "Low mana", "Partner critical", "Partner low"]
