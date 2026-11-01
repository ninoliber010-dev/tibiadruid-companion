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

## Phase 2 coverage (64 tests, 125 in total)
* **Notifications**: announce-once, escalation, flicker suppression, critical reminders, quiet mode,
  categories/priorities, sound selection and volume, one-off cooldown, valid WAV generation.
* **Healing engine**: every threshold boundary (strictly below), escalation by warning rules,
  potion vs warning, low confidence and missing data give no advice, disabled rules, duo-only
  partner advice, sorting, publishing, compatibility with the seeded default rules.
* **Simulation**: values in range, determinism, each scenario produces its intended condition.
* **HUD view-model**: nothing shown as fact before data, threshold-based colours, low confidence,
  stale data hidden, partner, creatures/trends, monitoring timer, window-problem status, rounding.
* **HUD UI**: window flags, always-on-top off, click-through + badge, opacity, compact mode,
  section visibility, geometry persistence, off-screen correction, simulation end-to-end,
  duo-only party section, critical toast + alarm, quiet mode, stop clears display, hide/menu,
  render cost budget, Dashboard controls.

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
DPI awareness, real HUD transparency/click-through, audio output and the PyInstaller build are
verified in Phase 7. Headless Linux reports "does not support setting window opacity" and audio
device warnings — expected, not failures. Recognition tests with
synthetic screenshots arrive in Phase 3.
