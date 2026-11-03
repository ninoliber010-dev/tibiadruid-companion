"""Region geometry: where a calibrated region is when the Tibia window moves or is resized.

Regions are stored in physical pixels relative to the Tibia *client area*, together with the
client size at calibration time. Tibia's interface panels stick to the window edges (side bars
to the left/right, the bottom panel to the bottom), so when the window is resized each region
keeps its distance to the edge it was nearest to at calibration time.
"""

from __future__ import annotations

from dataclasses import dataclass

from tdc.storage.repositories import Region


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def translated(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def intersects(self, other: "Rect") -> bool:
        return not (self.right <= other.x or other.right <= self.x or
                    self.bottom <= other.y or other.bottom <= self.y)

    def contains(self, other: "Rect") -> bool:
        return (self.x <= other.x and self.y <= other.y and
                other.right <= self.right and other.bottom <= self.bottom)


@dataclass(frozen=True)
class ResolvedRegion:
    rect: Rect            # relative to the client area, in the current client size
    moved: bool           # True when the client size differs from calibration
    inside: bool          # False when the region falls (partly) outside the client area


def anchors(region: Region) -> tuple[str, str]:
    """('left'|'right', 'top'|'bottom') — the window edges the region is closest to."""
    if region.ref_width <= 0 or region.ref_height <= 0:
        return "left", "top"
    cx = region.x + region.width / 2
    cy = region.y + region.height / 2
    return ("right" if cx > region.ref_width / 2 else "left",
            "bottom" if cy > region.ref_height / 2 else "top")


def resolve(region: Region, client_width: int, client_height: int) -> ResolvedRegion:
    x, y = region.x, region.y
    moved = False
    if region.ref_width > 0 and region.ref_height > 0 and (
            client_width != region.ref_width or client_height != region.ref_height):
        moved = True
        ax, ay = anchors(region)
        if ax == "right":
            x = client_width - (region.ref_width - region.x)
        if ay == "bottom":
            y = client_height - (region.ref_height - region.y)
    rect = Rect(x, y, region.width, region.height)
    inside = Rect(0, 0, client_width, client_height).contains(rect)
    return ResolvedRegion(rect, moved, inside)
