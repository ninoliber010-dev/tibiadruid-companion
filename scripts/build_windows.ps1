# Builds a standalone Windows folder: dist\TibiaDruidCompanion\TibiaDruidCompanion.exe
# Run from the project root in PowerShell:  .\scripts\build_windows.ps1
# STATUS: drafted in Phase 1, verified on Windows in Phase 7.
$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name TibiaDruidCompanion `
    --collect-submodules tdc `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick `
    scripts\launcher.py
.\dist\TibiaDruidCompanion\TibiaDruidCompanion.exe --smoke-test
Write-Host "Build finished: dist\TibiaDruidCompanion\TibiaDruidCompanion.exe"
