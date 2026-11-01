"""Plays notification sounds with QSoundEffect; silently falls back to a system beep."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from tdc.notifications.sounds import write_sound_files

log = logging.getLogger(__name__)


class SoundPlayer(QObject):
    def __init__(self, sound_dir: Path) -> None:
        super().__init__()
        self._effects = {}
        self.last_played: str | None = None
        try:
            from PySide6.QtMultimedia import QSoundEffect

            for name, path in write_sound_files(sound_dir).items():
                eff = QSoundEffect(self)
                eff.setSource(QUrl.fromLocalFile(str(path)))
                self._effects[name] = eff
        except Exception:  # noqa: BLE001
            log.warning("Sound effects unavailable; using system beep", exc_info=True)

    def play(self, name: str, volume: int) -> None:
        if name == "none" or volume <= 0:
            return
        self.last_played = name
        eff = self._effects.get(name)
        if eff is None:
            from PySide6.QtWidgets import QApplication

            QApplication.beep()
            return
        eff.setVolume(max(0.0, min(1.0, volume / 100.0)))
        eff.play()
