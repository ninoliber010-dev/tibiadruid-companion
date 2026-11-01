"""AppContext: wires the Qt-free services together. Used by the UI and by tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tdc.config.manager import ConfigManager
from tdc.config.settings import GeneralSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import HuntMode
from tdc.core.paths import AppPaths
from tdc.storage.backup import create_backup
from tdc.storage.database import Database
from tdc.storage.repositories import (
    CreaturePriorityRepository, HealingRuleRepository, ProfileRepository, RegionRepository, SettingsStore,
)

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    paths: AppPaths
    db: Database
    bus: EventBus
    config: ConfigManager
    profiles: ProfileRepository
    healing_rules: HealingRuleRepository
    regions: RegionRepository
    creatures: CreaturePriorityRepository

    @classmethod
    def create(cls, paths: AppPaths, bus: EventBus | None = None) -> "AppContext":
        paths.ensure()
        db = Database(paths.database)
        bus = bus or EventBus()
        ctx = cls(
            paths=paths,
            db=db,
            bus=bus,
            config=ConfigManager(SettingsStore(db), bus),
            profiles=ProfileRepository(db),
            healing_rules=HealingRuleRepository(db),
            regions=RegionRepository(db),
            creatures=CreaturePriorityRepository(db),
        )
        if db.recovered_from:
            bus.publish(Topic.APP_ERROR, f"The database was damaged and has been reset. The old file was kept as {db.recovered_from.name}.")
        return ctx

    # ------------------------------------------------------------------ hunting mode
    @property
    def mode(self) -> HuntMode:
        return HuntMode(self.config.get(GeneralSettings).active_mode)

    def set_mode(self, mode: HuntMode) -> None:
        if mode == self.mode:
            return
        self.config.update(GeneralSettings, active_mode=mode.value)
        log.info("Hunting mode changed to %s", mode.value)
        self.bus.publish(Topic.PROFILE_CHANGED, mode)

    # ------------------------------------------------------------------ shutdown
    def shutdown(self) -> None:
        general = self.config.get(GeneralSettings)
        if general.backup_on_exit:
            try:
                create_backup(self.db, self.paths.backups, keep=general.backups_to_keep)
            except Exception:  # noqa: BLE001
                log.exception("Backup on exit failed")
        self.db.close()
