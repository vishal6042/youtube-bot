"""Shared drawing kit for the animated long-form scenes (hook.py, podium.py).

Everything is drawn here rather than borrowed from stock art, so it can move:
a dotted globe with India lit up, metallic numerals, laurel wreaths, neon line
icons (Lucide), glowing arcs, and the closing line that lights word by word.
Sprites are RGBA PIL images, built once and composited per frame.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import PROJECT_ROOT

W, H, FPS = 1920, 1080, 30
ASSETS = PROJECT_ROOT / "assets"
CACHE = PROJECT_ROOT / "data" / "cache"

SAFFRON = (255, 153, 51)
GOLD_TXT = (255, 214, 90)
FG = (244, 246, 252)
MUTED = (160, 172, 192)

# Vertical metal ramps: highlight, body, shadow band, reflection, base.
METALS = {
    "gold": [(255, 248, 205), (255, 214, 92), (205, 140, 28), (255, 228, 135), (150, 92, 12)],
    "silver": [(255, 255, 255), (214, 222, 234), (140, 150, 168), (236, 241, 250), (96, 104, 120)],
    "bronze": [(255, 222, 186), (236, 152, 86), (165, 86, 38), (244, 176, 116), (110, 52, 20)],
    "red": [(255, 214, 214), (255, 96, 96), (200, 28, 40), (255, 130, 130), (120, 12, 20)],
    "teal": [(214, 255, 248), (94, 230, 205), (28, 150, 130), (150, 245, 226), (12, 86, 76)],
    "saffron": [(255, 236, 200), (255, 170, 70), (220, 110, 20), (255, 190, 110), (150, 64, 6)],
    "saffron_bright": [(255, 246, 214), (255, 190, 72), (255, 128, 20), (255, 212, 120), (196, 88, 8)],
}
TONE_RGB = {"gold": (255, 200, 60), "silver": (205, 215, 230), "bronze": (230, 145, 80),
            "red": (255, 70, 80), "teal": (70, 225, 205), "saffron": SAFFRON, "saffron_bright": (255, 160, 40)}


# --------------------------------------------------------------------------- #
# Basics
# --------------------------------------------------------------------------- #
_FONT_FILES = {
    "black": ["seguibl.ttf", "ariblk.ttf"],
    "bold": ["segoeuib.ttf", "arialbd.ttf"],
    "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf"],
}


@lru_cache(maxsize=256)
def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    for name in _FONT_FILES.get(weight, _FONT_FILES["bold"]):
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            return ImageFont.truetype(str(p), int(size))
    from ..sims.canvas import font as dejavu

    return dejavu(int(size), bold=weight != "regular")


def clamp(u: float) -> float:
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_out(u: float) -> float:
    return 1 - (1 - clamp(u)) ** 3


def ease_in_out(u: float) -> float:
    u = clamp(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def ease_back(u: float, s: float = 1.9) -> float:
    u = clamp(u) - 1
    return u * u * ((s + 1) * u + s) + 1


def with_alpha(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def paste(canvas: Image.Image, spr: Image.Image, x: float, y: float, a: float = 1.0, s: float = 1.0,
          anchor: str = "mm") -> None:
    """Composite ``spr`` at (x, y) (its centre by default), faded and scaled."""
    if a <= 0.003 or spr is None:
        return
    if abs(s - 1) > 0.004:
        spr = spr.resize((max(1, int(spr.width * s)), max(1, int(spr.height * s))), Image.BICUBIC)
    spr = with_alpha(spr, a)
    ox = {"l": 0, "m": spr.width / 2, "r": spr.width}[anchor[0]]
    oy = {"t": 0, "m": spr.height / 2, "b": spr.height}[anchor[1]]
    canvas.alpha_composite(spr, (int(round(x - ox)), int(round(y - oy))))


def glow(img: Image.Image, radius: float, strength: float = 1.0, tint=None) -> Image.Image:
    """``img`` over a blurred copy of itself (optionally recoloured)."""
    pad = int(radius * 2.5)
    base = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    base.alpha_composite(img, (pad, pad))
    halo = base if tint is None else Image.new("RGBA", base.size, (*tint, 0))
    if tint is not None:
        halo.putalpha(base.getchannel("A"))
    halo = halo.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1:
        halo.putalpha(halo.getchannel("A").point(lambda v: min(255, int(v * strength))))
    halo.alpha_composite(base)
    return halo


def surface_to_image(surf: cairo.ImageSurface) -> Image.Image:
    """Cairo's premultiplied BGRA to a straight-alpha PIL RGBA image."""
    w, h = surf.get_width(), surf.get_height()
    buf = np.frombuffer(surf.get_data(), np.uint8).reshape(h, surf.get_stride() // 4, 4)[:, :w]
    a = buf[..., 3:4].astype(np.float32)
    rgb = np.where(a > 0, buf[..., [2, 1, 0]].astype(np.float32) * 255 / np.maximum(a, 1), 0)
    out = np.concatenate([np.clip(rgb, 0, 255), a], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def canvas_surface(w: int, h: int) -> tuple[cairo.ImageSurface, cairo.Context]:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h))
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    return surf, ctx


