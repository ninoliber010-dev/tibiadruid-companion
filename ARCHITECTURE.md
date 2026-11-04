# Tibia Druid Companion — Architecture

Status: **Phases 1–4 implemented** (foundation, floating HUD, visual recognition, recommendation systems). Later sections describe the target design;
anything not yet built is marked with its phase.

---

## 1. Development environment inspection

| Item | Finding | Consequence |
|---|---|---|
| Build host | Linux container, Python 3.13, 4 CPU, no .NET SDK, no Tesseract | Python is immediately usable; C# would need a toolchain install and cannot run WPF here at all |
| Target | Windows 10/11, official Tibia client | All Windows-only code (window lookup, click-through flags, tray) sits behind small adapters with non-Windows fallbacks so the whole app is testable headless |
| GUI test | PySide6 6.x works with `QT_QPA_PLATFORM=offscreen` | UI smoke tests run in CI without a display |

Nothing in this repository has been run on a real Windows machine yet. Windows-specific
behaviour (window detection, capture of a live Tibia client, packaging) must be verified on
Windows before it is called working — see `TESTING.md`.

## 2. Python vs C# evaluation

| Criterion | Python (PySide6 + OpenCV) | C# (.NET 8 WPF/WinUI + OpenCvSharp) |
|---|---|---|
| Screen capture | `mss` (GDI BitBlt, multi-monitor, fast); `ctypes` for Win32 window lookup; optional Windows Graphics Capture later | Excellent native access (BitBlt, DXGI, WGC) |
| Computer vision | OpenCV + NumPy are first-class; fastest iteration on colour segmentation/template matching | OpenCvSharp works but is a wrapper; fewer examples |
| OCR | Tesseract via subprocess or a custom glyph matcher in NumPy | Windows.Media.Ocr built in (decent), Tesseract wrapper |
| UI performance | Qt is native C++; a 10 fps HUD repaint is trivial | WPF is excellent |
| Overlay | Qt: frameless, always-on-top, translucent, `WindowTransparentForInput` for click-through | WPF: same, via `WS_EX_TRANSPARENT` |
| Database | `sqlite3` in the standard library | `Microsoft.Data.Sqlite` |
| Packaging | PyInstaller one-folder build (~120–180 MB) | Single-file self-contained (~70 MB) |
| Testability here | Full (headless Qt, pytest, synthetic images) | Logic only; no WPF on Linux |
| Maintainability | Small, readable codebase; vision code is concise | Strong typing; more boilerplate |

**Decision: Python 3.11+ with PySide6 (Qt 6), OpenCV, NumPy, mss, pyqtgraph, SQLite.**

Reasons: the hardest, highest-risk part of this product is recognition accuracy, and Python's
vision ecosystem gives the fastest iteration on it. Qt gives a modern, styleable UI and a
capable overlay window. Everything can be unit-tested here, including synthetic screenshots.
The accepted costs are a larger installer and the need for disciplined typing (dataclasses,
type hints) to keep the code maintainable.

Dependencies are deliberately few:

| Package | Purpose | Required |
|---|---|---|
| PySide6 | UI, HUD, threads, tray, sound | yes |
| numpy | image arrays | yes |
| opencv-python-headless | colour segmentation, template matching | yes (Phase 3) |
| mss | screen capture | yes (Phase 3) |
| pyqtgraph | analytics charts | yes (Phase 6) |
| Tesseract OCR (external exe) | optional OCR backend for creature names | optional |
| pytest, pytest-qt | tests | dev |
| PyInstaller | Windows executable | build |

## 3. Compliance boundary (design rule, enforced by structure)

The app is **read-only**. It never sends input to Tibia, never reads/writes Tibia memory,
never injects, never touches the Tibia process, and has no anti-cheat evasion. Concretely:

* The only interaction with Tibia is *finding its window rectangle* (Win32 `FindWindow` /
  `GetWindowRect` — read-only, the same calls any screen recorder uses) and *capturing screen
  pixels* of that rectangle.
* There is no code path that imports `SendInput`, `keybd_event`, `mouse_event`,
  `PostMessage`, `WriteProcessMemory`, `OpenProcess`, etc. A unit test
  (`tests/unit/test_compliance.py`) scans the source tree and fails if any of these appear.
