import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from tdc.app_context import AppContext  # noqa: E402
from tdc.core.events import EventBus  # noqa: E402
from tdc.core.paths import AppPaths  # noqa: E402
from tdc.storage.database import Database  # noqa: E402


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    return AppPaths(tmp_path / "data").ensure()


@pytest.fixture
def db(paths) -> Database:
    d = Database(paths.database)
    yield d
    d.close()


@pytest.fixture
def mem_db() -> Database:
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def ctx(paths) -> AppContext:
    c = AppContext.create(paths, EventBus())
    yield c
    try:
        c.db.close()
    except Exception:
        pass
