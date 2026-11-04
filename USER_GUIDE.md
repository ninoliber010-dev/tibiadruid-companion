# User Guide

> Current version: Phase 4 (recommendation systems). Sections marked *(planned)* describe features that are
> not available yet.

## Main window
The sidebar has nine pages:

* **Dashboard** — switch between Solo and Duo, show/hide the HUD, toggle click-through and compact
  mode, run a simulation, and see the state of every module. A grey dot and "—" mean the
  information is not available; nothing is guessed.
* **Visual Recognition** — calibrate the screen regions the app reads and start live recognition.
* **Combat Assistant** — creatures now (health, trend, time to 0 %, your target), creature
  priorities and combat alert settings.
* **Healing Assistant** — edit healing, potion and warning rules per profile, and try them out.
* **Party Settings** — duo partner: name/position, live health, partner thresholds.
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

## Setting up recognition
Keep Tibia in **windowed** or **borderless** mode and don't move its panels after calibrating.

1. Bring Tibia to **full health and mana**, open **Visual Recognition**, press
   **Take screenshot of Tibia**. (No Tibia? *Load demo screenshot* lets you practise.)
2. Click **Health bar**, then drag a rectangle on the screenshot around the health bar —
   a few pixels *larger* than the bar, so its border is included. Do the same for **Mana bar**.
3. Press **Learn bar** for both. The app learns the exact colour and edges. It refuses areas that
   are not a solid bar with a border.
4. Draw the **Battle list** (the whole list window) and, for duo, the **Party list**.
   *Game view* is an optional fallback when you have no battle list open.
5. Under **Creature names**, type the name shown in each row and press **Teach**. Each letter only
   needs to be taught once; after a few creatures most new names are read automatically.
   Untaught letters show as “?”, and unknown creatures as *Unrecognized* — never a guessed name.
6. Press **Test regions on this screenshot** to check, then **Start recognition**.

The HUD then says **Live**. If Tibia is closed or minimized it shows the problem (and an alert
plays); if a bar is covered by another window, or confidence drops below the threshold, the bar
turns into a dashed “no data” bar instead of showing a wrong number. If health stays unreadable for
a few seconds you get a warning. If you resize the Tibia window, regions follow the panels, but
re-calibrating gives the best accuracy.

**Partner (duo)**: set the partner's name under Configuration → Party for name matching (needs
taught letters), or their position in the party list.

**Settings** (Configuration → Visual Recognition): capture mode (*window* follows Tibia; *screen*
uses fixed positions on a monitor), interval, minimum confidence, smoothing, name OCR backend.

## Healing rules
Healing Assistant → pick **Solo** or **Duo** (the profile you edit; the *active* one is chosen on the
Dashboard). Each rule says: *for* you or your partner, *type* (spell, potion or warning only), the
*name* shown in the HUD, what to *watch* (health or mana), *below* which % it applies, and a
*priority* (normal / elevated / critical).

When several rules match, the HUD suggests the spell or potion with the **lowest threshold** and
uses the **highest priority** of all matches. Example: at 30 % health, *Exura Vita (below 60 %,
elevated)* and *Critical health (below 35 %, critical)* both match → “Cast Exura Vita” shown as
**critical**. Untick a rule to pause it, ▲/▼ to reorder, double-click to edit, *Restore example
rules* to start over. The **Try it** sliders show what would be recommended at any values.

## Combat
Combat Assistant lists what the battle list shows. Add creatures with a **priority** (1–10): they
get a ★ and are listed first in the HUD, and those at or above *Announce from priority* are
announced when they appear. **Crowd warning/critical** alert you when many creatures are on screen.
*Trend* is how fast a creature is losing health; *Time to 0 %* is a rough estimate at that rate.
The app never selects or attacks anything.

## Alert log
Every alert that was actually shown is stored locally (Diagnostics database counts show
`event_log`). Phase 6 uses it for session history.

## Simulation
Dashboard → *Simulation*: pick a scenario (steady hunt, dangerous pull, duo partner in trouble,
recognition problems) and press **Start simulation**. Everything the HUD shows is then made-up
test data, labelled “Simulation”. Use it to tune thresholds, sounds and the HUD layout.

## Important
Recommendations are information for you. The app never presses keys, clicks, casts or uses
items. Keep Tibia in windowed or borderless mode so the HUD can appear above it.
