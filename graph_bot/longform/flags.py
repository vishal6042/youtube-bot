"""National flags drawn with cairo, to their official constructions, so a map can
show a country filled with its flag. Nothing is downloaded.

``draw(c, name, x, y, h)`` paints the flag itself, top-left corner at (x, y),
``h`` tall (``ASPECT[name]`` is width / height).

``field(c, name, ex, ey, h, w_area, h_area)`` paints the flag's pattern over a
whole area with its emblem (India's Ashoka Chakra, Pakistan's crescent and star,
Bangladesh's red disc) centred on (ex, ey): the bands and fields simply carry on
past the flag's edges, so it can fill a country's shape whatever its size.

Pakistan (Pakistan Standard 1700): 2:3, white hoist bar 1/4 of the length. On the
green field's diagonal (top right to bottom left): A, its centre; B, 13/20 of the
height from the top-right corner. Crescent = the circle about A, radius 3/10 of the
height, less the circle about B, radius 11/40. Star: circumscribed radius 1/10 of
the height, on the diagonal inside the opening, its outer point where the outer
circle cuts the diagonal.
"""
from __future__ import annotations

import math

import cairo

ASPECT = {"India": 3 / 2, "Pakistan": 3 / 2, "Bangladesh": 5 / 3}
SAFFRON, WHITE, IN_GREEN, NAVY = "#FF671F", "#FFFFFF", "#046A38", "#06038D"
PK_GREEN = "#01411C"
BD_GREEN, BD_RED = "#006A4E", "#F42A41"


def _rgb(hexs: str) -> tuple[float, float, float]:
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rect(c: cairo.Context, x0: float, y0: float, x1: float, y1: float, col: str) -> None:
    c.rectangle(x0, y0, x1 - x0, y1 - y0)
    c.set_source_rgb(*_rgb(col))
    c.fill()


def _chakra(c: cairo.Context, cx: float, cy: float, r: float) -> None:
    """The Ashoka Chakra: a navy wheel of 24 spokes."""
    c.set_source_rgb(*_rgb(NAVY))
    c.set_line_width(r * 0.09)
    c.arc(cx, cy, r * 0.955, 0, 2 * math.pi)
    c.stroke()
    c.arc(cx, cy, r * 0.17, 0, 2 * math.pi)
    c.fill()
    c.set_line_width(r * 0.045)
    for k in range(24):
        a = 2 * math.pi * k / 24
        c.move_to(cx + math.cos(a) * r * 0.17, cy + math.sin(a) * r * 0.17)
        c.line_to(cx + math.cos(a) * r * 0.92, cy + math.sin(a) * r * 0.92)
        c.stroke()


def _star(c: cairo.Context, cx: float, cy: float, r: float, rot: float) -> None:
    ri = r * 0.382
    for k in range(10):
        a = rot + math.pi * k / 5
        rr = r if k % 2 == 0 else ri
        (c.move_to if k == 0 else c.line_to)(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
    c.close_path()


def _pk_diag(h: float) -> tuple[float, float]:
    """Unit vector along the green field's diagonal, towards its top right."""
    gw = h * ASPECT["Pakistan"] * 0.75
    n = math.hypot(gw, h)
    return gw / n, -h / n


def _crescent_star(c: cairo.Context, ax: float, ay: float, h: float) -> None:
    ux, uy = _pk_diag(h)
    gw = h * ASPECT["Pakistan"] * 0.75
    half_diag = math.hypot(gw, h) / 2
    ab = half_diag - 13 / 20 * h               # A to B, towards the top right
    # outer disc in white, then the inner disc cut back out in the field's green
    c.new_path()
    c.arc(ax, ay, 3 / 10 * h, 0, 2 * math.pi)
    c.set_source_rgb(1, 1, 1)
    c.fill()
    c.arc(ax + ux * ab, ay + uy * ab, 11 / 40 * h, 0, 2 * math.pi)
    c.set_source_rgb(*_rgb(PK_GREEN))
    c.fill()
    # the star sits in the crescent's opening, its outer point on the outer circle
    r_s = h / 10
    d = 3 / 10 * h - r_s
    c.set_source_rgb(1, 1, 1)
    _star(c, ax + ux * d, ay + uy * d, r_s, math.atan2(uy, ux))
    c.fill()


# --------------------------------------------------------------------------- #
# the flags themselves
# --------------------------------------------------------------------------- #
def draw(c: cairo.Context, name: str, x: float, y: float, h: float) -> None:
    w = h * ASPECT[name]
    c.save()
    c.rectangle(x, y, w, h)
    c.clip()
    if name == "India":
        ex, ey = x + w / 2, y + h / 2
    elif name == "Pakistan":
        ex, ey = emblem_of_flag("Pakistan", x, y, h)
    else:
        ex, ey = x + w * 0.45, y + h / 2
    field(c, name, ex, ey, h, x + w + 10, y + h + 10, x0=x)
    c.restore()


def emblem_of_flag(name: str, x: float, y: float, h: float) -> tuple[float, float]:
    """Where field() puts the emblem centre, for a flag drawn at (x, y), h tall."""
    w = h * ASPECT[name]
    if name == "Pakistan":
        ax, ay = x + w / 4 + w * 0.375, y + h / 2
        ux, uy = _pk_diag(h)
        return ax + ux * EMBLEM_SHIFT * h, ay + uy * EMBLEM_SHIFT * h
    if name == "Bangladesh":
        return x + w * 0.45, y + h / 2
    return x + w / 2, y + h / 2


# Pakistan's crescent and star both lie within the outer circle about A, so the
# emblem is centred on A itself.
EMBLEM_SHIFT = 0.0

# how far the emblem reaches from its centre, as a share of the flag's height
EMBLEM_R = {"India": 0.15, "Pakistan": 0.30, "Bangladesh": 1 / 3}


# --------------------------------------------------------------------------- #
# the pattern over a whole area, emblem at (ex, ey)
# --------------------------------------------------------------------------- #
def field(c: cairo.Context, name: str, ex: float, ey: float, h: float, w_area: float, h_area: float,
          x0: float = -1e5) -> None:
    big = 1e5
    if name == "India":
        b = h / 3
        _rect(c, -big, -big, big, ey - b / 2 + 0.5, SAFFRON)
        _rect(c, -big, ey - b / 2, big, ey + b / 2 + 0.5, WHITE)
        _rect(c, -big, ey + b / 2, big, big, IN_GREEN)
        _chakra(c, ex, ey, b * 0.45)
    elif name == "Pakistan":
        ux, uy = _pk_diag(h)
        ax, ay = ex - ux * EMBLEM_SHIFT * h, ey - uy * EMBLEM_SHIFT * h
        gw = h * ASPECT["Pakistan"] * 0.75
        green_left = ax - gw / 2
        _rect(c, -big, -big, big, big, PK_GREEN)
        _rect(c, max(-big, x0 if x0 > -big else -big), -big, green_left + 0.5, big, WHITE)
        _crescent_star(c, ax, ay, h)
    else:
        _rect(c, -big, -big, big, big, BD_GREEN)
        w = h * ASPECT["Bangladesh"]
        c.arc(ex, ey, w / 5, 0, 2 * math.pi)
        c.set_source_rgb(*_rgb(BD_RED))
        c.fill()
