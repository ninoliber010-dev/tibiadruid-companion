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

## Phase 2 — Floating HUD ✅
- [x] Frameless always-on-top tool window (no taskbar entry); drag to move, resize grip,
      debounced persisted geometry, off-screen position correction
- [x] Opacity, compact/expanded (compact auto-sizes to content), per-section visibility, text size
- [x] Click-through mode with a visible badge; turn off from the tray menu or the Dashboard
- [x] Sections: player, party (duo only), recommendations, creatures with health trend, session —
      unavailable / low-confidence / stale values shown as such, never as numbers
- [x] Status colours derived from the user's own healing thresholds
- [x] Notification manager: priorities, announce-once, escalation, critical reminders, flicker
      suppression (cooldown), quiet mode, categories, per-priority sounds; in-HUD toasts, critical
      border flash, tray balloon for critical alerts when the HUD is hidden
- [x] Sounds synthesised in code (soft/chime/alarm) with volume
- [x] Simulation: 4 deterministic scenarios (steady, dangerous pull, duo partner, recognition dropout),
      start/stop from the Dashboard
- [x] Healing-engine core (brought forward from Phase 4 so the HUD shows real recommendation logic)
- [x] Tray menu: open window, show/hide HUD, click-through, compact, opacity, quiet mode, stop simulation
- Measured: render ≈ 1–2 ms per frame; ~2 % of one core and ~90 MB RSS while simulating (Linux, offscreen).
- Not yet verified on Windows: real transparency/click-through behaviour and audio output.

## Phase 3 — Visual Recognition ✅ (synthetic screenshots; real-client verification pending)
- [x] Tibia window lookup (read-only Win32: title, client rect, minimized/visible, skips own windows)
- [x] "screen" capture mode (fixed monitor positions) as a fallback
- [x] Capture of configured regions only (`mss`), CRC change detection skips unchanged regions
- [x] Regions follow the window; on resize they keep their distance to the nearest window edge,
      with a confidence penalty and a "resized since calibration" status
- [x] Health/mana bar analyzer: colour segmentation, text-over-bar tolerance, occlusion detection,
      step-fit/track/coverage confidence; "Learn bar" calibration (colour + exact extents) that
      rejects non-bars and too-tight rectangles
- [x] Battle list / party list analyzer: bordered health-bar detection, per-entry health,
      attacked-creature (red frame) detection
- [x] Creature names: glyph-template OCR trained in the app ("Teach"), optional Tesseract,
      fuzzy matching (with OCR wildcards) against known creatures + your creature priorities
- [x] Partner chosen by name (OCR) or by position in the party list
- [x] ReadingValidator: confidence gate, median smoothing, drops pass immediately, large rises
      need confirmation (a single bad frame can never hide an emergency)
- [x] Worker thread with configurable interval, idle back-off when Tibia is absent/minimized,
      error back-off, fps reporting; simulation and live recognition are mutually exclusive
- [x] Alerts: monitoring unavailable (critical), not set up (elevated), health unreadable for N s
- [x] Visual Recognition page: screenshot / load image / demo screenshot, draw regions, learn bars,
      test results with previews, teach names, start/stop
- [x] HUD hidden from screen capture on Windows 10 2004+ (so it is never read as game pixels)
- Measured: ~1 ms analysis per cycle with every region changing (≈0.4 % of a core at 250 ms),
  excluding Windows capture time.
- Pending on Windows: real client colours/layout, DPI scaling, capture timing, Tesseract backend.

## Phase 4 — Recommendation Systems ✅
- [x] Healing engine core (self + partner rules, priorities, solo/duo) — done in Phase 2
- [x] Healing Assistant page: rule table per profile (enable toggle, add/edit dialog with validation and
      spell/potion suggestions, delete, reorder, restore example rules), "Try it" sliders, live list
- [x] Potion recommendations and low-mana warnings (potion/warning rule types)
- [x] Combat assistant: creature list sorted by priority, health trend (%/s) and time-to-0 %,
      attacked creature, crowd warning/critical, priority-creature announcements — information only
- [x] Combat Assistant page: live table, creature-priority editor (also feeds OCR name matching),
      combat settings
- [x] Party Settings page: mode switch, live partner bar, partner settings, partner-only rule editor
- [x] RecommendationHub combines healing + combat into one list per reading (correct alert de-duplication)
- [x] HUD: ★ priority creatures shown first (configurable)
- [x] Every shown notification recorded in `event_log` (pruned to 50 000 rows)

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
