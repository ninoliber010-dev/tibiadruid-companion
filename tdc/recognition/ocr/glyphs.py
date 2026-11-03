"""Glyph-template OCR for Tibia's pixel font.

Generic OCR engines struggle with small, un-smoothed pixel fonts. Pixel fonts, however, draw
every character identically each time, so exact template matching works well once the
templates are known. Templates are learned from the user's own screenshots ("teach": select a
name strip, type what it says).

Pipeline: text mask (bright pixels) -> split into glyphs at empty columns -> match each glyph
against the library (Hamming distance on same-size bitmaps) -> text + confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SPACE_GAP = 3        # empty columns between glyphs that count as a space


@dataclass(frozen=True)
class Glyph:
    bits: np.ndarray     # bool array, shape (h, w)
    x: int               # left column in the strip
    gap_before: int      # empty columns before this glyph

    @property
    def key(self) -> str:
        return glyph_key(self.bits)


def glyph_key(bits: np.ndarray) -> str:
    h, w = bits.shape
    return f"{w}x{h}:" + np.packbits(bits.astype(np.uint8).ravel()).tobytes().hex()


def bits_from_key(key: str) -> np.ndarray:
    size, hexdata = key.split(":", 1)
    w, h = (int(v) for v in size.split("x"))
    flat = np.unpackbits(np.frombuffer(bytes.fromhex(hexdata), dtype=np.uint8))[: w * h]
    return flat.reshape(h, w).astype(bool)


def text_mask(img_bgr: np.ndarray, threshold: int = 140) -> np.ndarray:
    """Bright pixels = text. Tibia draws names in light colours on dark backgrounds."""
    return img_bgr.max(axis=2) >= threshold


def segment(mask: np.ndarray, space_gap: int = SPACE_GAP) -> list[Glyph]:
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) == 0:
        return []
    top, bottom = rows[0], rows[-1] + 1
    line = mask[top:bottom]
    cols = line.any(axis=0)
    glyphs: list[Glyph] = []
    x, w = 0, line.shape[1]
    last_end = None
    while x < w:
        if not cols[x]:
            x += 1
            continue
        start = x
        while x < w and cols[x]:
            x += 1
        gap = 0 if last_end is None else start - last_end
        glyphs.append(Glyph(line[:, start:x].copy(), start, gap))
        last_end = x
    return glyphs


@dataclass
class GlyphLibrary:
    templates: dict[str, str] = field(default_factory=dict)   # glyph key -> character(s)

    def __len__(self) -> int:
        return len(self.templates)

    def learn(self, img_bgr: np.ndarray, text: str, threshold: int = 140) -> dict[str, str]:
        """Learn glyphs from a strip whose content is ``text``. Returns the new templates.

        Raises ValueError if the number of glyphs does not match the text (e.g. touching letters).
        """
        glyphs = segment(text_mask(img_bgr, threshold))
        chars = [c for c in text if not c.isspace()]
        if not glyphs:
            raise ValueError("No text found in the selected area.")
        if len(glyphs) != len(chars):
            raise ValueError(f"Found {len(glyphs)} characters in the image but the text has {len(chars)}.")
        new = {}
        for g, c in zip(glyphs, chars):
            if self.templates.get(g.key) != c:
                new[g.key] = c
        self.templates.update(new)
        return new

    def _match(self, bits: np.ndarray) -> tuple[str | None, float]:
        key = glyph_key(bits)
        if key in self.templates:
            return self.templates[key], 1.0
        h, w = bits.shape
        best, best_score = None, 0.0
        for k, ch in self.templates.items():
            tb = bits_from_key(k)
            th, tw = tb.shape
            if abs(tw - w) > 1 or abs(th - h) > 1:
                continue
            H, W = max(h, th), max(w, tw)
            a = np.zeros((H, W), bool)
            b = np.zeros((H, W), bool)
            a[:h, :w] = bits
            b[:th, :tw] = tb
            union = (a | b).sum()
            score = 1.0 - (a ^ b).sum() / max(1, union)
            if score > best_score:
                best, best_score = ch, score
        return best, best_score

    def read(self, img_bgr: np.ndarray, threshold: int = 140, space_gap: int = SPACE_GAP,
             min_glyph_score: float = 0.8) -> tuple[str, float]:
        """Return (text, confidence). Unknown glyphs become '?' and lower the confidence."""
        glyphs = segment(text_mask(img_bgr, threshold), space_gap)
        if not glyphs:
            return "", 0.0
        out, scores = [], []
        for g in glyphs:
            if out and g.gap_before >= space_gap:
                out.append(" ")
            ch, score = self._match(g.bits)
            if ch is None or score < min_glyph_score:
                out.append("?")
                scores.append(0.0)
            else:
                out.append(ch)
                scores.append(score)
        return "".join(out), float(np.mean(scores))
