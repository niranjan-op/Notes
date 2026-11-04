"""Brand assets and the shared line-icon set for Secure Notes.

Icons are drawn on a 24-unit grid (Lucide-like proportions) with Pillow at a
high resolution and downsampled, so they stay crisp at every Windows display
scaling level. Each icon is cached per (name, size, tone).
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

APP_NAME = "Secure Notes"
APP_VERSION = "1.3.0"   # keep in sync with packaging/installer.iss and packaging/version_info.txt
APP_USER_MODEL_ID = "SecureNotes.Desktop.App"

_GRID = 24
_SUPERSAMPLE = 8          # draw at 192px, store at 64px
_STORE_SIZE = 64
_STROKE = 1.75

# (light-mode colour, dark-mode colour) per tone.
_TONES = {
    "muted": ("#52525B", "#A1A1AA"),
    "faint": ("#A1A1AA", "#6B6B73"),
    "strong": ("#18181B", "#E8E8EB"),
    "primary": ("#4F46E5", "#818CF8"),
    "danger": ("#DC2626", "#F87171"),
    "on_primary": ("#FFFFFF", "#FFFFFF"),
}


def asset_path(name: str) -> Path:
    """Return a bundled asset path in source and packaged builds."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "assets" / name


def logo_image(size: int) -> ctk.CTkImage:
    """Return the Secure Notes brand mark scaled for CustomTkinter."""
    image = Image.open(asset_path("notes.png")).convert("RGBA")
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


