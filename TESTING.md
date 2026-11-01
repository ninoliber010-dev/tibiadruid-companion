# Testing

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
UI tests use `pytest-qt`; `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`, so no display is
needed. On minimal Linux images Qt needs `libegl1 libgl1 libxkbcommon0 libfontconfig1`.

## Layout
| Folder | Contents |
|---|---|
| `tests/unit/` | Qt-free logic: database, migrations, backup, config, repositories, events, compliance |
| `tests/ui/` | Main window navigation, settings forms, diagnostics, GUI-thread dispatch |
| `tests/fixtures/` | Synthetic screenshots and sample datasets (from Phase 3) |

## Phase 1 coverage (61 tests)
* **Database**: fresh migration, seeding, idempotent reopen, persistence across restart, refusal
  of newer schemas, corrupt-file recovery, rollback of a failing migration, FK cascades, CHECK
  constraints, transactions.
* **Backup**: content, pruning, restore, refusal of damaged backups.
* **Configuration**: defaults valid, persistence across restart, range/choice/type validation,
  cross-field validation, unknown keys, copy semantics, repair of corrupt stored values, change events.
* **Repositories**: profiles, healing-rule CRUD and validation, regions, creature priorities.
* **Event bus**: subscribe/unsubscribe, error isolation, custom dispatcher, multi-thread publishing,
  delivery on the Qt GUI thread from a worker thread.
* **Compliance**: source scan for input-simulation, memory, injection and network APIs.
* **UI**: every page reachable, unbuilt modules clearly marked, mode switch, settings save and
  error display, backup button.

## Manual verification
`python -m tdc --smoke-test` starts the app, shows every page and exits with code 0.

## Not yet verified
Nothing has been run on Windows yet (development so far is in a Linux container). Windows tray,
DPI awareness and the PyInstaller build are verified in Phase 7. Recognition tests with
synthetic screenshots arrive in Phase 3.
