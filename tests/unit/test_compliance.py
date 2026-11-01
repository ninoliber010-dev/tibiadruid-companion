"""Guard rail: the source tree must not contain input-simulation, memory or injection APIs."""

import re
from pathlib import Path

import tdc

FORBIDDEN = [
    r"\bSendInput\b", r"\bkeybd_event\b", r"\bmouse_event\b", r"\bPostMessage[AW]?\b",
    r"\bSendMessage[AW]?\b", r"\bWriteProcessMemory\b", r"\bReadProcessMemory\b",
    r"\bOpenProcess\b", r"\bCreateRemoteThread\b", r"\bVirtualAllocEx\b", r"\bSetWindowsHookEx",
    r"\bpyautogui\b", r"\bpynput\b", r"\bpydirectinput\b", r"\binterception\b", r"\bpymem\b",
    r"\bkeyboard\.(press|write|send)\b", r"\bmouse\.(click|move)\b",
]


def test_no_forbidden_apis_in_source():
    root = Path(tdc.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if re.search(pattern, text):
                offenders.append(f"{path.relative_to(root)}: {pattern}")
    assert not offenders, "Forbidden gameplay-automation APIs found:\n" + "\n".join(offenders)


def test_no_network_code():
    root = Path(tdc.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(import requests|urllib\.request|http\.client|socket\.socket)\b", text), path
