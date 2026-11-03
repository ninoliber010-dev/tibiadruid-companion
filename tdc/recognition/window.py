"""Locating the Tibia window — read-only.

Only window *metadata* is read (title, rectangle, minimized/visible state, owning process id
to skip our own windows). Nothing is sent to the window and the Tibia process is never opened.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Protocol

from tdc import APP_NAME
from tdc.recognition.geometry import Rect


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    client: Rect          # client area in screen coordinates (physical pixels)
    minimized: bool
    visible: bool


class WindowFinder(Protocol):
    def find(self, title_prefix: str) -> WindowInfo | None: ...


def title_matches(title: str, prefix: str) -> bool:
    """Official client titles look like 'Tibia' or 'Tibia - Character Name'."""
    t = title.strip()
    if not t or APP_NAME.lower() in t.lower() or "druid companion" in t.lower():
        return False
    p = (prefix or "Tibia").strip()
    return t == p or t.startswith(p + " - ") or t.startswith(p + " ")


class NullWindowFinder:
    """Used where window lookup is unavailable (non-Windows)."""

    def find(self, title_prefix: str) -> WindowInfo | None:
        return None


class StaticWindowFinder:
    """Returns a fixed window; used by tests and the 'screen' capture mode."""

    def __init__(self, info: WindowInfo | None) -> None:
        self.info = info

    def find(self, title_prefix: str) -> WindowInfo | None:
        return self.info


class Win32WindowFinder:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._user32 = ctypes.windll.user32
        self._own_pid = os.getpid()

    def _windows(self) -> list[tuple[int, str]]:
        ct, wt, u = self._ct, self._wt, self._user32
        found: list[tuple[int, str]] = []
        proc = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def cb(hwnd, _lparam):
            length = u.GetWindowTextLengthW(hwnd)
            if length:
                buf = ct.create_unicode_buffer(length + 1)
                u.GetWindowTextW(hwnd, buf, length + 1)
                pid = wt.DWORD()
                u.GetWindowThreadProcessId(hwnd, ct.byref(pid))
                if pid.value != self._own_pid:
                    found.append((hwnd, buf.value))
            return True

        u.EnumWindows(proc(cb), 0)
        return found

    def find(self, title_prefix: str) -> WindowInfo | None:
        ct, wt, u = self._ct, self._wt, self._user32
        for hwnd, title in self._windows():
            if not title_matches(title, title_prefix):
                continue
            rc = wt.RECT()
            u.GetClientRect(hwnd, ct.byref(rc))
            pt = wt.POINT(0, 0)
            u.ClientToScreen(hwnd, ct.byref(pt))
            return WindowInfo(
                handle=int(hwnd), title=title,
                client=Rect(pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top),
                minimized=bool(u.IsIconic(hwnd)), visible=bool(u.IsWindowVisible(hwnd)),
            )
        return None


def default_window_finder() -> WindowFinder:
    if sys.platform == "win32":
        try:
            return Win32WindowFinder()
        except Exception:  # noqa: BLE001
            pass
    return NullWindowFinder()
