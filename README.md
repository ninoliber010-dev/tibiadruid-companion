# Tibia Druid Companion

A **read-only** desktop hunting companion for Elder Druids (level 200–400) on the official
Tibia Windows client. It watches parts of your screen you choose, and shows health/mana,
party, creature and session information in a floating HUD with healing and potion
*recommendations*. It never plays the game for you.

> **What it will never do:** send keyboard/mouse input to Tibia, cast spells, use potions or
> items, target or attack, move your character, read or modify game memory, inject into the
> client, or try to hide from anti-cheat. A unit test enforces this on every build.
> Check the current Tibia Rules yourself before using any third-party tool.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 Foundation | Architecture, app shell, SQLite + migrations, config, logging, diagnostics | **Done** |
| 2 Floating HUD | Overlay, transparency, compact/expanded, tray, notifications, simulated data, healing-engine core | **Done** |
| 3 Visual recognition | Capture, calibration, health/mana bars, battle list, party list, name OCR, confidence, validator | **Done** (not yet tried on a real Tibia client) |
| 4 Recommendations | Healing rule editor, potions, combat assistant, creature priorities, duo partner page, alert log | **Done** — 234 automated tests in total |
| 5 Route manager | Routes, folders, waypoints, import/export, visualization | Planned |
| 6 Analytics | Sessions, XP/h, supplies, profit, charts, Hunt Analyser import | Planned |
| 7 Finalization | Packaging, performance, Windows verification | Planned |

Pages for modules that are not built yet say so explicitly; nothing is faked. Besides live
recognition, the HUD can be driven by **simulated** hunts from the Dashboard (labelled
“Simulation”), and calibration can be tried on a synthetic **demo screenshot**.

> Recognition has been developed and tested against synthetic, Tibia-like screenshots. It has not
> yet been run against the real client, whose colours and layout will need the calibration step
> (and possibly analyzer tuning) — see `TESTING.md`.

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate elsewhere)
pip install -r requirements-dev.txt
python -m tdc
```

Run tests: `python -m pytest -q`. See `INSTALLATION.md` for the Windows executable build.

## Documentation

* `ARCHITECTURE.md` — technology decision, modules, data flow, risks
* `DEVELOPMENT_ROADMAP.md` — phases and acceptance criteria
* `INSTALLATION.md` — install, build the .exe, troubleshooting
* `CONFIGURATION.md` — every setting and where it is stored
* `USER_GUIDE.md` — how to use the app
* `TESTING.md` — test strategy and how to run tests

## Privacy

All data (settings, sessions, screenshots) stays on your PC in
`%LOCALAPPDATA%\TibiaDruidCompanion`. The app contains no network code.