* Recommendation modules output *text and sounds for the human*. They have no reference to
  the capture layer or to any OS input API.

Players remain responsible for checking the current Tibia Rules; the app is designed so that
it behaves like a screen-recording + notes tool.

## 4. System architecture

```
                     ┌────────────────────────────── Qt GUI thread ──────────────────────────────┐
 ┌──────────────┐    │  ┌───────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐ │
 │ Capture +    │    │  │ Validator │──▶│ Assistants   │──▶│ HUD ViewModel │──▶│ Floating HUD │ │
 │ Recognition  │────┼─▶│ (confid., │   │ healing /    │   │ (aggregates,  │   │ + Main window│ │
 │ worker thread│ Ev │  │ smoothing)│   │ combat/party │   │  throttles)   │   └──────────────┘ │
 └──────────────┘ Bus│  └───────────┘   └──────┬───────┘   └───────────────┘                    │
        ▲            │                         ▼                                                │
        │ regions,   │                  ┌──────────────┐   ┌───────────────┐                    │
        │ interval   │                  │ Notification │   │ Analytics /   │                    │
 ┌──────┴───────┐    │                  │ manager      │   │ Session svc   │                    │
 │ ConfigManager│◀───┼──────────────────┴──────────────┴───┴───────────────┘                    │
 └──────┬───────┘    └───────────────────────────────────────────────────────────────────────────┘
        ▼
   SQLite (settings, regions, profiles, healing rules, routes, sessions, events)
```

### Modules (package `tdc/`)

| # | Module | Package | Responsibility | Phase |
|---|---|---|---|---|
| 1 | Desktop app | `tdc/ui/` (`main_window.py`, `pages/`) | Navigation, all configuration pages | 1 (shell), filled per phase |
| 2 | Floating HUD | `tdc/ui/hud/` (`viewmodel.py` Qt-free, `window.py`, `widgets.py`, `controller.py`, `sound.py`) | Overlay window, view-model | **2** |
| 3 | Recognition engine | `tdc/recognition/` (`window.py`, `capture.py`, `geometry.py`, `analyzers/`, `ocr/`, `creatures.py`, `engine.py` Qt-free; `service.py` worker thread; `validator.py`) | Window lookup, capture, bar/battle-list analysis, OCR, confidence | **3** |
| 4 | Combat assistant | `tdc/assistants/combat.py` | Creature list, priorities, health trends, info recommendations | **4** |
| 5 | Healing assistant | `tdc/assistants/healing.py`, `defaults.py`; UI `ui/rule_editor.py`, `ui/pages/healing.py` | Threshold → recommendation engine (self & partner) | **2 + 4** |
| 6 | Party assistant | partner rules in `healing.py`, partner reading in `recognition/engine.py`, UI `ui/pages/party.py` | Solo/duo profile, partner monitoring | **4** |
| — | Recommendation hub | `tdc/assistants/hub.py` | Runs all assistants per reading, publishes one combined list | **4** |
| — | Event recorder | `tdc/notifications/recorder.py` | Stores every shown notification in `event_log` | **4** |
| 7 | Route manager | `tdc/routes/` | Routes, folders, waypoints, import/export | 5 |
| 8 | Analytics | `tdc/analytics/` | Sessions, XP/h, supplies, profit, reliability tags | 6 |
| 9 | Notifications | `tdc/notifications/` | Priority, cooldown, dedupe, quiet mode, sounds | **2** |
| 10 | Configuration | `tdc/config/` | Typed, validated, persisted settings | **1** |
| 11 | Database | `tdc/storage/` | SQLite, migrations, backup, recovery | **1** |
| 12 | Logging/diagnostics | `tdc/core/logging_setup.py`, `ui/pages/diagnostics.py` | Rotating log file, in-memory log buffer, health checks | **1** |
| — | Event bus & models | `tdc/core/` | Topics, immutable data models | **1** |
| — | Simulation | `tdc/simulation/` (`scenarios.py` Qt-free, `runner.py` QTimer) | Simulated readings for HUD/assistant development | **2** |
| — | UI services | `tdc/ui/services.py` | Builds notification manager, healing assistant, simulation and HUD controller | **2** |

