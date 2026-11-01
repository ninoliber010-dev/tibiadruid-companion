"""SQLite connection management: open, integrity check, recovery and migrations."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from tdc.core.errors import DatabaseError
from tdc.storage.migrations import LATEST_VERSION, MIGRATIONS

log = logging.getLogger(__name__)


class Database:
    """Owns one SQLite connection. Thread-safe via a lock (writes are tiny and infrequent)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else None
        self._lock = threading.RLock()
        self.recovered_from: Path | None = None
        self._conn = self._open()

    # ---------------------------------------------------------------- lifecycle
    def _connect(self) -> sqlite3.Connection:
        target = str(self.path) if self.path else ":memory:"
        conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if self.path:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _open(self) -> sqlite3.Connection:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = self._connect()
            ok = conn.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise sqlite3.DatabaseError(f"integrity check failed: {ok}")
        except sqlite3.DatabaseError as exc:
            if not self.path:
                raise DatabaseError(str(exc)) from exc
            conn = self._recover(exc)
        self._migrate(conn)
        return conn

    def _recover(self, exc: Exception) -> sqlite3.Connection:
        """Move a corrupt database aside and start fresh. The old file is kept for the user."""
        assert self.path is not None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        aside = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        log.error("Database %s is unreadable (%s); moving it to %s", self.path, exc, aside)
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(self.path) + suffix)
            if src.exists():
                src.replace(Path(str(aside) + suffix))
        self.recovered_from = aside
        return self._connect()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] or 0
        if current > LATEST_VERSION:
            raise DatabaseError(
                f"Database schema v{current} is newer than this app (v{LATEST_VERSION}). "
                "Please update the application."
            )
        for m in MIGRATIONS:
            if m.version <= current:
                continue
            log.info("Applying migration v%d: %s", m.version, m.description)
            try:
                conn.execute("BEGIN")
                m.apply(conn)
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (m.version,))
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                raise DatabaseError(f"Migration v{m.version} failed: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- access
    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def schema_version(self) -> int:
        return self.query_one("SELECT MAX(version) AS v FROM schema_version")["v"]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def integrity_check(self) -> str:
        return self.query_one("PRAGMA integrity_check")[0]

    def table_counts(self) -> dict[str, int]:
        names = [
            r["name"]
            for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {n: self.query_one(f'SELECT COUNT(*) FROM "{n}"')[0] for n in names}
