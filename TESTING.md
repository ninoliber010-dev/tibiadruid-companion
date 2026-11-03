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

## Phase 3 coverage (85 tests, 210 in total)
Synthetic screenshots come from `tdc/simulation/synthetic_screen.py` (Tibia-like structure with
known ground truth: status bars, battle list, party list, pixel-font names, noise, text over bars,
occluding windows).
* **Bars**: accuracy at 10 fill levels for health and mana (±1 %), calibration learns hue and exact
  edges, rejects non-bars, textured game view and too-tight rectangles; uncalibrated is less
  confident; noise up to σ=12; text over the bar; wrong-colour calibration; a cover hiding the fill
  edge is unreliable while a cover after a visible edge still reads; fully covered → unavailable;
  empty bar never trusted by default.
* **Lists**: entry detection order and health (±1.5 %), attacked-creature frame (no leakage into
  the next row), empty list, noise, party list.
* **OCR**: taught names read back exactly, new combinations of known letters, unknown letters → “?”,
  mismatch rejection, glyph key round-trip; fuzzy matching with wildcards.
* **Engine**: full cycle (health, mana, creatures + names + target, partner), partner by name vs slot,
  solo ignores partner, missing names without letters, window missing/minimized/not calibrated,
  region outside window, window moved, window resized (anchors + penalty + status), change
  detection, screen mode.
* **Validator**: low confidence gate, single high glitch suppressed, drops pass immediately, large
  rises confirmed, reset on missing data, publishing.
* **Worker/service**: thread publishes and stops cleanly, survives engine exceptions, config built
  from the database and reloaded on changes.
* **UI**: screenshot → regions → learn bars → test; canvas drawing; redraw drops old calibration;
  learn rejects non-bars; teaching names; screenshot error messages; loading image files; live
  recognition end-to-end into the HUD and healing recommendations; simulation/recognition exclusive.

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

## Verifying recognition on Windows (to do with the real client)
1. Calibrate as in `USER_GUIDE.md`; *Test regions* must read 100 % at full bars.
2. Take damage / use mana and compare the HUD with the client at several levels (e.g. 90/60/30 %).
3. Cover a bar with another window: the HUD must show “no data”, not a number.
4. Minimize Tibia and close it: status and alerts must say so.
5. Try 100 %, 125 % and 150 % Windows display scaling.
6. Save problem screenshots (*Diagnostics → Open data folder → screenshots*) — they can become test fixtures.

## Not yet verified
Nothing has been run on Windows yet (development so far is in a Linux container). Windows tray,
DPI awareness, real HUD transparency/click-through, audio output and the PyInstaller build are
verified in Phase 7. Headless Linux reports "does not support setting window opacity" and audio
device warnings — expected, not failures. Recognition tests with
synthetic screenshots arrive in Phase 3.