Rules that keep modules independent:

* `core`, `config`, `storage`, `assistants`, `analytics`, `routes`, `notifications` logic is
  **Qt-free** plain Python → unit-testable in milliseconds.
* Only `ui/` and the thin worker wrapper in `recognition/` import Qt.
* Modules talk through the **EventBus** and immutable dataclasses in `tdc/core/models.py`.
  No assistant imports the recognition package; no recognition code imports the UI.

## 5. How the HUD communicates with the recognition engine

1. **Capture worker** (a `QThread`, Phase 3) wakes every `recognition.interval_ms`
   (default 250 ms, configurable 100–2000). If the Tibia window is missing or minimized it
   publishes a `RecognitionStatus(state=WINDOW_NOT_FOUND|MINIMIZED)` and sleeps longer
   (back-off), instead of burning CPU.
2. It captures only the configured regions (not the full screen) and runs analyzers, producing
   a **`FrameReading`**: e.g. `health=Measurement(value=72.0, confidence=0.97)`,
   `mana=Measurement(None, confidence=0.0, reason="region not calibrated")`, a list of
   `CreatureReading`, `partner_health`. Values that cannot be read are `None` with a reason —
   never guessed.
3. The worker publishes `Topic.FRAME_READING` on the **EventBus**. The bus's dispatcher in the
   app is a Qt queued call, so subscribers always run on the GUI thread; the worker never
   touches widgets.
4. The **ReadingValidator** applies the confidence threshold and short temporal smoothing
   (median of last N frames, reject physically impossible jumps) and publishes
   `Topic.READING_VALIDATED`. Low-confidence measurements are passed on as *unavailable*.
5. **Assistants** (run together by the `RecommendationHub`, which publishes one combined list per
   reading) turn validated readings into `Recommendation`s
   (`Topic.RECOMMENDATIONS`), e.g. `Recommendation(priority=ELEVATED, text="Cast Exura Vita",
   reason="Health 58% < 60%")`.
6. The **NotificationManager** turns new/escalated recommendations into toasts + sounds,
   applying cooldown, de-duplication and quiet mode.
7. The **HUD view-model** keeps the latest state of every section and the HUD repaints at
   most ~10 times per second. Each value carries its reliability so the HUD can show
   `—` / "not calibrated" instead of a number.

Because every stage is an event, the **simulation source** (Phase 2) publishes the same
`FrameReading` objects, so the HUD and assistants are developed and tested before real
recognition exists, and recordings of real frames can be replayed in tests.

## 6. Recognition approach (implemented in Phase 3)

Threading: `RecognitionWorker` is a plain Python thread running `RecognitionEngine.cycle()`.
It only publishes on the event bus. `Services` guarantees the bus uses `QtDispatcher`, so every
subscriber (validator, assistants, HUD, pages) runs on the GUI thread — widgets are never
touched from the worker. On shutdown, queued deliveries are drained and then dropped.

Safety bias in the validator: falling values pass immediately; a rise of more than 30 points
must be seen twice; below-threshold confidence becomes *unavailable*. Change detection uses a
CRC of each captured region, so a static screen costs almost nothing.


* **Coordinates**: regions are stored in physical pixels *relative to the Tibia client area*
  together with the client size at calibration time. If the window moves, regions follow; if
  it is resized, the user is warned and regions are scaled (and flagged lower confidence until
  re-calibrated).
* **Health/mana**: Tibia draws bars with known fill colours. The analyzer measures the filled
  fraction by colour segmentation along the bar's centre row(s). Confidence comes from
  how well pixels match the expected palette and how sharp the fill edge is. Optional OCR of the
  numeric `current/max` text cross-checks the bar when available.
* **Battle list / party list**: entries are found by locating the small health bars (fixed
  height, black border, coloured fill) — robust and font-independent. Each entry's bar gives
  creature/partner health %. The name strip next to it goes to the OCR backend.
