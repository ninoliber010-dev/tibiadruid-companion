from tdc.app_context import AppContext
from tdc.config.settings import GeneralSettings
from tdc.core.events import EventBus, Topic
from tdc.core.models import HuntMode
from tdc.storage.backup import list_backups


def test_mode_switch_persists_and_publishes(paths):
    bus = EventBus()
    seen = []
    bus.subscribe(Topic.PROFILE_CHANGED, seen.append)
    ctx = AppContext.create(paths, bus)
    assert ctx.mode == HuntMode.SOLO
    ctx.set_mode(HuntMode.DUO)
    ctx.set_mode(HuntMode.DUO)  # no duplicate event
    assert seen == [HuntMode.DUO]
    ctx.db.close()
    ctx2 = AppContext.create(paths)
    assert ctx2.mode == HuntMode.DUO
    ctx2.db.close()


def test_shutdown_backs_up_when_enabled(paths):
    ctx = AppContext.create(paths)
    ctx.shutdown()
    assert len(list_backups(paths.backups)) == 1
    ctx = AppContext.create(paths)
    ctx.config.update(GeneralSettings, backup_on_exit=False)
    ctx.shutdown()
    assert len(list_backups(paths.backups)) == 1


def test_recovered_database_reports_error(paths):
    paths.database.write_bytes(b"x" * 4096)
    bus = EventBus()
    errors = []
    bus.subscribe(Topic.APP_ERROR, errors.append)
    ctx = AppContext.create(paths, bus)
    assert errors and "damaged" in errors[0]
    ctx.db.close()