class _Pen:
    """Tiny helper that maps 24-grid coordinates to the supersampled canvas."""

    def __init__(self, color: str):
        self.scale = _STORE_SIZE * _SUPERSAMPLE / _GRID
        self.image = Image.new("RGBA", (_STORE_SIZE * _SUPERSAMPLE,) * 2, (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.color = color
        self.width = max(1, round(_STROKE * self.scale))

    def _p(self, points):
        return [(x * self.scale, y * self.scale) for x, y in points]

    def line(self, *points, closed: bool = False) -> None:
        pts = self._p(points)
        if closed:
            pts.append(pts[0])
        self.draw.line(pts, fill=self.color, width=self.width, joint="curve")
        radius = self.width / 2
        for x, y in pts:
            self.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=self.color)

    def circle(self, cx: float, cy: float, r: float, fill: bool = False) -> None:
        box = self._p([(cx - r, cy - r), (cx + r, cy + r)])
        if fill:
            self.draw.ellipse(box, fill=self.color)
        else:
            self.draw.ellipse(box, outline=self.color, width=self.width)

    def rect(self, x0: float, y0: float, x1: float, y1: float, radius: float = 2) -> None:
        self.draw.rounded_rectangle(self._p([(x0, y0), (x1, y1)]), radius=radius * self.scale,
                                    outline=self.color, width=self.width)

    def arc(self, x0: float, y0: float, x1: float, y1: float, start: float, end: float) -> None:
        self.draw.arc(self._p([(x0, y0), (x1, y1)]), start, end, fill=self.color, width=self.width)

    def pie(self, x0: float, y0: float, x1: float, y1: float, start: float, end: float) -> None:
        self.draw.pieslice(self._p([(x0, y0), (x1, y1)]), start, end, fill=self.color)

    def result(self) -> Image.Image:
        return self.image.resize((_STORE_SIZE, _STORE_SIZE), Image.Resampling.LANCZOS)


def _folder(pen: _Pen) -> None:
    pen.line((3, 7), (3, 18), (4, 19), (20, 19), (21, 18), (21, 9), (20, 8),
             (11.5, 8), (9.5, 5.5), (4, 5.5), (3, 6.5), closed=True)


def _page(pen: _Pen) -> None:
    pen.line((14, 3), (6.5, 3), (5.5, 4), (5.5, 20), (6.5, 21), (17.5, 21), (18.5, 20), (18.5, 7.5),
             closed=True)
    pen.line((14, 3), (14, 7.5), (18.5, 7.5))


def _gear(pen: _Pen) -> None:
    points = []
    for tooth in range(8):
        base = math.radians(tooth * 45)
        for offset, radius in ((-15, 6.6), (-9, 9.2), (9, 9.2), (15, 6.6)):
            angle = base + math.radians(offset)
            points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
    pen.line(*points, closed=True)
    pen.circle(12, 12, 2.8)


def _draw(name: str, color: str) -> Image.Image:
    pen = _Pen(color)
    if name == "chevron_right":
        pen.line((9.5, 6), (15.5, 12), (9.5, 18))
    elif name == "chevron_down":
        pen.line((6, 9.5), (12, 15.5), (18, 9.5))
    elif name == "folder":
        _folder(pen)
    elif name == "folder_plus":
        _folder(pen)
        pen.line((12, 11), (12, 16.5))
        pen.line((9.25, 13.75), (14.75, 13.75))
    elif name == "note":
        _page(pen)
        pen.line((9, 12.5), (15, 12.5))
        pen.line((9, 16.5), (13.5, 16.5))
    elif name == "note_plus":
        _page(pen)
        pen.line((12, 11), (12, 17.5))
        pen.line((8.75, 14.25), (15.25, 14.25))
    elif name == "plus":
        pen.line((12, 5), (12, 19))
        pen.line((5, 12), (19, 12))
    elif name == "search":
        pen.circle(10.5, 10.5, 6.5)
        pen.line((15.5, 15.5), (20, 20))
    elif name == "settings":
        _gear(pen)
    elif name == "trash":
        pen.line((4, 6.5), (20, 6.5))
        pen.line((9, 6.5), (9, 4.5), (10, 3.5), (14, 3.5), (15, 4.5), (15, 6.5))
        pen.line((6, 6.5), (7, 19.5), (8, 20.5), (16, 20.5), (17, 19.5), (18, 6.5))
        pen.line((10, 10.5), (10, 16.5))
        pen.line((14, 10.5), (14, 16.5))
    elif name == "lock":
        pen.rect(4.5, 10.5, 19.5, 21, radius=2.2)
        pen.line((8, 10.5), (8, 7.5))
        pen.line((16, 10.5), (16, 7.5))
        pen.arc(8, 3.5, 16, 11.5, 180, 360)
        pen.circle(12, 15.75, 1.1, fill=True)
    elif name == "eye":
        pen.arc(2, 5, 22, 25, 205, 335)
        pen.arc(2, -1, 22, 19, 25, 155)
        pen.circle(12, 12, 3)
    elif name == "eye_off":
        pen.arc(2, 5, 22, 25, 205, 335)
        pen.arc(2, -1, 22, 19, 25, 155)
        pen.circle(12, 12, 3)
        pen.line((4, 4), (20, 20))
    elif name == "arrow_left":
        pen.line((19, 12), (5, 12))
        pen.line((11, 6), (5, 12), (11, 18))
    elif name == "panel_right":
        pen.rect(3, 4, 21, 20, radius=2.5)
        pen.line((15, 4.5), (15, 19.5))
    elif name == "book":
        pen.line((12, 6.5), (12, 19.5))
        pen.line((12, 6.5), (9.5, 5), (4, 5), (3, 6), (3, 18), (4, 19), (9.5, 19), (12, 20))
        pen.line((12, 6.5), (14.5, 5), (20, 5), (21, 6), (21, 18), (20, 19), (14.5, 19), (12, 20))
    elif name == "edit":
        pen.line((16.5, 3.5), (20.5, 7.5), (8, 20), (3.5, 20.5), (4, 16), closed=True)
        pen.line((14, 6), (18, 10))
    elif name == "theme":
        pen.circle(12, 12, 8.5)
        pen.pie(3.5, 3.5, 20.5, 20.5, 90, 270)
    elif name == "import":
        pen.line((4, 15), (4, 19), (5, 20), (19, 20), (20, 19), (20, 15))
        pen.line((12, 4), (12, 15))
        pen.line((7.5, 10.5), (12, 15), (16.5, 10.5))
    elif name == "export":
        pen.line((4, 15), (4, 19), (5, 20), (19, 20), (20, 19), (20, 15))
        pen.line((12, 15), (12, 4))
        pen.line((7.5, 8.5), (12, 4), (16.5, 8.5))
    elif name == "close":
        pen.line((6, 6), (18, 18))
        pen.line((18, 6), (6, 18))
    else:
        raise ValueError(f"Unknown icon: {name}")
    return pen.result()


@lru_cache(maxsize=256)
def icon_image(name: str, size: int = 18, tone: str = "muted") -> ctk.CTkImage:
    """Return a cached, theme-aware line icon."""
    light, dark = _TONES[tone]
    return ctk.CTkImage(light_image=_draw(name, light), dark_image=_draw(name, dark), size=(size, size))
