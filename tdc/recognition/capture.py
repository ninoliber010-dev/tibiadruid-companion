"""Screen capture of small rectangles (BGR numpy arrays)."""

from __future__ import annotations

import threading
from typing import Protocol

import numpy as np

from tdc.recognition.geometry import Rect


class Capturer(Protocol):
    def grab(self, rect: Rect) -> np.ndarray: ...


class MssCapturer:
    """GDI screen capture via ``mss``. One mss instance per thread (mss is not thread-safe)."""

    def __init__(self) -> None:
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss

            sct = mss.mss()
            self._local.sct = sct
        return sct

    def grab(self, rect: Rect) -> np.ndarray:
        shot = self._sct().grab({"left": rect.x, "top": rect.y, "width": rect.width, "height": rect.height})
        arr = np.asarray(shot, dtype=np.uint8)     # BGRA
        return np.ascontiguousarray(arr[:, :, :3])

    def monitors(self) -> list[Rect]:
        return [Rect(m["left"], m["top"], m["width"], m["height"]) for m in self._sct().monitors[1:]]


class ImageCapturer:
    """Serves crops of a fixed image placed at ``origin`` on a virtual screen (tests, screenshots)."""

    def __init__(self, image: np.ndarray, origin: tuple[int, int] = (0, 0)) -> None:
        self.image = image
        self.origin = origin
        self.grabs = 0

    def grab(self, rect: Rect) -> np.ndarray:
        self.grabs += 1
        h, w = self.image.shape[:2]
        x0, y0 = rect.x - self.origin[0], rect.y - self.origin[1]
        out = np.zeros((rect.height, rect.width, 3), dtype=np.uint8)
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(w, x0 + rect.width), min(h, y0 + rect.height)
        if sx1 > sx0 and sy1 > sy0:
            out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = self.image[sy0:sy1, sx0:sx1, :3]
        return out
