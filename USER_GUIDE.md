# User Guide

> Current version: Phase 2 (floating HUD). Sections marked *(planned)* describe features that are
> not available yet.

## Main window
The sidebar has nine pages:

* **Dashboard** — switch between Solo and Duo, show/hide the HUD, toggle click-through and compact
  mode, run a simulation, and see the state of every module. A grey dot and "—" mean the
  information is not available; nothing is guessed.
* **Visual Recognition** *(Phase 3)* — calibrate the screen regions the app reads.
* **Combat Assistant** *(Phase 4)* — recognized creatures and informational hints.
* **Healing Assistant** *(Phase 4)* — edit healing, potion and warning rules.
* **Party Settings** *(Phase 4)* — duo partner monitoring.
* **Route Manager** *(Phase 5)* — plan hunting routes and waypoints.
* **Analytics** *(Phase 6)* — session statistics and history.
* **Configuration** — every setting, grouped in tabs. Press **Save** to apply; **Revert**
  discards edits; **Restore defaults** loads defaults (press Save to apply).
* **Diagnostics** — versions, data folder, database health check, **Back up now**, and the live log.

## Tray
Closing the window keeps the app in the system tray (configurable). Right-click the tray icon for:
open main window, show/hide HUD, click-through, compact mode, opacity, quiet mode, stop
simulation and **Quit**. A database backup is made on exit (configurable).

## Floating HUD
A small always-on-top window that sits next to Tibia.

* **Move**: drag anywhere on its background. **Resize**: bottom-right corner. Position and size
  are remembered; if the saved position is off-screen (monitor removed) it moves back on screen.
* **Header**: mode badge (SOLO/DUO), data source (Not running / Simulation / Live), ▴/▾ for
  compact/expanded, ⋯ for options, ✕ to hide. Right-click the HUD for the same options.
* **Sections**: Player (health, mana), Party (duo only), Recommendations, Creatures, Session.
  Choose which appear under Configuration → Floating HUD.
* **Colours** come from your own healing thresholds: green/blue normal, blue a normal
  recommendation, amber elevated, red critical. A **dashed grey bar** means *no data* — with the
  reason (not calibrated, low confidence, no recent reading) — and is different from an empty bar.
* **Compact mode** shows only player/party bars and the most important recommendation.
* **Click-through**: clicks pass through the HUD to Tibia. An amber badge shows while it is on.
  Turn it off from the **tray icon** menu or the **Dashboard** (the HUD itself can't be clicked then).
* **Notifications** appear as a coloured banner at the top of the HUD with a sound; critical
  alerts also flash the border. If the HUD is hidden, critical alerts appear as a tray message.
  The same alert is not repeated while it stays active (critical ones remind you after the
  cooldown). Quiet mode is in the tray and HUD menus.

## Simulation
Dashboard → *Simulation*: pick a scenario (steady hunt, dangerous pull, duo partner in trouble,
recognition problems) and press **Start simulation**. Everything the HUD shows is then made-up
test data, labelled “Simulation”. Use it to tune thresholds, sounds and the HUD layout.

## Important
Recommendations are information for you. The app never presses keys, clicks, casts or uses
items. Keep Tibia in windowed or borderless mode so the HUD can appear above it.
