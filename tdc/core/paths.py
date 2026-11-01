"""Locations of user data, logs and backups.

Windows: %LOCALAPPDATA%\\TibiaDruidCompanion
Other:   $XDG_DATA_HOME/TibiaDruidCompanion (or ~/.local/share/...)
The environment variable TDC_DATA_DIR overrides both (used by tests and portable installs).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from tdc import APP_ID


def default_data_dir() -> Path:
    override = os.environ.get("TDC_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_ID


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "tdc.sqlite3"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs / "tdc.log"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def screenshots(self) -> Path:
        return self.root / "screenshots"

    def ensure(self) -> "AppPaths":
        for p in (self.root, self.logs, self.backups, self.screenshots):
            p.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(default_data_dir())
