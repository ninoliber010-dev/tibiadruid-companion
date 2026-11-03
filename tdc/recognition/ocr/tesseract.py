"""Optional Tesseract backend (external executable, called via subprocess)."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np


class TesseractOcr:
    def __init__(self, executable: str = "") -> None:
        self.executable = executable or shutil.which("tesseract") or ""

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def read(self, img_bgr: np.ndarray) -> tuple[str, float]:
        if not self.available:
            return "", 0.0
        big = cv2.resize(img_bgr, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ok, png = cv2.imencode(".png", bw)
        if not ok:
            return "", 0.0
        try:
            res = subprocess.run([self.executable, "stdin", "stdout", "--psm", "7"], input=png.tobytes(),
                                 capture_output=True, timeout=2,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            return "", 0.0
        text = res.stdout.decode("utf-8", "ignore").strip()
        # Tesseract gives no reliable per-line confidence here; the name matcher supplies it.
        return text, 0.7 if text else 0.0
