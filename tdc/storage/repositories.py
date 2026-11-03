"""Typed repositories over the SQLite schema. Input is validated before it reaches SQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tdc.core.errors import ValidationError
from tdc.core.models import HuntMode
from tdc.storage.database import Database

REGION_KINDS = ("health", "mana", "creatures", "battle_list", "party")
RULE_TARGETS = ("self", "partner")
RULE_KINDS = ("spell", "potion", "warning")
RULE_RESOURCES = ("health", "mana")


# --------------------------------------------------------------------------- settings
class SettingsStore:
    """Stores one JSON document per configuration section."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def load(self, section: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT data FROM settings WHERE section = ?", (section,))
        if row is None:
            return None
        try:
            data = json.loads(row["data"])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def save(self, section: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO settings(section, data, updated_at) VALUES (?, ?, datetime('now'))"
            " ON CONFLICT(section) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (section, json.dumps(data, sort_keys=True)),
        )

    def sections(self) -> list[str]:
        return [r["section"] for r in self.db.query("SELECT section FROM settings ORDER BY section")]


# --------------------------------------------------------------------------- profiles
@dataclass
class HuntingProfile:
    id: int | None
    name: str
    mode: HuntMode
    notes: str = ""


class ProfileRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[HuntingProfile]:
        return [
            HuntingProfile(r["id"], r["name"], HuntMode(r["mode"]), r["notes"])
            for r in self.db.query("SELECT * FROM hunting_profiles ORDER BY id")
        ]

    def get(self, profile_id: int) -> HuntingProfile | None:
        r = self.db.query_one("SELECT * FROM hunting_profiles WHERE id = ?", (profile_id,))
        return HuntingProfile(r["id"], r["name"], HuntMode(r["mode"]), r["notes"]) if r else None

    def by_mode(self, mode: HuntMode) -> HuntingProfile | None:
        r = self.db.query_one(
            "SELECT * FROM hunting_profiles WHERE mode = ? ORDER BY id LIMIT 1", (mode.value,)
        )
        return HuntingProfile(r["id"], r["name"], HuntMode(r["mode"]), r["notes"]) if r else None

    def save(self, profile: HuntingProfile) -> HuntingProfile:
        name = profile.name.strip()
        if not name:
            raise ValidationError("Profile name is required")
        if len(name) > 60:
            raise ValidationError("Profile name must be 60 characters or fewer")
        if profile.id is None:
            cur = self.db.execute(
                "INSERT INTO hunting_profiles(name, mode, notes) VALUES (?,?,?)",
                (name, profile.mode.value, profile.notes),
            )
            profile.id = cur.lastrowid
        else:
            self.db.execute(
                "UPDATE hunting_profiles SET name=?, mode=?, notes=? WHERE id=?",
                (name, profile.mode.value, profile.notes, profile.id),
            )
        profile.name = name
        return profile


# --------------------------------------------------------------------------- healing rules
@dataclass
class HealingRule:
    id: int | None
    profile_id: int
    target: str      # self | partner
    kind: str        # spell | potion | warning
    name: str
    resource: str    # health | mana
    threshold: float  # percent, rule fires when value < threshold
    priority: int    # 0 normal, 1 elevated, 2 critical
    enabled: bool = True
    sort_order: int = 0

    def validate(self) -> None:
        errors = []
        if self.target not in RULE_TARGETS:
            errors.append(f"target must be one of {RULE_TARGETS}")
        if self.kind not in RULE_KINDS:
            errors.append(f"kind must be one of {RULE_KINDS}")
        if self.resource not in RULE_RESOURCES:
            errors.append(f"resource must be one of {RULE_RESOURCES}")
        if self.target == "partner" and self.resource != "health":
            errors.append("partner rules can only use health")
        if not self.name.strip():
            errors.append("name is required")
        if not 0 <= float(self.threshold) <= 100:
            errors.append("threshold must be between 0 and 100")
        if self.priority not in (0, 1, 2):
            errors.append("priority must be 0, 1 or 2")
        if errors:
            raise ValidationError("; ".join(errors))


class HealingRuleRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _row(r) -> HealingRule:
        return HealingRule(
            r["id"], r["profile_id"], r["target"], r["kind"], r["name"], r["resource"],
            r["threshold"], r["priority"], bool(r["enabled"]), r["sort_order"],
        )

    def for_profile(self, profile_id: int) -> list[HealingRule]:
        rows = self.db.query(
            "SELECT * FROM healing_rules WHERE profile_id = ? ORDER BY sort_order, id", (profile_id,)
        )
        return [self._row(r) for r in rows]

    def save(self, rule: HealingRule) -> HealingRule:
        rule.validate()
        values = (
            rule.profile_id, rule.target, rule.kind, rule.name.strip(), rule.resource,
            float(rule.threshold), int(rule.priority), int(rule.enabled), int(rule.sort_order),
        )
        if rule.id is None:
            cur = self.db.execute(
                "INSERT INTO healing_rules(profile_id, target, kind, name, resource, threshold,"
                " priority, enabled, sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
                values,
            )
            rule.id = cur.lastrowid
        else:
            self.db.execute(
                "UPDATE healing_rules SET profile_id=?, target=?, kind=?, name=?, resource=?,"
                " threshold=?, priority=?, enabled=?, sort_order=? WHERE id=?",
                (*values, rule.id),
            )
        return rule

    def delete(self, rule_id: int) -> None:
        self.db.execute("DELETE FROM healing_rules WHERE id = ?", (rule_id,))


# --------------------------------------------------------------------------- regions
@dataclass
class Region:
    kind: str
    x: int
    y: int
    width: int
    height: int
    ref_width: int = 0   # client-area size when calibrated (for resize detection)
    ref_height: int = 0

    def validate(self) -> None:
        if self.kind not in REGION_KINDS:
            raise ValidationError(f"Unknown region kind {self.kind!r}")
        if self.x < 0 or self.y < 0:
            raise ValidationError("Region position must not be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValidationError("Region width and height must be positive")


class RegionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[str, Region]:
        return {
            r["kind"]: Region(r["kind"], r["x"], r["y"], r["width"], r["height"], r["ref_width"], r["ref_height"])
            for r in self.db.query("SELECT * FROM recognition_regions")
        }

    def get(self, kind: str) -> Region | None:
        return self.all().get(kind)

    def save(self, region: Region) -> None:
        region.validate()
        self.db.execute(
            "INSERT INTO recognition_regions(kind, x, y, width, height, ref_width, ref_height, updated_at)"
            " VALUES (?,?,?,?,?,?,?, datetime('now'))"
            " ON CONFLICT(kind) DO UPDATE SET x=excluded.x, y=excluded.y, width=excluded.width,"
            " height=excluded.height, ref_width=excluded.ref_width, ref_height=excluded.ref_height,"
            " updated_at=excluded.updated_at",
            (region.kind, region.x, region.y, region.width, region.height, region.ref_width, region.ref_height),
        )

    def delete(self, kind: str) -> None:
        self.db.execute("DELETE FROM recognition_regions WHERE kind = ?", (kind,))


# --------------------------------------------------------------------------- creatures
class CreaturePriorityRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[str, int]:
        return {r["name"]: r["priority"] for r in self.db.query("SELECT * FROM creature_priorities ORDER BY name")}

    def set(self, name: str, priority: int, notes: str = "") -> None:
        name = name.strip()
        if not name:
            raise ValidationError("Creature name is required")
        if not -10 <= priority <= 10:
            raise ValidationError("Priority must be between -10 and 10")
        self.db.execute(
            "INSERT INTO creature_priorities(name, priority, notes) VALUES (?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET priority=excluded.priority, notes=excluded.notes",
            (name, priority, notes),
        )

    def delete(self, name: str) -> None:
        self.db.execute("DELETE FROM creature_priorities WHERE name = ?", (name,))


# --------------------------------------------------------------------------- recognition
class CalibrationRepository:
    """Per-region analyzer calibration (e.g. learned bar colour), stored as JSON."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[str, dict]:
        out = {}
        for r in self.db.query("SELECT kind, data FROM recognition_calibration"):
            try:
                out[r["kind"]] = json.loads(r["data"])
            except json.JSONDecodeError:
                continue
        return out

    def save(self, kind: str, data: dict) -> None:
        if kind not in REGION_KINDS:
            raise ValidationError(f"Unknown region kind {kind!r}")
        self.db.execute(
            "INSERT INTO recognition_calibration(kind, data, updated_at) VALUES (?,?, datetime('now'))"
            " ON CONFLICT(kind) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (kind, json.dumps(data)),
        )

    def delete(self, kind: str) -> None:
        self.db.execute("DELETE FROM recognition_calibration WHERE kind = ?", (kind,))


class GlyphRepository:
    """Learned OCR glyph templates: glyph key -> character(s)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[str, str]:
        return {r["glyph_key"]: r["text"] for r in self.db.query("SELECT glyph_key, text FROM ocr_glyphs")}

    def save_many(self, templates: dict[str, str]) -> None:
        if not templates:
            return
        with self.db.transaction() as conn:
            conn.executemany(
                "INSERT INTO ocr_glyphs(glyph_key, text) VALUES (?,?)"
                " ON CONFLICT(glyph_key) DO UPDATE SET text=excluded.text",
                list(templates.items()),
            )

    def clear(self) -> None:
        self.db.execute("DELETE FROM ocr_glyphs")

    def count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) FROM ocr_glyphs")[0]
