import sqlite3

import pytest

from tdc.storage.backup import create_backup, list_backups, restore_backup
from tdc.storage.database import Database


def test_backup_contains_data(db, paths):
    db.execute("INSERT INTO item_prices(name, price) VALUES ('Great Mana Potion', 144)")
    path = create_backup(db, paths.backups)
    con = sqlite3.connect(path)
    assert con.execute("SELECT price FROM item_prices").fetchone()[0] == 144
    con.close()


def test_backups_are_pruned(db, paths):
    for _ in range(5):
        create_backup(db, paths.backups, keep=3)
    assert len(list_backups(paths.backups)) == 3


def test_restore_backup(paths):
    db = Database(paths.database)
    db.execute("INSERT INTO item_prices(name, price) VALUES ('a', 1)")
    backup = create_backup(db, paths.backups)
    db.execute("DELETE FROM item_prices")
    db.close()
    restore_backup(backup, paths.database)
    db2 = Database(paths.database)
    assert db2.query_one("SELECT COUNT(*) FROM item_prices")[0] == 1
    db2.close()


def test_restore_refuses_damaged_backup(paths, tmp_path):
    bad = tmp_path / "tdc-backup-bad.sqlite3"
    bad.write_bytes(b"garbage" * 200)
    with pytest.raises(Exception):
        restore_backup(bad, paths.database)
