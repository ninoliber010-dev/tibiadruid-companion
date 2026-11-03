import sqlite3

import pytest

from tdc.core.errors import DatabaseError
from tdc.storage import migrations
from tdc.storage.database import Database
from tdc.storage.migrations import LATEST_VERSION

EXPECTED_TABLES = {
    "settings", "hunting_profiles", "healing_rules", "recognition_regions", "creature_priorities",
    "route_folders", "routes", "waypoints", "hunt_sessions", "session_metrics", "item_prices",
    "session_supplies", "session_kills", "event_log", "schema_version", "recognition_calibration",
    "ocr_glyphs",
}


def test_fresh_database_is_migrated_to_latest(db):
    assert db.schema_version() == LATEST_VERSION
    assert EXPECTED_TABLES <= set(db.table_counts())


def test_default_profiles_are_seeded(db):
    modes = {r["name"]: r["mode"] for r in db.query("SELECT name, mode FROM hunting_profiles")}
    assert modes == {"Solo": "solo", "Duo": "duo"}
    duo_partner_rules = db.query(
        "SELECT * FROM healing_rules r JOIN hunting_profiles p ON p.id = r.profile_id "
        "WHERE p.name='Duo' AND r.target='partner'")
    solo_partner_rules = db.query(
        "SELECT * FROM healing_rules r JOIN hunting_profiles p ON p.id = r.profile_id "
        "WHERE p.name='Solo' AND r.target='partner'")
    assert duo_partner_rules and not solo_partner_rules


def test_reopen_is_idempotent(paths):
    Database(paths.database).close()
    db2 = Database(paths.database)
    assert db2.schema_version() == LATEST_VERSION
    assert db2.query_one("SELECT COUNT(*) FROM hunting_profiles")[0] == 2
    assert db2.query_one("SELECT COUNT(*) FROM schema_version")[0] == len(migrations.MIGRATIONS)
    db2.close()


def test_data_persists_across_restart(paths):
    d = Database(paths.database)
    d.execute("INSERT INTO item_prices(name, price) VALUES ('Ultimate Mana Potion', 438)")
    d.close()
    d2 = Database(paths.database)
    assert d2.query_one("SELECT price FROM item_prices WHERE name='ultimate mana potion'")[0] == 438
    d2.close()


def test_newer_schema_is_refused(paths):
    d = Database(paths.database)
    d.execute("INSERT INTO schema_version(version) VALUES (999)")
    d.close()
    with pytest.raises(DatabaseError, match="newer"):
        Database(paths.database)


def test_corrupt_file_is_moved_aside_and_recreated(paths):
    paths.database.write_bytes(b"this is not a sqlite database" * 100)
    d = Database(paths.database)
    assert d.recovered_from is not None and d.recovered_from.exists()
    assert d.schema_version() == LATEST_VERSION
    d.close()


def test_failed_migration_rolls_back(paths, monkeypatch):
    def broken(conn):
        conn.execute("CREATE TABLE half_done (x INTEGER)")
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS + [migrations.Migration(99, "broken", broken)])
    monkeypatch.setattr("tdc.storage.database.MIGRATIONS", migrations.MIGRATIONS)
    monkeypatch.setattr("tdc.storage.database.LATEST_VERSION", 99)
    with pytest.raises(DatabaseError, match="v99"):
        Database(paths.database)
    raw = sqlite3.connect(paths.database)
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = raw.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    raw.close()
    assert "half_done" not in tables
    assert version == LATEST_VERSION  # earlier migrations kept, broken one not recorded


def test_foreign_keys_cascade(mem_db):
    pid = mem_db.query_one("SELECT id FROM hunting_profiles WHERE name='Duo'")[0]
    assert mem_db.query_one("SELECT COUNT(*) FROM healing_rules WHERE profile_id=?", (pid,))[0] > 0
    mem_db.execute("DELETE FROM hunting_profiles WHERE id=?", (pid,))
    assert mem_db.query_one("SELECT COUNT(*) FROM healing_rules WHERE profile_id=?", (pid,))[0] == 0


def test_check_constraints_reject_bad_rows(mem_db):
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO hunting_profiles(name, mode) VALUES ('X', 'trio')")
    with pytest.raises(sqlite3.IntegrityError):
        mem_db.execute("INSERT INTO item_prices(name, price) VALUES ('x', -1)")


def test_transaction_rolls_back_on_error(mem_db):
    with pytest.raises(RuntimeError):
        with mem_db.transaction() as conn:
            conn.execute("INSERT INTO item_prices(name, price) VALUES ('a', 1)")
            raise RuntimeError
    assert mem_db.query_one("SELECT COUNT(*) FROM item_prices")[0] == 0


def test_run_script_rejects_incomplete_sql(mem_db):
    with pytest.raises(ValueError):
        migrations.run_script(mem_db.connection, "CREATE TABLE t (x INTEGER)")
