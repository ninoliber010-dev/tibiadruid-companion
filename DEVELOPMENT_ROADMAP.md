# Development Roadmap

Each phase ends with its tests passing and the docs updated. A phase is only marked done when
its features are implemented **and** tested.

## Phase 1 — Foundation ✅
- [x] Environment inspection and Python vs C# evaluation (`ARCHITECTURE.md`)
- [x] Architecture, directory structure, risks, dependencies
- [x] Entry point `python -m tdc`, `--smoke-test` flag for build verification
- [x] Dark-themed main window with all 9 navigation pages (unbuilt ones clearly marked)
- [x] SQLite: schema v1 for all modules, v2 seed of Solo/Duo profiles, migrations in transactions,
      integrity check, corrupt-file recovery, online backups with pruning, restore
- [x] Typed, validated configuration (5 sections), tolerant loading that repairs bad values,
      auto-generated settings forms with inline errors
- [x] Event bus with GUI-thread dispatcher
- [x] Logging to rotating file + Diagnostics page (environment, DB health, backups, live log)
- [x] System tray (open/quit), minimize-to-tray
- [x] Compliance test (no input/memory/injection APIs, no network code)
- [x] 61 automated tests

## Phase 2 — Floating HUD
- [ ] Frameless always-on-top HUD window; drag to move, resize grip, persisted geometry
- [ ] Opacity slider, compact/expanded modes, per-section visibility
- [ ] Click-through mode with a visible badge; disable via tray menu, main window and HUD hotkey
- [ ] Sections: player, party, combat, recommendations, session — showing "—"/reason when unavailable
- [ ] Notification manager: priorities, cooldown, de-duplication, quiet mode, categories, toasts, sounds
- [ ] Simulation source publishing `FrameReading`s (scripted hunt scenarios)
- Acceptance: HUD runs ≥ 10 fps on simulated data with < 3 % CPU; settings persist; tests for
  notification cooldown/dedupe/quiet mode and HUD view-model.

## Phase 3 — Visual Recognition
- [ ] Tibia window lookup (read-only Win32), minimized/missing detection with back-off
- [ ] Capture of configured regions (`mss`), change detection
- [ ] Calibration UI: take screenshot, drag rectangles for each region, live preview
- [ ] Health/mana bar analyzer (colour segmentation) with confidence
- [ ] Battle list / party list analyzer (health-bar detection, per-entry health %)
- [ ] Creature name OCR: glyph-template backend + optional Tesseract; fuzzy match to known names
- [ ] Validator: confidence gate, median smoothing, impossible-jump rejection
- [ ] Recognition worker thread with configurable interval
- Acceptance: synthetic-screenshot test suite (various fills, noise, scaling, occlusion);
  low-confidence cases return *unavailable*.

## Phase 4 — Recommendation Systems
- [ ] Healing engine (self + partner rules, priorities, solo/duo profiles)
- [ ] Potion recommendations and low-mana warnings
- [ ] Combat assistant: creature list, priorities, health trends, informational hints
- [ ] Duo monitoring with separate thresholds
- [ ] Healing/Combat/Party pages with rule editors and live preview
- [ ] Recommendation events recorded in `event_log`

## Phase 5 — Route Manager
- [ ] Folders, routes, waypoints (UUID, order, coordinates/floor, notes, screenshot)
- [ ] Drag reorder, profile association, informational progress
- [ ] JSON import/export with validation; route visualization

## Phase 6 — Analytics
- [ ] Session start/stop, duration, mode, route
- [ ] XP/h, supplies (start/end inventory × price), loot, profit/loss, kills
- [ ] Paste-import of Tibia's Hunt Analyser text (damage, healing, XP, loot, supplies)
- [ ] Reliability tag on every metric; manual entry fields
- [ ] Charts and session comparison

## Phase 7 — Finalization
- [ ] Complete tests, profiling and optimisation
- [ ] PyInstaller build verified on Windows 10 and 11, installer (optional Inno Setup)
- [ ] Final documentation and troubleshooting
