"""Notification sounds, synthesised in code so no audio files have to be shipped."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 22050

# (frequency Hz, duration s) segments; 0 Hz = silence
SOUNDS: dict[str, list[tuple[float, float]]] = {
    "soft": [(660, 0.12)],
    "chime": [(880, 0.10), (0, 0.03), (1175, 0.16)],
    "alarm": [(988, 0.12), (0, 0.05), (988, 0.12), (0, 0.05), (1319, 0.22)],
}


def synthesize(name: str) -> bytes:
    """Return 16-bit mono PCM samples for ``name`` with short fades to avoid clicks."""
    frames = bytearray()
    for freq, dur in SOUNDS[name]:
        n = int(RATE * dur)
        fade = max(1, int(RATE * 0.01))
        for i in range(n):
            if freq == 0:
                sample = 0.0
            else:
                env = min(1.0, i / fade, (n - i) / fade)
                sample = 0.45 * env * math.sin(2 * math.pi * freq * i / RATE)
            frames += struct.pack("<h", int(sample * 32767))
    return bytes(frames)


def write_sound_files(directory: Path) -> dict[str, Path]:
    """Write every sound as a WAV file (once) and return name -> path."""
    directory.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name in SOUNDS:
        path = directory / f"{name}.wav"
        if not path.exists():
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(synthesize(name))
        out[name] = path
    return out