def _ramp(stops: list[tuple[int, int, int]], n: int) -> np.ndarray:
    pos = np.linspace(0, 1, len(stops))
    t = np.linspace(0, 1, n)
    arr = np.array(stops, np.float32)
    return np.stack([np.interp(t, pos, arr[:, c]) for c in range(3)], axis=1)


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def text(s: str, size: int, colour=FG, weight: str = "bold", glow_r: float = 0.0,
         glow_a: float = 0.8, shadow: bool = True) -> Image.Image:
    """Plain text on a sprite sized from font metrics (shared baseline per size)."""
    f = font(size, weight)
    asc, desc = f.getmetrics()
    pad = max(8, size // 3)
    adv = int(math.ceil(f.getlength(s)))
    img = Image.new("RGBA", (adv + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad, pad + asc), s, font=f, fill=colour, anchor="ls")
    if glow_r:
        img = glow(img, glow_r, glow_a, tint=colour[:3] if isinstance(colour, tuple) else None)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(img.getchannel("A").point(lambda v: int(v * 0.6)))
        sh = sh.filter(ImageFilter.GaussianBlur(max(2, size // 14)))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 0))
        out = out.transform(out.size, Image.AFFINE, (1, 0, -size * 0.03, 0, 1, -size * 0.05))
        out.alpha_composite(img)
        img = out
    return img


def metal_text(s: str, size: int, tone: str = "gold", weight: str = "black",
               glow_r: float | None = None) -> Image.Image:
    """Bevelled metallic lettering: gradient fill, lit edges, dark rim, glow."""
    f = font(size, weight)
    asc, desc = f.getmetrics()
    pad = int(size * 0.35)
    adv = int(math.ceil(f.getlength(s)))
    w, h = adv + pad * 2, asc + desc + pad * 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad, pad + asc), s, font=f, fill=255, anchor="ls")
    rim = Image.new("L", (w, h), 0)
    ImageDraw.Draw(rim).text((pad, pad + asc), s, font=f, fill=255, anchor="ls",
                             stroke_width=max(2, size // 34))
    bbox = mask.getbbox() or (0, 0, w, h)
    ramp = _ramp(METALS.get(tone, METALS["gold"]), bbox[3] - bbox[1])
    col = np.zeros((h, w, 3), np.float32)
    col[bbox[1]:bbox[3]] = ramp[:, None, :]
    col[:bbox[1]] = ramp[0]
    col[bbox[3]:] = ramp[-1]
    # Bevel: light from the top left, read off the slope of a blurred mask.
    m = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(1.5, size / 40))), np.float32) / 255
    gy, gx = np.gradient(m)
    shade = np.clip(-(gx * 0.7 + gy * 1.0) * size * 0.9, -1, 1)
    col = np.where(shade[..., None] > 0, col + (255 - col) * shade[..., None] * 0.75,
                   col * (1 + shade[..., None] * 0.55))
    a = np.asarray(mask, np.float32)
    fill = Image.fromarray(np.dstack([np.clip(col, 0, 255), a]).astype(np.uint8), "RGBA")
    dark = tuple(int(c * 0.35) for c in METALS.get(tone, METALS["gold"])[-1])
    out = Image.new("RGBA", (w, h), (*dark, 0))
    out.putalpha(rim)
    out.alpha_composite(fill)
    # Drop shadow and the tone's glow.
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(rim.point(lambda v: int(v * 0.7)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(size / 18))
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    base.alpha_composite(shadow, (int(size * 0.03), int(size * 0.06)))
    base.alpha_composite(out)
    return glow(base, glow_r if glow_r is not None else size / 9, 0.55, tint=TONE_RGB.get(tone))


def shine(sprite: Image.Image, u: float, width: float = 0.18) -> Image.Image:
    """A diagonal band of light crossing ``sprite`` (u from 0 to 1)."""
    if u <= 0 or u >= 1:
        return sprite
    w, h = sprite.size
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    pos = (x / w + y / h * 0.45) / 1.45
    band = np.exp(-((pos - (-0.2 + 1.4 * u)) / width) ** 2)
    arr = np.asarray(sprite).astype(np.float32)
    lift = band[..., None] * 0.75 * (arr[..., 3:4] / 255)
    arr[..., :3] = arr[..., :3] + (255 - arr[..., :3]) * lift
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# --------------------------------------------------------------------------- #
# Icons (Lucide line icons, drawn with cairo)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=64)
def _icon_paths(name: str):
    from svgelements import (SVG, Arc, Close, CubicBezier, Line, Move, Path as SPath,
                             QuadraticBezier, Shape)

    svg = SVG.parse(str(ASSETS / "icons" / "lucide" / f"{name}.svg"))
    out = []
    for el in svg.elements():
        if not isinstance(el, Shape) or isinstance(el, SVG):
            continue
        segs = []
        for seg in SPath(el):
            if isinstance(seg, Move):
                segs.append(("M", seg.end.x, seg.end.y))
            elif isinstance(seg, Line):
                segs.append(("L", seg.end.x, seg.end.y))
            elif isinstance(seg, Close):
                segs.append(("Z",))
            elif isinstance(seg, CubicBezier):
                segs.append(("C", seg.control1.x, seg.control1.y, seg.control2.x, seg.control2.y,
                             seg.end.x, seg.end.y))
            elif isinstance(seg, QuadraticBezier):
                s0, c, e = seg.start, seg.control, seg.end
                segs.append(("C", s0.x + 2 / 3 * (c.x - s0.x), s0.y + 2 / 3 * (c.y - s0.y),
                             e.x + 2 / 3 * (c.x - e.x), e.y + 2 / 3 * (c.y - e.y), e.x, e.y))
            elif isinstance(seg, Arc):
                for cub in seg.as_cubic_curves():
                    segs.append(("C", cub.control1.x, cub.control1.y, cub.control2.x, cub.control2.y,
                                 cub.end.x, cub.end.y))
        out.append(segs)
    return out


def icon(name: str, size: int, tone: str = "gold", stroke: float = 2.0, glow_r: float | None = None,
         fill_alpha: float = 0.22) -> Image.Image:
    """A Lucide icon as glowing neon: gradient stroke, faint tinted fill."""
    pad = int(size * 0.25)
    S = 2
    surf, ctx = canvas_surface((size + pad * 2) * S, (size + pad * 2) * S)
    ctx.translate(pad * S, pad * S)
    ctx.scale(size * S / 24, size * S / 24)
    ramp = METALS.get(tone, METALS["gold"])
    grad = cairo.LinearGradient(0, 0, 0, 24)
    for p, c in zip((0, 0.45, 1), (ramp[0], ramp[1], ramp[2])):
        grad.add_color_stop_rgb(p, *(v / 255 for v in c))
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for segs in _icon_paths(name):
        ctx.new_path()
        for s in segs:
            if s[0] == "M":
                ctx.move_to(s[1], s[2])
            elif s[0] == "L":
                ctx.line_to(s[1], s[2])
            elif s[0] == "C":
                ctx.curve_to(*s[1:])
            else:
                ctx.close_path()
        r, g, b = (v / 255 for v in TONE_RGB.get(tone, (255, 255, 255)))
        ctx.set_source_rgba(r, g, b, fill_alpha)
        ctx.fill_preserve()
        ctx.set_source(grad)
        ctx.set_line_width(stroke)
        ctx.stroke()
    img = surface_to_image(surf).resize((size + pad * 2, size + pad * 2), Image.LANCZOS)
    return glow(img, glow_r if glow_r is not None else size / 10, 0.9, tint=TONE_RGB.get(tone))


# --------------------------------------------------------------------------- #
# Laurel wreath
# --------------------------------------------------------------------------- #
def laurel(height: int, tone: str, side: int, leaves: int, total: int = 10) -> Image.Image:
    """One branch (side -1 left, +1 right) curving up; the first ``leaves`` of
    ``total`` leaf pairs are drawn, so the wreath can grow."""
    S = 2
    w = int(height * 0.62)
    surf, ctx = canvas_surface(w * S, height * S)
    ramp = METALS.get(tone, METALS["gold"])
    cx = w * S * (0.98 if side < 0 else 0.02)
    cy = height * S * 0.50
    R = height * S * 0.46
    a0, a1 = (math.pi * 0.52, math.pi * 1.36) if side < 0 else (math.pi * 0.48, -math.pi * 0.36)

    def at(u: float) -> tuple[float, float]:
        a = a0 + (a1 - a0) * u
        return cx + R * math.cos(a), cy + R * math.sin(a)

    frac = leaves / total
    if frac > 0:
        ctx.set_line_width(height * S * 0.03)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        stem = cairo.LinearGradient(0, 0, 0, height * S)
        stem.add_color_stop_rgb(0, *(v / 255 for v in ramp[1]))
        stem.add_color_stop_rgb(1, *(v / 255 for v in ramp[4]))
        ctx.new_path()
        for i in range(41):
            x, y = at(i / 40 * frac)
            ctx.line_to(x, y) if i else ctx.move_to(x, y)
        ctx.set_source(stem)
        ctx.stroke()
    for k in range(leaves):
        u = (k + 0.5) / total
        x, y = at(u)
        x2, y2 = at(u + 0.01)
        heading = math.atan2(x2 - x, -(y2 - y))          # the way the branch grows
        size = height * S * (0.20 - 0.08 * u)
        for flip in (-1, 1):                               # a leaf on each side of the stem
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(heading + flip * 0.62)
            g = cairo.LinearGradient(-size * 0.3, 0, size * 0.3, 0)
            g.add_color_stop_rgb(0, *(v / 255 for v in ramp[0]))
            g.add_color_stop_rgb(0.5, *(v / 255 for v in ramp[1]))
            g.add_color_stop_rgb(1, *(v / 255 for v in ramp[4]))
            ctx.new_path()
            ctx.move_to(0, 0)
            ctx.curve_to(size * 0.40, -size * 0.25, size * 0.38, -size * 0.80, 0, -size * 1.05)
            ctx.curve_to(-size * 0.38, -size * 0.80, -size * 0.40, -size * 0.25, 0, 0)
            ctx.set_source(g)
            ctx.fill()
            ctx.restore()
    img = surface_to_image(surf).resize((w, height), Image.LANCZOS)
    return glow(img, height / 30, 0.6, tint=TONE_RGB.get(tone))


# --------------------------------------------------------------------------- #
# Globe and world map
# --------------------------------------------------------------------------- #
def _world_paths():
    from matplotlib.path import Path as MPath

    data = json.loads((ASSETS / "geo" / "ne_110m_admin_0_countries.geojson").read_text(encoding="utf-8"))
    paths = []
    for f in data["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            paths.append(MPath(np.array(poly[0])))
    return paths


def india_rings() -> list[np.ndarray]:
    data = json.loads((ASSETS / "geo" / "india_pov.json").read_text(encoding="utf-8"))
    return [np.array(r, np.float64) for r in data["rings"]]


def _in_any(paths, pts: np.ndarray) -> np.ndarray:
    inside = np.zeros(len(pts), bool)
    for p in paths:
        ext = p.get_extents()
        sel = (~inside & (pts[:, 0] >= ext.x0) & (pts[:, 0] <= ext.x1)
               & (pts[:, 1] >= ext.y0) & (pts[:, 1] <= ext.y1))
        if sel.any():
            inside[sel] |= p.contains_points(pts[sel])
    return inside


def land_points(n: int = 26000) -> dict[str, np.ndarray]:
    """Evenly spread points on the sphere, flagged land / India. Cached."""
    path = CACHE / f"globe_points_{n}_v1.npz"
    if path.exists():
        d = np.load(path)
        return {k: d[k] for k in d.files}
    from matplotlib.path import Path as MPath

    i = np.arange(n) + 0.5
    lat = 90 - np.degrees(np.arccos(1 - 2 * i / n))
    lon = (np.degrees(np.pi * (1 + 5 ** 0.5) * i) % 360) - 180
    pts = np.c_[lon, lat]
    land = _in_any(_world_paths(), pts)
    india = _in_any([MPath(r) for r in india_rings()], pts)
    # A finer sprinkle of points inside India for its city lights.
    g = np.mgrid[66:98:0.28, 6:38:0.28].reshape(2, -1).T
    fine = g[_in_any([MPath(r) for r in india_rings()], g)]
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(path, lon=lon, lat=lat, land=land | india, india=india, fine=fine)
    return {"lon": lon, "lat": lat, "land": land | india, "india": india, "fine": fine}


def ortho(lon, lat, lon0: float, lat0: float):
    """Orthographic projection: unit-disc x, y and visibility (cos of the angle)."""
    lam, phi = np.radians(np.asarray(lon) - lon0), np.radians(lat)
    p0 = math.radians(lat0)
    x = np.cos(phi) * np.sin(lam)
    y = math.cos(p0) * np.sin(phi) - math.sin(p0) * np.cos(phi) * np.cos(lam)
    vis = math.sin(p0) * np.sin(phi) + math.cos(p0) * np.cos(phi) * np.cos(lam)
    return x, y, vis


def globe(radius: int, lon0: float = 80.0, lat0: float = 16.0, seed: int = 7) -> dict[str, Any]:
    """The globe as layers: ``base`` (sphere, land dots, lights, India) and
    ``india`` (India's glow alone, to pulse), plus India's centre in sprite
    coordinates."""
    rng = np.random.default_rng(seed)
    pts = land_points()
    margin = int(radius * 0.22)
    size = radius * 2 + margin * 2
    c = size / 2
    S = 1
    surf, ctx = canvas_surface(size, size)

    # Atmosphere halo.
    halo = cairo.RadialGradient(c, c, radius * 0.96, c, c, radius * 1.2)
    halo.add_color_stop_rgba(0, 0.25, 0.55, 1.0, 0.55)
    halo.add_color_stop_rgba(0.35, 0.15, 0.40, 0.95, 0.22)
    halo.add_color_stop_rgba(1, 0.05, 0.10, 0.40, 0.0)
    ctx.arc(c, c, radius * 1.2, 0, 2 * math.pi)
    ctx.set_source(halo)
    ctx.fill()
    # Ocean.
    sea = cairo.RadialGradient(c - radius * 0.35, c - radius * 0.4, radius * 0.1, c, c, radius)
    sea.add_color_stop_rgb(0, 0.10, 0.22, 0.42)
    sea.add_color_stop_rgb(0.6, 0.04, 0.10, 0.24)
    sea.add_color_stop_rgb(1, 0.02, 0.04, 0.11)
    ctx.arc(c, c, radius, 0, 2 * math.pi)
    ctx.set_source(sea)
    ctx.fill()

    # Land dots: dimmer and smaller towards the edge of the disc.
    x, y, vis = ortho(pts["lon"], pts["lat"], lon0, lat0)
    on = pts["land"] & (vis > 0.02) & ~pts["india"]
    for xi, yi, v in zip(x[on], y[on], vis[on]):
        r = radius * 0.0058 * (0.45 + 0.55 * v)
        ctx.arc(c + xi * radius, c - yi * radius, r, 0, 2 * math.pi)
        ctx.set_source_rgba(0.35, 0.62, 0.95, 0.30 + 0.45 * v)
        ctx.fill()
    # Scattered warm city lights on other land.
    lights = np.flatnonzero(on)
    lights = rng.choice(lights, size=min(len(lights), 900), replace=False)
    for k in lights:
        v = vis[k]
        ctx.arc(c + x[k] * radius, c - y[k] * radius, radius * 0.0045 * (0.5 + v), 0, 2 * math.pi)
        ctx.set_source_rgba(1.0, 0.78, 0.40, 0.25 + 0.5 * v)
        ctx.fill()

    # India: a saffron fill, bright border, dense golden lights.
    def india_path(cx: cairo.Context) -> None:
        for ring in india_rings():
            rx, ry, _ = ortho(ring[:, 0], ring[:, 1], lon0, lat0)
            cx.move_to(c + rx[0] * radius, c - ry[0] * radius)
            for a, b in zip(rx[1:], ry[1:]):
                cx.line_to(c + a * radius, c - b * radius)
            cx.close_path()

    india_path(ctx)
    ctx.set_source_rgba(1.0, 0.55, 0.12, 0.30)
    ctx.fill()
    fx_, fy_, fv = ortho(pts["fine"][:, 0], pts["fine"][:, 1], lon0, lat0)
    keep = rng.random(len(fx_)) < 0.55
    for xi, yi, v in zip(fx_[keep], fy_[keep], fv[keep]):
        ctx.arc(c + xi * radius, c - yi * radius, radius * rng.uniform(0.002, 0.0055), 0, 2 * math.pi)
        ctx.set_source_rgba(1.0, rng.uniform(0.72, 0.92), 0.45, rng.uniform(0.55, 1.0))
        ctx.fill()
    india_path(ctx)
    ctx.set_source_rgba(1.0, 0.80, 0.45, 0.95)
    ctx.set_line_width(max(1.5, radius * 0.0045))
    ctx.stroke()

    # Soft specular light top-left, and a sunrise flare on the upper rim.
    spec = cairo.RadialGradient(c - radius * 0.45, c - radius * 0.5, 0, c - radius * 0.45, c - radius * 0.5,
                                radius * 0.9)
    spec.add_color_stop_rgba(0, 1, 1, 1, 0.10)
    spec.add_color_stop_rgba(1, 1, 1, 1, 0)
    ctx.arc(c, c, radius, 0, 2 * math.pi)
    ctx.set_source(spec)
    ctx.fill()
    base = surface_to_image(surf)

    # India's glow on its own layer.
    s2, c2 = canvas_surface(size, size)
    india_path(c2)
    c2.set_source_rgba(1.0, 0.62, 0.18, 1.0)
    c2.fill()
    india = s2_img = surface_to_image(s2)
    india = Image.new("RGBA", s2_img.size, (255, 150, 40, 0))
    india.putalpha(s2_img.getchannel("A"))
    india = india.filter(ImageFilter.GaussianBlur(radius * 0.035))

    ix, iy, _ = ortho([79.0], [22.5], lon0, lat0)
    return {"base": base, "india": india, "size": size,
            "india_xy": (c + float(ix[0]) * radius, c - float(iy[0]) * radius)}


def flare(radius: int, colour=(255, 214, 150)) -> Image.Image:
    """A soft star-like light flare (sunrise on the globe's rim)."""
    s = radius * 2
    y, x = np.mgrid[0:s, 0:s].astype(np.float32) - radius
    r = np.hypot(x, y) / radius
    core = np.exp(-(r / 0.12) ** 2) + 0.5 * np.exp(-(r / 0.4) ** 2)
    streak = np.exp(-(y / (radius * 0.025)) ** 2) * np.exp(-(np.abs(x) / radius) * 2.2) * 0.9
    streak += np.exp(-(x / (radius * 0.02)) ** 2) * np.exp(-(np.abs(y) / radius) * 3.5) * 0.5
    a = np.clip(core + streak, 0, 1)
    img = np.zeros((s, s, 4), np.float32)
    img[..., :3] = np.array(colour, np.float32) * (0.7 + 0.3 * a[..., None]) + 255 * np.clip(core, 0, 1)[..., None] * 0.4
    img[..., 3] = a * 255
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA")


def backdrop(seed: int = 3, map_alpha: float = 0.16) -> Image.Image:
    """Deep-space navy with a faint dotted world map and soft bokeh."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot((x - W * 0.55) / W, (y - H * 0.45) / H)
    top, bot = np.array([16, 26, 58], np.float32), np.array([3, 6, 16], np.float32)
    img = top * (1 - np.clip(d * 1.5, 0, 1))[..., None] + bot * np.clip(d * 1.5, 0, 1)[..., None]
    bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    # Flat dotted map across the frame, lit more on the right.
    pts = land_points()
    surf, ctx = canvas_surface(W, H)
    lon, lat, land = pts["lon"], pts["lat"], pts["land"]
    for lo, la in zip(lon[land], lat[land]):
        if la < -58:
            continue
        px = (lo + 180) / 360 * W * 1.05 - W * 0.02
        py = (78 - la) / 150 * H * 0.92 + H * 0.02
        ctx.arc(px, py, 1.6, 0, 2 * math.pi)
        ctx.set_source_rgba(0.45, 0.65, 1.0, map_alpha * (0.4 + 0.6 * px / W))
        ctx.fill()
    for _ in range(140):   # city lights on the map
        k = rng.integers(len(lon))
        if not land[k] or lat[k] < -58:
            continue
        px = (lon[k] + 180) / 360 * W * 1.05 - W * 0.02
        py = (78 - lat[k]) / 150 * H * 0.92 + H * 0.02
        ctx.arc(px, py, rng.uniform(1.2, 2.6), 0, 2 * math.pi)
        ctx.set_source_rgba(1.0, 0.8, 0.45, rng.uniform(0.25, 0.6))
        ctx.fill()
    bg.alpha_composite(surface_to_image(surf))
    # Bokeh near the bottom.
    bok = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bok)
    for _ in range(26):
        r = rng.uniform(10, 34)
        bx, by = rng.uniform(0, W), rng.uniform(H * 0.72, H * 1.02)
        warm = rng.random() < 0.6
        col = (255, 190, 110) if warm else (110, 170, 255)
        bd.ellipse([bx - r, by - r, bx + r, by + r], fill=(*col, int(rng.uniform(18, 46))))
    bg.alpha_composite(bok.filter(ImageFilter.GaussianBlur(6)))
    return bg


def particles(n: int = 60, seed: int = 11) -> np.ndarray:
    """Slow drifting motes: x, y, radius, speed, phase."""
    rng = np.random.default_rng(seed)
    return np.c_[rng.uniform(0, W, n), rng.uniform(0, H, n), rng.uniform(1.0, 2.6, n),
                 rng.uniform(6, 22, n), rng.uniform(0, 6.28, n)]


def draw_particles(ctx: cairo.Context, motes: np.ndarray, t: float, alpha: float = 1.0) -> None:
    for x, y, r, v, ph in motes:
        yy = (y - v * t) % H
        a = (0.25 + 0.25 * math.sin(t * 1.3 + ph)) * alpha
        ctx.arc(x + 8 * math.sin(t * 0.4 + ph), yy, r, 0, 2 * math.pi)
        ctx.set_source_rgba(1.0, 0.85, 0.6, a)
        ctx.fill()


def arc_path(p0, p1, lift: float, n: int = 48) -> np.ndarray:
    """A quadratic arc from p0 to p1 bowing upward by ``lift`` pixels."""
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, min(y0, y1) - lift
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * np.array([x0, y0]) + 2 * (1 - t) * t * np.array([mx, my]) + t ** 2 * np.array([x1, y1])


def draw_arc(ctx: cairo.Context, pts: np.ndarray, grow: float, colour=(1.0, 0.75, 0.35),
             alpha: float = 1.0, pulse: float | None = None) -> None:
    """Draw the first ``grow`` fraction of an arc, glowing, with a travelling light."""
    k = max(2, int(len(pts) * clamp(grow)))
    seg = pts[:k]
    for w, a in ((9, 0.08), (5, 0.18), (2.2, 0.85)):
        ctx.new_path()
        ctx.move_to(*seg[0])
        for p in seg[1:]:
            ctx.line_to(*p)
        ctx.set_source_rgba(*colour, a * alpha)
        ctx.set_line_width(w)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.stroke()
    head = seg[-1] if pulse is None else pts[int(clamp(pulse) * (len(pts) - 1))]
    for r, a in ((10, 0.15), (5, 0.4), (2.5, 1.0)):
        ctx.arc(head[0], head[1], r, 0, 2 * math.pi)
        ctx.set_source_rgba(1.0, 0.95, 0.8, a * alpha)
        ctx.fill()


# --------------------------------------------------------------------------- #
# Timing and the closing line
# --------------------------------------------------------------------------- #
def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


class Timeline:
    """When trigger words are spoken, searched in order."""

    def __init__(self, cues: list[dict[str, Any]], offset: float):
        self.words = [(norm(c["text"]), c["start"] + offset) for c in cues]
        self.pos = 0

    def find(self, word: str, default: float) -> float:
        want = norm(word)
        if not want:
            return default
        for i in range(self.pos, len(self.words)):
            if self.words[i][0] == want or (len(want) > 3 and self.words[i][0].startswith(want)):
                self.pos = i + 1
                return self.words[i][1]
        return default


class Finale:
    """The closing line, lit word by word, with a question and two buttons."""

    def __init__(self, spec: dict[str, Any], tl: Timeline, total: float, top: float = H * 0.36):
        self.on = bool(spec.get("lines"))
        self.words: list[dict[str, Any]] = []
        self.t0 = total + 1
        if not self.on:
            return
        accent = {norm(a) for a in spec.get("accent", [])}
        tl.find(spec.get("at", ""), -1)
        tl.pos = max(0, tl.pos - 1)
        sizes, gaps = [104, 104, 54], [0, 118, 214]
        last = None
        for li, line in enumerate(spec["lines"]):
            size = sizes[min(li, 2)]
            weight = "black" if li < 2 else "semibold"
            items = []
            for w in line.split():
                t = tl.find(w, -1)
                if t < 0:
                    t = (last or 0) + 0.2
                last = t
                hot = norm(w) in accent
                lit = (metal_text(w, size, "saffron", weight) if hot
                       else text(w, size, FG, weight, glow_r=size / 10, glow_a=0.35))
                dim = text(w, size, (64, 74, 100), weight, shadow=False)
                items.append({"lit": lit, "dim": dim, "t": t, "adv": font(size, weight).getlength(w)})
            space = font(size, weight).getlength(" ")
            line_w = sum(i["adv"] for i in items) + space * (len(items) - 1)
            x = W / 2 - line_w / 2
            for it in items:
                self.words.append({**it, "x": x + it["adv"] / 2, "y": top + gaps[min(li, 2)]})
                x += it["adv"] + space
        self.t0 = min(w["t"] for w in self.words) - 0.35
        self.top = top
        q = spec.get("question") or {}
        self.q_t = tl.find(q.get("at", ""), total + 1) if q else total + 1
        self.q = text(q.get("text", ""), 44, (110, 235, 215), "semibold", glow_r=5, glow_a=0.4) if q else None
        self.sub_t = tl.find((spec.get("subscribe") or {}).get("at", "subscribe"), total + 1) \
            if spec.get("subscribe") else total + 1
        self.share_t = tl.find((spec.get("share") or {}).get("at", "share"), total + 1) \
            if spec.get("share") else total + 1
        self.sub = _button("SUBSCRIBE", "bell", filled=True) if spec.get("subscribe") else None
        self.share = _button("SHARE", "share-2", filled=False) if spec.get("share") else None

    def fade(self, t: float) -> float:
        """How much of everything else is still visible (1 = all, 0 = gone)."""
        return 1 - 0.95 * ease_out((t - self.t0) / 0.7)

    def draw(self, frame: Image.Image, t: float) -> None:
        if not self.on or t < self.t0:
            return
        scrim = Image.new("RGBA", (W, H), (4, 7, 18, int(170 * ease_out((t - self.t0) / 0.7))))
        frame.alpha_composite(scrim)
        appear = ease_out((t - self.t0) / 0.5)
        for w in self.words:
            paste(frame, w["dim"], w["x"], w["y"], appear)
            v = ease_out((t - w["t"]) / 0.25)
            if v > 0:
                paste(frame, w["lit"], w["x"], w["y"], v, 1 + 0.06 * (1 - ease_back((t - w["t"]) / 0.35)))
        if self.q is not None and t >= self.q_t:
            u = ease_out((t - self.q_t) / 0.4)
            paste(frame, self.q, W / 2, self.top + 318 - (1 - u) * 24, u)
        y = self.top + 450
        if self.sub is not None and t >= self.sub_t:
            s = ease_back((t - self.sub_t) / 0.45)
            pulse = 1 + 0.035 * math.sin((t - self.sub_t) * 5.0) if t - self.sub_t > 0.45 else 1.0
            paste(frame, self.sub, W / 2 - (215 if self.share else 0), y, min(1, s * 1.4), max(0.3, s) * pulse)
        if self.share is not None and t >= self.share_t:
            s = ease_back((t - self.share_t) / 0.45)
            paste(frame, self.share, W / 2 + 215, y, min(1, s * 1.4), max(0.3, s))


def _button(label: str, icon_name: str, filled: bool) -> Image.Image:
    w, h = 390, 104
    S = 2
    surf, ctx = canvas_surface(w * S, h * S)
    r = h * S / 2
    ctx.new_path()
    ctx.arc(r, r, r - 3 * S, math.pi / 2, 3 * math.pi / 2)
    ctx.arc(w * S - r, r, r - 3 * S, -math.pi / 2, math.pi / 2)
    ctx.close_path()
    if filled:
        g = cairo.LinearGradient(0, 0, 0, h * S)
        g.add_color_stop_rgb(0, 1.0, 0.36, 0.36)
        g.add_color_stop_rgb(1, 0.82, 0.08, 0.12)
        ctx.set_source(g)
        ctx.fill()
    else:
        ctx.set_source_rgba(0.08, 0.11, 0.22, 0.85)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.set_line_width(4 * S)
        ctx.stroke()
    img = surface_to_image(surf).resize((w, h), Image.LANCZOS)
    ic = icon(icon_name, 40, "silver", stroke=2.4, glow_r=0, fill_alpha=0.0)
    f = font(36, "black")
    tw = f.getlength(label)
    x0 = (w - (40 + 16 + tw)) / 2
    img.alpha_composite(ic, (int(x0 - ic.width / 2 + 20), int(h / 2 - ic.height / 2)))
    ImageDraw.Draw(img).text((x0 + 56, h / 2 + 2), label, font=f, fill=(255, 255, 255), anchor="lm")
    return glow(img, 14, 0.5, tint=(255, 60, 60) if filled else (180, 200, 255))


class Encoder:
    """Raw RGB frames into ffmpeg."""

    def __init__(self, path: Path, ffmpeg: str, encode_args: list[str] | None = None):
        import subprocess

        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-r", str(FPS), "-i", "-", *(encode_args or ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]),
             "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)

    def write(self, frame: Image.Image) -> None:
        self.proc.stdin.write(np.asarray(frame.convert("RGB")).tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg failed writing the scene")
