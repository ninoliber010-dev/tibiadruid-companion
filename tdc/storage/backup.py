"""Online backups using SQLite's backup API (safe while the app is running)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from tdc.storage.database import Database

log = logging.getLogger(__name__)


def create_backup(db: Database, backup_dir: Path, keep: int = 10) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"tdc-backup-{stamp}.sqlite3"
    dest = sqlite3.connect(str(target))
    try:
        with db._lock:  # noqa: SLF001 - backup must not interleave with writes
            db.connection.backup(dest)
    finally:
        dest.close()
    log.info("Database backup written to %s", target)
    prune_backups(backup_dir, keep)
    return target


def list_backups(backup_dir: Path) -> list[Path]:
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("tdc-backup-*.sqlite3"))


def prune_backups(backup_dir: Path, keep: int) -> None:
    files = list_backups(backup_dir)
    for old in files[: max(0, len(files) - keep)]:
        try:
            old.unlink()
        except OSError:
            log.warning("Could not delete old backup %s", old)


def restore_backup(backup: Path, database_path: Path) -> None:
    """Copy ``backup`` over the live database file. The app must be restarted afterwards
    (call only when the database is closed)."""
    src = sqlite3.connect(str(backup))
    try:
        check = src.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"Backup {backup.name} is damaged: {check}")
        dest = sqlite3.connect(str(database_path))
        try:
            src.backup(dest)
        finally:
            dest.close()
    finally:
        src.close()
