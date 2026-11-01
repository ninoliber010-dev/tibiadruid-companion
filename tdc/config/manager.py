"""ConfigManager: the single source of truth for settings at runtime."""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import fields, replace
from typing import Any, TypeVar

from tdc.config.settings import ALL_SECTIONS, SettingsSection
from tdc.core.errors import ConfigValidationError
from tdc.core.events import EventBus, Topic
from tdc.storage.repositories import SettingsStore

log = logging.getLogger(__name__)
S = TypeVar("S", bound=SettingsSection)


class ConfigManager:
    def __init__(self, store: SettingsStore, bus: EventBus | None = None) -> None:
        self._store = store
        self._bus = bus
        self._lock = threading.RLock()
        self._sections: dict[str, SettingsSection] = {}
        self.load_warnings: list[str] = []
        self.load()

    def load(self) -> None:
        with self._lock:
            self.load_warnings.clear()
            for cls in ALL_SECTIONS:
                section, warnings = cls.from_dict(self._store.load(cls.SECTION))
                for w in warnings:
                    log.warning("Config repaired: %s", w)
                self.load_warnings.extend(warnings)
                self._sections[cls.SECTION] = section
                if warnings or self._store.load(cls.SECTION) is None:
                    self._store.save(cls.SECTION, section.to_dict())

    def get(self, cls: type[S]) -> S:
        """Return a *copy*; mutate it and pass it to ``save`` to apply changes."""
        with self._lock:
            return copy.deepcopy(self._sections[cls.SECTION])  # type: ignore[return-value]

    def save(self, section: SettingsSection) -> None:
        errors = section.validate()
        if errors:
            raise ConfigValidationError(section.SECTION, errors)
        with self._lock:
            self._store.save(section.SECTION, section.to_dict())
            self._sections[section.SECTION] = copy.deepcopy(section)
        log.info("Settings saved: %s", section.SECTION)
        if self._bus:
            self._bus.publish(Topic.CONFIG_CHANGED, section.SECTION)

    def update(self, cls: type[S], **changes: Any) -> S:
        valid = {f.name for f in fields(cls)}
        unknown = set(changes) - valid
        if unknown:
            raise ConfigValidationError(cls.SECTION, {k: "unknown setting" for k in unknown})
        section = replace(self.get(cls), **changes)
        self.save(section)
        return section

    def reset(self, cls: type[S]) -> S:
        section = cls()
        self.save(section)
        return section
