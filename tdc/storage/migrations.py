"""Ordered schema migrations.

Rules:
* Never edit a migration that has shipped; add a new one.
* Each migration runs inside a single transaction together with the version bump.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]


def run_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute several statements inside the caller's transaction.

    (``executescript`` would COMMIT first, breaking the per-migration transaction.)
    """
    buf = ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                conn.execute(buf)
            buf = ""
    if buf.strip():
        raise ValueError(f"Incomplete SQL statement: {buf.strip()[:80]}")


def _v1_schema(conn: sqlite3.Connection) -> None:
    run_script(
        conn,
        """
        CREATE TABLE settings (
            section     TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE hunting_profiles (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            mode        TEXT NOT NULL CHECK (mode IN ('solo','duo')),
            notes       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE healing_rules (
            id          INTEGER PRIMARY KEY,
            profile_id  INTEGER NOT NULL REFERENCES hunting_profiles(id) ON DELETE CASCADE,
            target      TEXT NOT NULL CHECK (target IN ('self','partner')),
            kind        TEXT NOT NULL CHECK (kind IN ('spell','potion','warning')),
            name        TEXT NOT NULL,
            resource    TEXT NOT NULL CHECK (resource IN ('health','mana')),
            threshold   REAL NOT NULL CHECK (threshold >= 0 AND threshold <= 100),
            priority    INTEGER NOT NULL CHECK (priority BETWEEN 0 AND 2),
            enabled     INTEGER NOT NULL DEFAULT 1,
            sort_order  INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_healing_rules_profile ON healing_rules(profile_id);

        CREATE TABLE recognition_regions (
            id          INTEGER PRIMARY KEY,
            kind        TEXT NOT NULL UNIQUE
                        CHECK (kind IN ('health','mana','creatures','battle_list','party')),
            x           INTEGER NOT NULL CHECK (x >= 0),
            y           INTEGER NOT NULL CHECK (y >= 0),
            width       INTEGER NOT NULL CHECK (width > 0),
            height      INTEGER NOT NULL CHECK (height > 0),
            ref_width   INTEGER NOT NULL DEFAULT 0,
            ref_height  INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE creature_priorities (
            name        TEXT PRIMARY KEY COLLATE NOCASE,
            priority    INTEGER NOT NULL DEFAULT 0,
            notes       TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE route_folders (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            parent_id   INTEGER REFERENCES route_folders(id) ON DELETE CASCADE
        );

        CREATE TABLE routes (
            id          INTEGER PRIMARY KEY,
            folder_id   INTEGER REFERENCES route_folders(id) ON DELETE SET NULL,
            name        TEXT NOT NULL,
            mode        TEXT NOT NULL DEFAULT 'any' CHECK (mode IN ('solo','duo','any')),
            description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE waypoints (
            id          INTEGER PRIMARY KEY,
            uid         TEXT NOT NULL UNIQUE,
            route_id    INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
            position    INTEGER NOT NULL,
            name        TEXT NOT NULL,
            x           INTEGER,
            y           INTEGER,
            floor       INTEGER,
            reference   TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            notes       TEXT NOT NULL DEFAULT '',
            screenshot  TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_waypoints_route ON waypoints(route_id, position);

        CREATE TABLE hunt_sessions (
            id          INTEGER PRIMARY KEY,
            profile_id  INTEGER REFERENCES hunting_profiles(id) ON DELETE SET NULL,
            mode        TEXT NOT NULL CHECK (mode IN ('solo','duo')),
            route_id    INTEGER REFERENCES routes(id) ON DELETE SET NULL,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            notes       TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE session_metrics (
            session_id  INTEGER NOT NULL REFERENCES hunt_sessions(id) ON DELETE CASCADE,
            metric      TEXT NOT NULL,
            value       REAL,
            reliability TEXT NOT NULL
                        CHECK (reliability IN ('measured','estimated','manual','unavailable')),
            PRIMARY KEY (session_id, metric)
        );

        CREATE TABLE item_prices (
            name        TEXT PRIMARY KEY COLLATE NOCASE,
            price       INTEGER NOT NULL CHECK (price >= 0)
        );

        CREATE TABLE session_supplies (
            session_id  INTEGER NOT NULL REFERENCES hunt_sessions(id) ON DELETE CASCADE,
            item        TEXT NOT NULL,
            start_qty   INTEGER NOT NULL CHECK (start_qty >= 0),
            end_qty     INTEGER CHECK (end_qty >= 0),
            unit_price  INTEGER NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
            PRIMARY KEY (session_id, item)
        );

        CREATE TABLE session_kills (
            session_id  INTEGER NOT NULL REFERENCES hunt_sessions(id) ON DELETE CASCADE,
            creature    TEXT NOT NULL,
            count       INTEGER NOT NULL CHECK (count >= 0),
            PRIMARY KEY (session_id, creature)
        );

        CREATE TABLE event_log (
            id          INTEGER PRIMARY KEY,
            session_id  INTEGER REFERENCES hunt_sessions(id) ON DELETE CASCADE,
            ts          REAL NOT NULL,
            category    TEXT NOT NULL,
            priority    INTEGER NOT NULL,
            message     TEXT NOT NULL
        );
        CREATE INDEX idx_event_log_session ON event_log(session_id, ts);
        """
    )


def _v2_seed_profiles(conn: sqlite3.Connection) -> None:
    """Default Solo/Duo profiles with *example* Elder Druid rules (all user-editable)."""
    conn.execute("INSERT INTO hunting_profiles(name, mode) VALUES ('Solo', 'solo')")
    conn.execute("INSERT INTO hunting_profiles(name, mode) VALUES ('Duo', 'duo')")
    solo = conn.execute("SELECT id FROM hunting_profiles WHERE name='Solo'").fetchone()[0]
    duo = conn.execute("SELECT id FROM hunting_profiles WHERE name='Duo'").fetchone()[0]

    self_rules = [
        # target, kind, name, resource, threshold, priority
        ("self", "spell", "Exura Gran", "health", 80, 0),
        ("self", "spell", "Exura Vita", "health", 60, 1),
        ("self", "warning", "Critical health", "health", 35, 2),
        ("self", "potion", "Ultimate Mana Potion", "mana", 50, 0),
        ("self", "warning", "Low mana", "mana", 25, 1),
    ]
    partner_rules = [
        ("partner", "spell", "Exura Sio", "health", 70, 1),
        ("partner", "warning", "Partner critical", "health", 35, 2),
    ]
    rows = []
    for order, r in enumerate(self_rules):
        rows.append((solo, *r, order))
        rows.append((duo, *r, order))
    for order, r in enumerate(partner_rules, start=len(self_rules)):
        rows.append((duo, *r, order))
    conn.executemany(
        "INSERT INTO healing_rules(profile_id, target, kind, name, resource, threshold, priority, sort_order)"
        " VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )


def _v3_recognition(conn: sqlite3.Connection) -> None:
    run_script(
        conn,
        """
        CREATE TABLE recognition_calibration (
            kind        TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE ocr_glyphs (
            glyph_key   TEXT PRIMARY KEY,
            text        TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    )


MIGRATIONS: list[Migration] = [
    Migration(1, "initial schema", _v1_schema),
    Migration(2, "seed default solo/duo profiles", _v2_seed_profiles),
    Migration(3, "bar calibration and OCR glyph library", _v3_recognition),
]

LATEST_VERSION = MIGRATIONS[-1].version
