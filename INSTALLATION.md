# Installation

## Requirements
* Windows 10 or 11 (64-bit)
* Tibia running in **windowed** or **borderless** mode (an overlay cannot appear above exclusive fullscreen)
* For running from source: Python 3.11 or 3.12 (64-bit) from python.org

## Run from source
```powershell
git clone <your repository url> tibia-druid-companion
cd tibia-druid-companion
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q        # optional: run the test suite
python -m tdc              # start the app
```

## Build a standalone executable
```powershell
.\scripts\build_windows.ps1
```
This creates `dist\TibiaDruidCompanion\TibiaDruidCompanion.exe` (a folder build — copy the
whole folder). The script runs the tests first and finishes by starting the exe with
`--smoke-test`. *Status: the script is drafted; it will be verified on Windows in Phase 7.*

## Data location
`%LOCALAPPDATA%\TibiaDruidCompanion\` — database `tdc.sqlite3`, `logs\`, `backups\`,
`screenshots\`. Set the environment variable `TDC_DATA_DIR` to use another folder (portable use).

## Uninstall
Delete the program folder, then (optionally) the data folder above.

## Troubleshooting
| Problem | Fix |
|---|---|
| App says the database was damaged and reset | The old file is kept next to the new one as `tdc.sqlite3.corrupt-<date>`. Restore a file from `backups\` if needed (close the app first). |
| "Database schema is newer than this app" | You opened data from a newer version. Update the app. |
| No tray icon | Check Windows taskbar settings → "Other system tray icons". With no tray, closing the window quits the app. |
| Antivirus flags the .exe | PyInstaller builds are sometimes falsely flagged. Build from source yourself or add an exception. |
| Anything else | Open **Diagnostics** → check the log, or read `logs\tdc.log`. |
