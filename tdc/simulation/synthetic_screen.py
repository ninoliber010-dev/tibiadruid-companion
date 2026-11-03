"""Synthetic Tibia-like client screenshots with known ground truth.

Used by the automated tests and by the "Load demo screenshot" button on the Visual Recognition
page (so calibration can be tried without Tibia). It imitates the *structure* of the client —
coloured status bars, a battle list and a party list with bordered health bars and pixel-font
names — not its exact artwork. Real screenshots differ; that is what calibration is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from tdc.recognition.geometry import Rect

FONT = cv2.FONT_HERSHEY_PLAIN
FONT_SCALE = 0.75
NAME_COLOR = (192, 192, 192)      # BGR
HEALTH_FILL = (40, 40, 200)       # red (BGR)
MANA_FILL = (205, 95, 40)         # blue (BGR)
TRACK = (28, 28, 28)
PANEL = (58, 58, 58)
LIST_BG = (50, 50, 50)


@dataclass
class Entry:
    name: str
    health: float
    targeted: bool = False


@dataclass
class Scene:
    width: int = 1280
    height: int = 800
    health: float = 100.0
    mana: float = 100.0
    creatures: list[Entry] = field(default_factory=list)
    party: list[Entry] = field(default_factory=list)
    noise: float = 0.0                 # gaussian sigma (0-255 scale)
    bar_text: bool = False             # draw "1234 / 2000" over the status bars
    occlude: Rect | None = None        # white window over this rect
    seed: int = 1


@dataclass
class Truth:
    regions: dict[str, Rect]           # region kind -> rect in client coordinates
    bar_inner: dict[str, Rect]         # exact fill area of the status bars


def char_bitmap(ch: str) -> np.ndarray:
    """Render one character crisply (no anti-aliasing) and crop it — our stand-in pixel font."""
    canvas = np.zeros((16, 14), np.uint8)
    cv2.putText(canvas, ch, (1, 12), FONT, FONT_SCALE, 255, 1, cv2.LINE_8)
    ys, xs = np.nonzero(canvas)
    if len(xs) == 0:
        return np.zeros((16, 3), bool)
    return canvas[:, xs.min():xs.max() + 1] > 0


def draw_text(img: np.ndarray, text: str, x: int, y: int, color=NAME_COLOR) -> int:
    """Draw ``text`` with its top at ``y``; 1 px between glyphs, 4 px for spaces. Returns end x."""
    for ch in text:
        if ch == " ":
            x += 4
            continue
        bm = char_bitmap(ch)
        h, w = bm.shape
        sub = img[y - 2:y - 2 + h, x:x + w]
        mh, mw = sub.shape[:2]
        sub[bm[:mh, :mw]] = color
        x += w + 1
    return x


def _bar(img, x, y, w, h, frac, fill, track=TRACK, border=(0, 0, 0)) -> Rect:
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), border, 1)
    inner = Rect(x + 1, y + 1, w - 2, h - 2)
    img[inner.y:inner.bottom, inner.x:inner.right] = track
    fw = int(round(inner.width * max(0.0, min(1.0, frac))))
    if fw:
        img[inner.y:inner.bottom, inner.x:inner.x + fw] = fill
    return inner


def creature_bar_color(hp: float) -> tuple[int, int, int]:
    return (0, 192, 0) if hp > 60 else (0, 192, 192) if hp > 30 else (0, 0, 192)


def _list(img, x0, y0, w, h, entries: list[Entry]) -> Rect:
    img[y0:y0 + h, x0:x0 + w] = LIST_BG
    for i, e in enumerate(entries):
        y = y0 + 4 + i * 24
        if y + 22 > y0 + h:
            break
        icon_col = (60 + 37 * i % 150, 90, 120)
        cv2.rectangle(img, (x0 + 4, y), (x0 + 23, y + 19), icon_col, -1)
        if e.targeted:
            cv2.rectangle(img, (x0 + 2, y - 2), (x0 + 25, y + 21), (0, 0, 255), 1)
        draw_text(img, e.name, x0 + 30, y + 1)
        _bar(img, x0 + 30, y + 14, 120, 6, e.health / 100.0, creature_bar_color(e.health), track=(0, 0, 0))
    return Rect(x0, y0, w, h)


def render(scene: Scene) -> tuple[np.ndarray, Truth]:
    rng = np.random.default_rng(scene.seed)
    img = np.zeros((scene.height, scene.width, 3), np.uint8)
    # Game view: muted textured ground.
    img[:] = (52, 84, 70)
    tex = rng.integers(-12, 12, size=(scene.height // 8 + 1, scene.width // 8 + 1, 1))
    img[:] = np.clip(img.astype(int) + np.kron(tex, np.ones((8, 8, 1), int))[:scene.height, :scene.width], 0, 255)

    sx = scene.width - 180
    img[:, sx:] = PANEL
    regions: dict[str, Rect] = {}
    inner: dict[str, Rect] = {}
    inner["health"] = _bar(img, sx + 10, 16, 160, 11, scene.health / 100.0, HEALTH_FILL)
    inner["mana"] = _bar(img, sx + 10, 34, 160, 11, scene.mana / 100.0, MANA_FILL)
    if scene.bar_text:
        for kind, val in (("health", scene.health), ("mana", scene.mana)):
            r = inner[kind]
            draw_text(img, f"{int(val * 24)} / 2400", r.x + 46, r.y, (235, 235, 235))
    # Regions as a user would draw them: a little margin around each bar.
    regions["health"] = Rect(sx + 6, 13, 168, 17)
    regions["mana"] = Rect(sx + 6, 31, 168, 17)
    regions["battle_list"] = _list(img, sx + 4, 80, 172, 260, scene.creatures)
    regions["party"] = _list(img, sx + 4, 360, 172, 110, scene.party)

    if scene.noise > 0:
        img = np.clip(img.astype(np.float32) + rng.normal(0, scene.noise, img.shape), 0, 255).astype(np.uint8)
    if scene.occlude is not None:
        o = scene.occlude
        img[o.y:o.bottom, o.x:o.right] = (240, 240, 240)
    return img, Truth(regions, inner)


def crop(img: np.ndarray, r: Rect) -> np.ndarray:
    return img[r.y:r.bottom, r.x:r.right].copy()


def demo_scene() -> Scene:
    return Scene(
        health=72, mana=46,
        creatures=[Entry("Dragon Lord", 85, targeted=True), Entry("Dragon", 40), Entry("Hydra", 100),
                   Entry("Frost Dragon", 12)],
        party=[Entry("Knight Partner", 64)],
    )