* **Creature names**: two OCR backends behind one interface — (a) a *glyph template matcher*
  trained from the user's own screenshots (Tibia uses a pixel font, which suits exact
  matching far better than generic OCR), (b) optional Tesseract. Results are fuzzy-matched
  against a known creature list; the match distance becomes confidence.
* **Change detection**: a cheap hash of each region skips analysis when pixels did not change.

## 7. Data storage

SQLite file `tdc.sqlite3` in the user data directory
(`%LOCALAPPDATA%\TibiaDruidCompanion` on Windows; `TDC_DATA_DIR` overrides). WAL mode,
foreign keys on. Schema migrations are an ordered list in `tdc/storage/migrations.py`,
tracked in `schema_version`; each migration runs in a transaction. On startup the DB is
integrity-checked; a corrupt file is moved aside (`*.corrupt-<timestamp>`) and a fresh DB is
created, and the user is told. Backups use SQLite's online backup API into
`<data dir>/backups/`, keeping the newest N.

Tables (schema v1): `settings` (one JSON document per config section), `hunting_profiles`,
`healing_rules`, `recognition_regions`, `creature_priorities`, `route_folders`, `routes`,
`waypoints`, `hunt_sessions`, `session_metrics`, `session_supplies`, `session_kills`,
`item_prices`, `event_log`. Schema v2 seeds the default Solo/Duo profiles and example
healing rules.

No data leaves the machine. There is no network code.

## 8. Directory structure

```
tibia-druid-companion/
├── tdc/
│   ├── __main__.py            # python -m tdc
│   ├── app.py                 # bootstrap: paths, logging, DB, config, UI
│   ├── core/                  # events.py, models.py, paths.py, logging_setup.py, errors.py
│   ├── config/                # settings.py (typed sections), manager.py
│   ├── storage/               # database.py, migrations.py, repositories.py, backup.py
│   ├── recognition/           # window, capture, geometry, analyzers/, ocr/, engine, service, validator
│   ├── assistants/            # healing.py, combat.py, party.py                                  (Phase 4)
│   ├── routes/                # service.py, io.py                                                (Phase 5)
│   ├── analytics/             # sessions.py, calculations.py, hunt_analyser_import.py            (Phase 6)
│   ├── notifications/         # manager.py, sounds.py                                            (Phase 2)
│   ├── simulation/            # simulated reading source                                          (Phase 2)
│   ├── ui/                    # theme.py, main_window.py, widgets.py, pages/, hud/
│   └── resources/             # icons, sounds
├── tests/                     # unit/, ui/, fixtures/ (synthetic screenshots, sample data)
├── scripts/                   # build_windows.ps1, generate_fixtures.py
└── *.md                       # documentation
```

## 9. Technical risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tibia rules / anti-cheat views on third-party tools | Account risk for the user | Strict read-only design, compliance test, no process access, documented boundary; user must check current rules |
| Screen capture of the Tibia window (GPU-rendered, occluded or minimized) | Blank/incorrect frames | Capture the visible screen region; detect minimized/occluded/absent window and report *unavailable*; future Windows Graphics Capture backend |
| Overlay invisible over exclusive fullscreen | HUD hidden | Document: use windowed or borderless; HUD alerts also play sounds |
| OCR of Tibia's small pixel font | Wrong creature names | Font-independent bar detection; glyph-template OCR trained from user screenshots; fuzzy match to known names; confidence gating |
| Windows display scaling (125%/150%) | Region offsets wrong | Per-monitor DPI awareness; store regions in physical pixels relative to client area; calibration preview |
| UI layout changes between Tibia client updates | Recognition breaks | Everything calibrated by the user; diagnostics show live crops and confidence |
| Stats Tibia does not expose visually (damage dealt, healing) | Can't be measured | Import of Tibia's own Hunt Analyser "copy to clipboard" text (user pastes it), manual entry, reliability tags — never invented |
| Python packaging size / AV false positives with PyInstaller | Install friction | One-folder build, no UPX, document AV exceptions, optional code signing |
| Click-through HUD that the user cannot get back | Usability | Tray menu toggle, main-window toggle, and a visible "click-through" badge on the HUD |

## 10. Phased roadmap

See `DEVELOPMENT_ROADMAP.md` for the per-phase checklist and acceptance criteria.
