# Configuration

All settings are edited in the app (**Configuration** page) — no file editing is needed.
They are stored as one JSON document per section in the `settings` table of
`tdc.sqlite3`. Invalid values are rejected when saving (the field shows the error). If a stored
value becomes invalid (e.g. a manual database edit), it is replaced with the default at start
and a warning is written to the log.

## General
| Setting | Default | Range |
|---|---|---|
| Hunting mode | solo | solo / duo (also switchable on the Dashboard) |
| Show HUD on launch | on | |
| Minimize to system tray | on | closing the window keeps the app running in the tray |
| Back up database on exit | on | |
| Backups to keep | 10 | 1–100 |
| Log level | INFO | DEBUG / INFO / WARNING / ERROR |

## Floating HUD (used from Phase 2)
Width 220–900 px, height 120–1400 px, opacity 0.30–1.00, layout compact/expanded, always on top,
click-through, section visibility (player, party, combat, recommendations, session), text size
0.8–1.6×. Position is saved automatically when you move the HUD.

## Visual Recognition (used from Phase 3)
| Setting | Default | Range | Meaning |
|---|---|---|---|
| Tibia window title contains | Tibia | text | used to find the client window |
| Recognition interval | 250 ms | 100–2000 | lower = faster, more CPU |
| Minimum confidence | 0.80 | 0.50–0.99 | readings below are shown as unavailable |
| Smoothing frames | 3 | 1–10 | median filter length |
| Interval when Tibia is not visible | 2000 ms | 500–10000, ≥ interval | back-off to save CPU |
| Name OCR backend | template | template / tesseract / off | |
| Tesseract executable | empty | path | only for the tesseract backend |

Screen regions (health, mana, creatures, battle list, party) are stored in the
`recognition_regions` table with the client size at calibration time.

## Notifications (used from Phase 2)
Enabled, quiet mode, critical-ignores-quiet, sounds on/off, volume 0–100 %, toast duration
1–30 s, repeat cooldown 0–300 s, per-priority visibility and sound (none/soft/chime/alarm), and
per-category switches (healing, mana, party, combat, session & routes, recognition).

## Party
Partner name, monitor partner (duo), partner position in the party list (1–10).

## Healing profiles
Two profiles are created on first start — **Solo** and **Duo** — with *example* Elder Druid rules.
They are starting points, not advice; verify spell names and adjust every threshold.

| Profile | Target | Type | Name | Resource | Below | Priority |
|---|---|---|---|---|---|---|
| both | self | spell | Exura Gran | health | 80 % | normal |
| both | self | spell | Exura Vita | health | 60 % | elevated |
| both | self | warning | Critical health | health | 35 % | critical |
| both | self | potion | Ultimate Mana Potion | mana | 50 % | normal |
| both | self | warning | Low mana | mana | 25 % | elevated |
| Duo | partner | spell | Exura Sio | health | 70 % | elevated |
| Duo | partner | warning | Partner critical | health | 35 % | critical |

The rule editor arrives in Phase 4.
