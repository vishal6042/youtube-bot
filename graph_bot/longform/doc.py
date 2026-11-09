"""Documentary scenes (Visual Direction v2.0): the look of an economics
documentary rather than a dashboard.

One chapter mode, ``doc``, with a ``kind:`` per composition:

  reveal    dark   night map, a big revealed number, a gold ring on the map
  terrain   dusk   3D relief, map cards or population columns
  race      light  Swiss line chart that runs with the narration, "who led" band
  kinetic   dark   oversized numbers in columns (why 2019)
  district  light  isometric factory districts, one building per $1bn
  bars      light  big horizontal bars with country silhouettes
  ledger    light  who leads what, with silhouettes and counts
  track     light  a race on a running track: each country's economy runs year by year
  people    light  10 x 10 grids of figures, one per country (out of every 100 ...)
  lifeline  dark   an age ruler; lines grow from then to now (life expectancy)
  close     dark   the closing line on the night map, question, subscribe/share

Every moving part is keyed to a word of the narration (``at:``), found in the
word timings edge-tts returns. Type system: Sitka (editorial serif) for
headlines, Segoe UI Black for numbers, Segoe UI Variable for supporting text
and tracked uppercase labels.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import carto
from . import fx
from .fx import FPS, H, W, clamp, ease_in_out, ease_out

VERSION = 5

IVORY = (242, 236, 224)
CHAR = (14, 16, 19)
INK = (22, 23, 26)
GOLD = (201, 164, 92)
GOLD_DK = (138, 106, 46)
C = {"India": (194, 102, 43), "Bangladesh": (140, 35, 53), "Pakistan": (46, 74, 120)}
C_DARK = {"India": (226, 146, 90), "Bangladesh": (208, 89, 107), "Pakistan": (126, 156, 203)}


def col(country: str, dark: bool) -> tuple[int, int, int]:
    return (C_DARK if dark else C).get(country, IVORY if dark else INK)


# --------------------------------------------------------------------------- #
# Type
# --------------------------------------------------------------------------- #
_FONT_DIR = Path("C:/Windows/Fonts")


@lru_cache(maxsize=512)
def F(kind: str, size: int) -> ImageFont.FreeTypeFont:
    size = int(round(size))
    try:
        if kind in ("serif", "serif_i"):
            f = ImageFont.truetype(str(_FONT_DIR / ("SitkaVF.ttf" if kind == "serif" else "SitkaVF-Italic.ttf")), size)
            f.set_variation_by_axes([27 if size >= 44 else 18, 620])
            return f
        if kind == "num":
            return ImageFont.truetype(str(_FONT_DIR / "seguibl.ttf"), size)
        weight = {"sans": 450, "sans_m": 600, "sans_b": 700, "label": 700}[kind]
        f = ImageFont.truetype(str(_FONT_DIR / "SegUIVar.ttf"), size)
        f.set_variation_by_axes([weight, 10.5 if size < 30 else 20])
        return f
    except Exception:
        return fx.font(size, {"num": "black", "label": "bold", "sans_b": "bold"}.get(kind, "semibold"))


class Spr:
    """A text sprite: image, the x/y of its pen origin inside it, and its advance."""

    __slots__ = ("img", "ox", "base", "w")

    def __init__(self, img: Image.Image, ox: int, base: int, w: float):
        self.img, self.ox, self.base, self.w = img, ox, base, w


TRACK = {"label": 0.18, "num": -0.03}


@lru_cache(maxsize=6000)
def T(s: str, kind: str, size: int, color: tuple, track: float | None = None) -> Spr:
    f = F(kind, size)
    if kind == "label":
        s = s.upper()
    tr = TRACK.get(kind, 0.0) if track is None else track
    asc, desc = f.getmetrics()
    pad = int(size * 0.2) + 4
    if abs(tr) < 1e-6:
        w = f.getlength(s)
    else:
        w = sum(f.getlength(ch) for ch in s) + tr * size * max(0, len(s) - 1)
    img = Image.new("RGBA", (int(math.ceil(w)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = tuple(color) if len(color) == 4 else (*color, 255)
    if abs(tr) < 1e-6:
        d.text((pad, pad + asc), s, font=f, fill=fill, anchor="ls")
    else:
        x = float(pad)
        for ch in s:
            d.text((x, pad + asc), ch, font=f, fill=fill, anchor="ls")
            x += f.getlength(ch) + tr * size
    return Spr(img, pad, pad + asc, w)


def paste(frame: Image.Image, img: Image.Image, x: float, y: float) -> None:
    """Composite at a fractional position. Things pinned to a moving map must not
    snap to whole pixels, or they judder against the map gliding underneath."""
    ix, iy = math.floor(x), math.floor(y)
    fx_, fy_ = x - ix, y - iy
    if fx_ > 0.01 or fy_ > 0.01:
        pm = img.convert("RGBa")  # premultiplied, so edges do not pick up dark fringes
        pm = pm.transform((img.width + 1, img.height + 1), Image.AFFINE, (1, 0, -fx_, 0, 1, -fy_), Image.BILINEAR)
        img = pm.convert("RGBA")
    l, t_ = max(0, -ix), max(0, -iy)
    if l or t_:
        if l >= img.width or t_ >= img.height:
            return
        img = img.crop((l, t_, img.width, img.height))
    frame.alpha_composite(img, (ix + l, iy + t_))


def put(frame: Image.Image, sp: Spr, x: float, y: float, align: str = "l", a: float = 1.0,
        s: float = 1.0, sub: bool = False) -> None:
    """Draw a sprite with its baseline at y, aligned at x (l / c / r). ``sub`` places it
    at the exact fractional position (for labels that follow a moving map)."""
    if a <= 0.003:
        return
    img = sp.img
    ox, base, w = sp.ox, sp.base, sp.w
    if abs(s - 1) > 0.004:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)
        ox, base, w = ox * s, base * s, w * s
    left = x - {"l": 0, "c": w / 2, "r": w}[align] - ox
    img = fx.with_alpha(img, a)
    if sub:
        paste(frame, img, left, y - base)
    else:
        frame.alpha_composite(img, (int(round(left)), int(round(y - base))))


def tokens(text: str) -> list[tuple[str, bool]]:
    """Words, with **accent** runs flagged; a newline is the token '\\n'."""
    out: list[tuple[str, bool]] = []
    for i, part in enumerate(str(text).split("**")):
        for line_i, line in enumerate(part.split("\n")):
            if line_i:
                out.append(("\n", False))
            out.extend((w, i % 2 == 1) for w in line.split())
    return out


@lru_cache(maxsize=512)
def para(text: str, kind: str, size: int, color: tuple, max_w: int, line_h: float,
         akind: str | None = None, acolor: tuple | None = None, align: str = "l") -> Spr:
    """A wrapped paragraph; **accent** words take ``akind``/``acolor``."""
    toks = tokens(text)
    akind = akind or kind
    acolor = acolor or color
    space = F(kind, size).getlength(" ")
    lines: list[list[tuple[Spr, float]]] = [[]]
    widths = [0.0]
    for w, acc in toks:
        if w == "\n":
            lines.append([])
            widths.append(0.0)
            continue
        sp = T(w, akind if acc else kind, size, acolor if acc else color)
        need = sp.w + (space if lines[-1] else 0)
        if lines[-1] and widths[-1] + need > max_w:
            lines.append([])
            widths.append(0.0)
            need = sp.w
        lines[-1].append((sp, widths[-1] + (space if lines[-1] else 0)))
        widths[-1] += need
    pad = int(size * 0.3) + 4
    asc = F(kind, size).getmetrics()[0]
    full_w = max(widths) if widths else 0
    img = Image.new("RGBA", (int(full_w) + 2 * pad, int(line_h * (len(lines) - 1) + size * 1.4) + 2 * pad), (0, 0, 0, 0))
    for li, items in enumerate(lines):
        shift = {"l": 0, "c": (full_w - widths[li]) / 2, "r": full_w - widths[li]}[align]
        for sp, x in items:
            img.alpha_composite(sp.img, (int(round(pad + shift + x - sp.ox)), int(round(pad + asc + li * line_h - sp.base))))
    return Spr(img, pad, pad + asc, full_w)


def fmt(v: float, prefix: str = "", suffix: str = "", decimals: int = 0, sign: bool = False) -> str:
    neg = v < 0
    body = f"{abs(v):,.{decimals}f}"
    s = ("\u2212" if neg else ("+" if sign else "")) + prefix + body + suffix
    return s


# --------------------------------------------------------------------------- #
# Backgrounds and motion helpers
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def paper() -> Image.Image:
    rng = np.random.default_rng(2)
    a = np.empty((H, W, 3), np.float32)
    a[:] = IVORY
    yy, xx = np.mgrid[0:H, 0:W]
    dots = ((xx % 6 == 0) & (yy % 6 == 0)).astype(np.float32)
    a -= dots[..., None] * np.array([14, 14, 12])
    a += rng.normal(0, 2.2, (H, W))[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=1)
def charcoal() -> Image.Image:
    rng = np.random.default_rng(4)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot((xx - W * 0.22) / W, (yy - H * 0.15) / H)
    warm = np.clip(1 - d / 0.9, 0, 1) ** 1.6
    base = np.array([17, 18, 21], np.float32)
    a = base + warm[..., None] * np.array([22, 17, 11])
    a += rng.normal(0, 2.6, (H, W))[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=8)
def h_scrim(stops: tuple, rgb=(12, 13, 16)) -> Image.Image:
    """Horizontal gradient overlay: ((x_frac, alpha), ...)."""
    xs = np.linspace(0, 1, W)
    al = np.interp(xs, [s[0] for s in stops], [s[1] for s in stops])
    a = np.zeros((H, W, 4), np.uint8)
    a[..., :3] = rgb
    a[..., 3] = (np.clip(al, 0, 1) * 255).astype(np.uint8)[None, :]
    return Image.fromarray(a, "RGBA")


@lru_cache(maxsize=8)
def radial_scrim(cx: float, cy: float, rx: float, ry: float, alpha: float, rgb=(14, 16, 19)) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot((xx - cx) / rx, (yy - cy) / ry)
    al = np.clip(1 - d, 0, 1) ** 1.2 * alpha
    a = np.zeros((H, W, 4), np.uint8)
    a[..., :3] = rgb
    a[..., 3] = (al * 255).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def rise(t: float, t0: float, dur: float = 0.55) -> tuple[float, float]:
    """(alpha, dy) for an element that fades up into place from t0."""
    u = ease_out((t - t0) / dur)
    return u, (1 - u) * 22


class PlateCam:
    """A slow push into a map plate (drawn carto.PS times larger than the frame)."""

    def __init__(self, z0: float, z1: float, focus: tuple[float, float], t0: float, t1: float):
        self.z0, self.z1, self.focus, self.t0, self.t1 = z0, z1, focus, t0, t1

    def view(self, t: float) -> tuple[float, float, float, float]:
        u = ease_in_out((t - self.t0) / max(0.1, self.t1 - self.t0))
        z = self.z0 + (self.z1 - self.z0) * u
        cw, ch = carto.PW / z, carto.PH / z
        fx_p = carto.PW / 2 + (self.focus[0] - W / 2) * carto.PS
        fy_p = carto.PH / 2 + (self.focus[1] - H / 2) * carto.PS
        k = clamp((z - 1) / max(1e-6, carto.PS - 1))
        cx = carto.PW / 2 + (fx_p - carto.PW / 2) * k
        cy = carto.PH / 2 + (fy_p - carto.PH / 2) * k
        left = min(max(cx - cw / 2, 0), carto.PW - cw)
        top = min(max(cy - ch / 2, 0), carto.PH - ch)
        return left, top, cw, ch

    def frame(self, plate: Image.Image, t: float) -> Image.Image:
        left, top, cw, ch = self.view(t)
        return plate.resize((W, H), Image.BICUBIC, box=(left, top, left + cw, top + ch))

    def pt(self, t: float, x: float, y: float) -> tuple[float, float]:
        """Screen position of a point given in plate-at-rest (video) coordinates."""
        left, top, cw, ch = self.view(t)
        xp = carto.PW / 2 + (x - W / 2) * carto.PS
        yp = carto.PH / 2 + (y - H / 2) * carto.PS
        return (xp - left) * W / cw, (yp - top) * H / ch

    def zoom(self, t: float) -> float:
        left, top, cw, ch = self.view(t)
        return carto.PS * W / cw


def surface() -> tuple[cairo.ImageSurface, cairo.Context]:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    return s, c


def rgb1(c: tuple, a: float = 1.0) -> tuple[float, float, float, float]:
    return c[0] / 255, c[1] / 255, c[2] / 255, a


def split_words(cues: list[dict[str, Any]], offset: float) -> list[tuple[str, float]]:
    """(word, time) pairs. The speech engine sometimes returns a number together with
    the word before it ("In 1990"); those are split, the time shared out by length."""
    out: list[tuple[str, float]] = []
    for c in cues:
        parts = [w for w in (fx.norm(x) for x in str(c["text"]).split()) if w]
        if not parts:
            continue
        t0 = float(c["start"]) + offset
        t1 = max(t0, float(c.get("end", c["start"])) + offset)
        tot = sum(len(w) for w in parts)
        acc = 0
        for w in parts:
            out.append((w, t0 + (t1 - t0) * acc / tot))
            acc += len(w)
    return out


@lru_cache(maxsize=1)
def _wipe_edge() -> Image.Image:
    """The wipe's leading edge: a thin gold line with a soft glow."""
    w = 48
    xs = np.abs(np.arange(w) - (w - 1) / 2)
    al = np.clip(1 - xs / 2.2, 0, 1) * 0.95 + np.exp(-(xs / 9) ** 2) * 0.28
    a = np.zeros((H, w, 4), np.uint8)
    a[..., :3] = GOLD
    a[..., 3] = (np.clip(al, 0, 1) * 255).astype(np.uint8)[None, :]
    return Image.fromarray(a, "RGBA")


def with_neighbours(chart: dict[str, Any], chapters: list[dict[str, Any]], ch: dict[str, Any]) -> dict[str, Any]:
    """A copy of a doc chart that knows its neighbours, for the transitions (and for
    a chart that continues the one before it, where that one's camera ended)."""
    out = dict(chart)
    ids = [c.get("id") for c in chapters]
    try:
        i = ids.index(ch.get("id"))
    except ValueError:
        return out

    def tone(c: dict[str, Any]) -> bool:
        k = (c.get("chart") or {}).get("kind")
        cls = KINDS.get(k) if (c.get("chart") or {}).get("mode") == "doc" else None
        return bool(cls.dark) if cls else True

    if i > 0:
        out["_prev"] = {"dark": tone(chapters[i - 1])}
    if i + 1 < len(chapters):
        nc = (chapters[i + 1].get("chart") or {})
        out["_next"] = {"dark": tone(chapters[i + 1]), "continues": bool(nc.get("continues"))}
    # a continued chart picks the camera up where the previous chapter left it
    n, j = 0, i
    while j > 0 and (chapters[j].get("chart") or {}).get("continues"):
        n += 1
        j -= 1
    if n and not out.get("push"):
        out["_push"] = (1.0 + PUSH * n, 1.0 + PUSH * (n + 1))
    return out


@lru_cache(maxsize=64)
def halo(sp: Spr, rgb=(8, 9, 11), r: float = 9.0) -> Spr:
    """A blurred dark copy of a text sprite, drawn behind it to lift it off a busy map."""
    from PIL import ImageFilter

    pad = int(r * 2.5)
    a = sp.img.getchannel("A")
    big = Image.new("L", (a.width + 2 * pad, a.height + 2 * pad), 0)
    big.paste(a, (pad, pad))
    big = big.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(r))
    big = big.point(lambda v: min(255, int(v * 1.6)))
    img = Image.new("RGBA", big.size, (*rgb, 0))
    img.putalpha(big)
    return Spr(img, sp.ox + pad, sp.base + pad, sp.w)


def with_flags(nmap: "carto.NightMap", plate: Image.Image, chart: dict[str, Any]) -> Image.Image:
    """The night map with each country filled with its flag (``flags: 0.6`` sets how
    strongly; ``flag_countries`` which ones), emblems centred in each country."""
    fa = float(chart.get("flags", 0) or 0)
    if fa <= 0:
        return plate
    out = plate.copy()
    for n in chart.get("flag_countries") or ("India", "Pakistan", "Bangladesh"):
        out.alpha_composite(fx.with_alpha(nmap.flag_of(n, None, float(chart.get("flag_fit", 0.8))), fa))
    return out


# --------------------------------------------------------------------------- #
# Scene base
# --------------------------------------------------------------------------- #
WIPE = 0.55      # seconds a chapter-to-chapter wipe takes on each side of the cut
PUSH = 0.035     # how far a flat scene's camera pushes in over a chapter


class Scene:
    dark = True
    flat = False     # drawn on a transparent canvas over paper/charcoal, with a slow camera push

    def __init__(self, chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
                 data: dict[str, dict[int, float]] | None = None):
        self.c = chart
        self.total = total
        self.offset = offset
        self.words = split_words(cues, offset)
        self.data = data or {}
        self.ink = IVORY if self.dark else INK
        cta = chart.get("cta") or {}
        self.cta = cta
        self.t_cta = self.when(cta.get("at"), -1.0) if cta else -1.0

    def when(self, at: Any, default: float, after: float = -1.0) -> float:
        """Time a word (or phrase, or 'word#2' for its second use) is spoken.

        A number is taken as seconds into the chapter's narration.
        """
        if at is None or at == "":
            return default
        if isinstance(at, (int, float)):
            return self.offset + float(at)
        text, _, nth = str(at).partition("#")
        want = [fx.norm(w) for w in text.split() if fx.norm(w)]
        n = int(nth) if nth.isdigit() else 1
        if not want:
            return default
        seen = 0
        for i in range(len(self.words)):
            if self.words[i][1] < after:
                continue
            ok = True
            for k, w in enumerate(want):
                if i + k >= len(self.words):
                    ok = False
                    break
                got = self.words[i + k][0]
                if not (got == w or (len(w) > 3 and got.startswith(w))):
                    ok = False
                    break
            if ok:
                seen += 1
                if seen == n:
                    return self.words[i][1]
        return default

    # -- the frame as it goes to the encoder ---------------------------------
    def canvas(self) -> Image.Image:
        """Where a flat scene draws its content: transparent, so the camera can move
        it while the paper (whose dot grid would shimmer if scaled) stays still."""
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def background(self) -> Image.Image:
        return charcoal() if self.dark else paper()

    def render(self, t: float) -> Image.Image:
        img = self.frame(t)
        if self.flat:
            img = self.camera(img, t)
        self.overlay(img, t)
        self.wipe(img, t)
        return img

    def camera(self, content: Image.Image, t: float) -> Image.Image:
        """A slow, steady push into the content (never quite still, like a rostrum
        camera). ``push: [1.0, 1.035]`` and ``focus: [x, y]`` override it."""
        c = self.c
        z0, z1 = c.get("push") or c.get("_push") or (1.0, 1.0 + PUSH)
        fx_, fy_ = c.get("focus") or (W / 2, H * 0.55)
        z = z0 + (z1 - z0) * clamp(t / max(0.1, self.total))
        out = self.background().copy()
        if abs(z - 1) < 1e-4:
            out.alpha_composite(content)
            return out
        k = 1 / z
        pm = content.convert("RGBa").transform((W, H), Image.AFFINE, (k, 0, fx_ - fx_ * k, 0, k, fy_ - fy_ * k),
                                                Image.BICUBIC)
        out.alpha_composite(pm.convert("RGBA"))
        return out

    def wipe(self, frame: Image.Image, t: float) -> None:
        """A sweep in the next chapter's tone instead of a hard cut: it crosses the
        frame left to right over the last moments of this chapter, and the next
        chapter opens by drawing it off to the right. No wipe where a chart simply
        carries on into the next chapter."""
        nxt, prv = self.c.get("_next"), self.c.get("_prev")
        edges = []
        if nxt and not nxt.get("continues"):
            u = (t - (self.total - 1 / FPS - WIPE)) / WIPE
            if u > 0:
                e = W * ease_in_out(min(1.0, u))
                bg = charcoal() if nxt.get("dark") else paper()
                if e >= 1:
                    frame.paste(bg.crop((0, 0, int(e), H)), (0, 0))
                edges.append(e)
        if prv and not self.c.get("continues"):
            u = t / WIPE
            if u < 1:
                e = W * ease_in_out(u)
                if e < W - 1:
                    frame.paste(self.background().crop((int(e), 0, W, H)), (int(e), 0))
                edges.append(e)
        for e in edges:
            if 2 < e < W - 2:
                glow = _wipe_edge()
                frame.alpha_composite(glow, (int(round(e - glow.width / 2)), 0))

    # -- shared pieces -----------------------------------------------------
    def overlay(self, frame: Image.Image, t: float) -> None:
        """A call to action in the bottom-right corner, if the chapter has one:

            cta: {at: subscribe, line: Enjoying the race?}

        The Subscribe button pops in as the narrator asks, is "pressed" and turns
        into Subscribed, then everything fades after about five seconds."""
        tc = self.t_cta
        if tc < 0 or t < tc:
            return
        hold = float(self.cta.get("hold", 5.0))
        fade = 1 - ease_out((t - tc - hold) / 0.5)
        if fade <= 0:
            return
        dark = self.dark
        u = fx.ease_back(min(1.0, (t - tc) / 0.5), 1.6)
        pressed = t - tc >= 1.5
        press = 1 - 0.07 * math.sin(math.pi * clamp((t - tc - 1.3) / 0.25))
        img = pill("Subscribed" if pressed else "Subscribe", not pressed, dark)
        k = max(0.01, u * press)
        if abs(k - 1) > 0.004:
            img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.BICUBIC)
        cx, cy = W - 104 - 150, float(self.cta.get("y", H - 150))
        paste(frame, fx.with_alpha(img, fade * min(1.0, (t - tc) / 0.2)), cx - img.width / 2, cy - img.height / 2)
        if self.cta.get("line"):
            a, dy = rise(t, tc + 0.15, 0.5)
            col_ = (*IVORY, 230) if dark else (*INK, 230)
            put(frame, T(self.cta["line"], "serif_i", 34, col_), cx, cy - 66 + dy, "c", a * fade)

    def kicker(self, frame: Image.Image, text: str, x: float, y: float, t: float, t0: float,
               align: str = "l") -> None:
        a, dy = rise(t, t0)
        if a <= 0:
            return
        sp = T(text, "label", 22, GOLD if self.dark else (96, 92, 84))
        if self.dark:
            s, c = None, None
            rule_w = 56
            if align == "c":
                put(frame, sp, x, y + dy, "c", a)
                for side in (-1, 1):
                    x0 = x + side * (sp.w / 2 + 20)
                    ImageDraw.Draw(frame, "RGBA").line([(x0, y - 8 + dy), (x0 + side * rule_w, y - 8 + dy)],
                                               fill=(*GOLD, int(255 * a)), width=2)
            else:
                ImageDraw.Draw(frame, "RGBA").line([(x, y - 8 + dy), (x + rule_w, y - 8 + dy)],
                                           fill=(*GOLD, int(255 * a)), width=2)
                put(frame, sp, x + rule_w + 20, y + dy, "l", a)
        else:
            ImageDraw.Draw(frame, "RGBA").rectangle([x, y - 76 + dy, x + 56, y - 70 + dy], fill=(*INK, int(255 * a)))
            put(frame, sp, x, y + dy, "l", a)

    def brand(self, frame: Image.Image) -> None:
        sp = T("Data in Motion", "label", 17, (*(IVORY if self.dark else INK), 110))
        put(frame, sp, W - 64, H - 40, "r")


# --------------------------------------------------------------------------- #
# reveal: the cinematic opening
# --------------------------------------------------------------------------- #
class Reveal(Scene):
    dark = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.map = carto.night(c.get("map", "wide"))
        plate = with_flags(self.map, self.map.plate(), c)
        self.lights = self.map.lights()
        self.lit = plate.copy()
        self.lit.alpha_composite(self.lights)
        self.dim = plate
        self.cam = PlateCam(1.0, c.get("zoom", 1.07), tuple(c.get("focus", (1500, 520))), 0, self.total)
        self.scrim = h_scrim(((0, 0.9), (0.40, 0.62), (0.60, 0.0), (1, 0)))
        self.t_kick = self.when(c.get("kicker_at"), 0.25)
        big, small = c.get("big") or {}, c.get("small") or {}
        self.big, self.small = big, small
        self.t_big = self.when(big.get("at"), 0.6)
        self.t_small = self.when(small.get("at"), self.t_big + 2.5, after=self.t_big)
        ring = c.get("ring") or {}
        self.ring = ring
        self.t_ring = self.when(ring.get("at"), self.t_big + 0.8)
        self.labels = [(lb, self.when(lb.get("at"), 1.5)) for lb in c.get("labels") or []]
        self.heads = [(c.get("headline", ""), self.when(c.get("headline_at"), 0.35))]
        after = 0.0
        for th in c.get("then") or []:
            tt = self.when(th.get("at"), self.total + 1, after=after)
            after = tt
            self.heads.append((th.get("headline", ""), tt))

    def frame(self, t: float) -> Image.Image:
        c = self.c
        la = 0.25 + 0.75 * ease_out(t / 2.2)
        if la < 0.999:
            plate = self.dim.copy()
            plate.alpha_composite(fx.with_alpha(self.lights, la))
        else:
            plate = self.lit
        frame = self.cam.frame(plate, t)
        frame.alpha_composite(self.scrim)
        # the gold ring and its label on the map
        if self.ring:
            lon, lat = carto.COUNTRY_POINTS[self.ring.get("country", "Bangladesh")]
            x, y = self.cam.pt(t, *self.map.proj(lon, lat))
            z = self.cam.zoom(t)
            u = ease_out((t - self.t_ring) / 0.8)
            if u > 0:
                s, cx = surface()
                r = self.ring.get("r", 60) * z
                cx.set_source_rgba(*rgb1(GOLD, 0.95))
                cx.set_line_width(4)
                cx.arc(x, y, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * u)
                cx.stroke()
                v = ease_out((t - self.t_ring - 0.5) / 0.5)
                name = T(self.ring.get("label", self.ring.get("country", "")), "label", 24,
                         col(self.ring.get("country", ""), True))
                # leader up and right; down and right (into the sea) if the name
                # would run off the frame
                xe = self.cam.pt(self.total, *self.map.proj(lon, lat))[0]
                re_ = self.ring.get("r", 60) * self.cam.zoom(self.total)
                sy = -1 if xe + re_ * 0.7 + 84 + name.w < W - 56 else 1    # one side for the whole chapter
                if v > 0:
                    x0, y0 = x + r * 0.7, y + sy * r * 0.7
                    cx.move_to(x0, y0)
                    cx.line_to(x0 + 64 * v, y0 + sy * 60 * v)
                    cx.set_line_width(2.4)
                    cx.stroke()
                frame.alpha_composite(carto.to_img(s))
                if v > 0:
                    lx = min(x + r * 0.7 + 84, W - 56 - name.w)
                    ly = y - r * 0.7 - 50 if sy < 0 else y + r * 0.7 + 78
                    put(frame, halo(name), lx, ly, "l", v * 0.9, sub=True)
                    put(frame, name, lx, ly, "l", v, sub=True)
        for lb, tl in self.labels:
            u = ease_out((t - tl) / 0.6)
            if u > 0:
                lon, lat = carto.COUNTRY_POINTS[lb["country"]]
                x, y = self.cam.pt(t, *self.map.proj(lon, lat))
                name = T(lb.get("label", lb["country"]), "label", 24, col(lb["country"], True))
                put(frame, halo(name), x + lb.get("dx", 0), y + lb.get("dy", 0), "c", u * 0.9, sub=True)
                put(frame, name, x + lb.get("dx", 0), y + lb.get("dy", 0), "c", u * 0.92, sub=True)
        # the text panel
        X = 104
        self.kicker(frame, c.get("kicker", ""), X, 120, t, self.t_kick)
        for i, (txt, th) in enumerate(self.heads):
            nxt = self.heads[i + 1][1] if i + 1 < len(self.heads) else self.total + 9
            a_in, dy = rise(t, th)
            a_out = 1 - ease_out((t - nxt) / 0.35)
            a = a_in * a_out
            if a > 0:
                put(frame, para(txt, "serif", 62, IVORY, int(c.get("headline_w", 860)), 70), X, 212 + dy, "l", a)
        big, small = self.big, self.small
        if big:
            a, dy = rise(t, self.t_big - 0.2)
            put(frame, T(big.get("label", big.get("country", "")), "label", 24, col(big.get("country", ""), True)),
                X, 366 + dy, "l", a)
            u = ease_out((t - self.t_big) / 1.1)
            if u > 0:
                v = big["value"] * u
                txt = fmt(v, big.get("prefix", ""), big.get("suffix", ""), big.get("decimals", 0))
                put(frame, T(txt, "num", 216, IVORY), X - 6, 572, "l", min(1, u * 3))
        if small:
            a, dy = rise(t, self.t_small)
            if a > 0:
                ImageDraw.Draw(frame, "RGBA").line([(X, 632), (X + 600 * a, 632)], fill=(*IVORY, 72), width=2)
                txt = fmt(small["value"], small.get("prefix", ""), small.get("suffix", ""), small.get("decimals", 0))
                sp = T(txt, "num", 104, (*IVORY, 150))
                put(frame, sp, X - 3, 752 + dy, "l", a)
                put(frame, T(small.get("label", small.get("country", "")), "label", 24,
                             col(small.get("country", ""), True)), X + sp.w + 26, 748 + dy, "l", a)
                put(frame, T(c.get("note", ""), "sans", 26, (*IVORY, 150)), X, 822 + dy, "l", a)
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# terrain: perspective relief with map cards or population columns
# --------------------------------------------------------------------------- #
def cylinder_sprite(r: float, h: float, rgb: tuple, ring_h: float | None, ring_a: float = 1.0) -> tuple[Image.Image, float, float]:
    """A soft-lit column; returns (sprite, x of axis in sprite, y of base in sprite)."""
    ry = r * 0.30
    pad = 16
    sw, sh = int(2 * r + 2 * pad + 20), int(h + 2 * ry + 2 * pad + 10)
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
    c = cairo.Context(s)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    x, y = r + pad, sh - pad - ry
    rgbf = np.array(rgb) / 255.0
    g = cairo.LinearGradient(x - r, 0, x + r, 0)
    g.add_color_stop_rgb(0, *np.clip(rgbf * 0.95 + 0.04, 0, 1))
    g.add_color_stop_rgb(0.3, *np.clip(rgbf * 1.08 + 0.03, 0, 1))
    g.add_color_stop_rgb(0.85, *(rgbf * 0.62))
    g.add_color_stop_rgb(1, *(rgbf * 0.75))
    c.move_to(x - r, y - h)
    c.line_to(x - r, y)
    c.save(); c.translate(x, y); c.scale(1, ry / r); c.arc_negative(0, 0, r, math.pi, 0); c.restore()
    c.line_to(x + r, y - h)
    c.close_path()
    c.set_source(g)
    c.fill()
    c.save(); c.translate(x, y - h); c.scale(1, ry / r); c.arc(0, 0, r, 0, 2 * math.pi); c.restore()
    c.set_source_rgb(*np.clip(rgbf * 1.3 + 0.08, 0, 1))
    c.fill()
    if ring_h is not None and ring_a > 0:
        c.save(); c.translate(x, y - ring_h); c.scale(1, ry / r); c.arc(0, 0, r + 6, 0, 2 * math.pi); c.restore()
        c.set_source_rgba(*rgb1(GOLD, ring_a))
        c.set_line_width(3.5)
        c.stroke()
    return carto.to_img(s), x, y


@lru_cache(maxsize=1)
def pin_sprite() -> Image.Image:
    """The gold map pin with its stem; its point sits 12 px right, 30 px down."""
    sp = cairo.ImageSurface(cairo.FORMAT_ARGB32, 24, 42)
    c = cairo.Context(sp)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    c.set_source_rgba(*rgb1(INK))
    c.set_line_width(2)
    c.move_to(12, 4); c.line_to(12, 20); c.stroke()
    c.arc(12, 30, 8, 0, 2 * math.pi)
    c.set_source_rgba(*rgb1(GOLD)); c.fill_preserve()
    c.set_source_rgba(*rgb1(INK)); c.stroke()
    return carto.to_img(sp)


@lru_cache(maxsize=4)
def shadow_blob(r: int) -> Image.Image:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8 * r, 4 * r)
    c = cairo.Context(s)
    c.save(); c.translate(4 * r, 2 * r); c.scale(1, 0.32); c.arc(0, 0, 1.6 * r, 0, 2 * math.pi); c.restore()
    c.set_source_rgba(0.05, 0.04, 0.03, 0.4)
    c.fill()
    from PIL import ImageFilter

    return carto.to_img(s).filter(ImageFilter.GaussianBlur(r * 0.5))


class Terrain(Scene):
    dark = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.view = carto.terrain_view(c.get("view", "level"))
        self.plate = self.view.plate()
        self.cam = PlateCam(1.0, c.get("zoom", 1.07), tuple(c.get("focus", (W / 2, 420))), 0, self.total)
        self.scrim = radial_scrim(160, 1010, 1150, 660, 0.9)
        self.t_kick = self.when(c.get("kicker_at"), 0.3)
        self.t_big = self.when(c.get("big_at"), 0.5)
        self.t_head = self.when(c.get("headline_at"), 0.9)
        after = 0.0
        self.cards = []
        for cd in c.get("cards") or []:
            tt = self.when(cd.get("at"), after + 1.0, after=after)
            after = tt
            lon, lat = cd.get("lonlat") or carto.COUNTRY_POINTS[cd["country"]]
            x, y, _ = self.view.proj(lon, lat, cd.get("elev", 400))
            self.cards.append((cd, tt, x, y))
        after = 0.0
        self._cw: dict[int, float] = {}
        self.cols = []
        for cl in c.get("columns") or []:
            t1 = self.when(cl.get("from_at"), after + 0.8, after=after)
            t2 = self.when(cl.get("at"), t1 + 3.0, after=t1)
            after = t1
            lon, lat = cl.get("lonlat") or carto.COUNTRY_POINTS[cl["country"]]
            x, y, _ = self.view.proj(lon, lat)
            self.cols.append((cl, t1, t2, x, y))

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.cam.frame(self.plate, t)
        frame.alpha_composite(self.scrim)
        z = self.cam.zoom(t)
        for cl, t1, t2, bx, by in self.cols:
            x, y = self.cam.pt(t, bx, by)
            k = cl.get("px_per_unit", 1.0) * z
            u1 = ease_out((t - t1) / 1.0)
            u2 = ease_in_out((t - t2) / 1.8)
            if u1 <= 0:
                continue
            v = cl["from"] * u1 + (cl["to"] - cl["from"]) * u2
            h = max(2.0, v * k)
            r = cl.get("r", 24) * z
            sh = shadow_blob(int(r))
            paste(frame, fx.with_alpha(sh, u1), x + h * 0.06 - sh.width / 2, y + 2 - sh.height / 2)
            ring_a = ease_out((t - t2) / 0.5)
            spr, ax, ay = cylinder_sprite(r, h, C[cl["country"]], cl["from"] * k if u2 > 0 else None, ring_a)
            paste(frame, spr, x - ax, y - ay)
            # value card beside the top
            top = y - h
            dark = col(cl["country"], False)
            card_a = u1
            lab = cl.get("label", cl["country"]) if t >= t2 else cl.get("from_title", cl["country"])
            num = fmt(v, cl.get("prefix", ""), cl.get("suffix", ""), cl.get("decimals", 0))
            side = cl.get("side", 1)
            cy = top + 8
            if u2 > 0:
                cy -= ring_a * max(0.0, cy - (y - cl["from"] * k - 92))
            self._card(frame, x + side * (r + 26), cy, lab, num, dark, card_a, align="l" if side > 0 else "r", big=True,
                       min_w=self._card_w(cl, dark))
            if u2 > 0:
                ry = y - cl["from"] * k
                tag = T(cl.get("from_label", ""), "label", 19, INK)
                tx = x + side * (r + 26)
                w = tag.w + 28
                x0 = tx if side > 0 else tx - w
                box = Image.new("RGBA", (int(math.ceil(w)) + 1, 37), (0, 0, 0, 0))
                ImageDraw.Draw(box, "RGBA").rectangle([0, 0, w, 36], fill=(242, 236, 224, 230))
                put(box, tag, 14, 26, "l")
                # the tag waits until the card above has moved clear of it
                tag_a = ease_out((t - t2 - 0.45) / 0.4)
                if tag_a > 0:
                    paste(frame, fx.with_alpha(box, tag_a), x0, ry - 20)
        for cd, tt, bx, by in self.cards:
            u = ease_out((t - tt) / 0.6)
            if u <= 0:
                continue
            x, y = self.cam.pt(t, bx, by)
            paste(frame, fx.with_alpha(pin_sprite(), u), x - 12, y - 30)
            self._card(frame, x, y - 30 - (1 - u) * 18, cd.get("label", cd["country"]), cd["value"],
                       col(cd["country"], False), u, align="c", big=True, above=True)
        # the text block, bottom left
        X = 88
        self.kicker(frame, c.get("kicker", ""), X, 588, t, self.t_kick)
        y = 640
        if c.get("big"):
            a, dy = rise(t, self.t_big)
            put(frame, T(str(c["big"]), "num", 168, IVORY), X - 6, 760 + dy, "l", a)
            y = 790
        a, dy = rise(t, self.t_head)
        hp = para(c.get("headline", ""), "serif", 46, IVORY, c.get("headline_w", 660), 52, acolor=GOLD)
        put(frame, hp, X, y + 38 + dy, "l", a)
        nlines = round((hp.img.height - 2 * hp.ox - 46 * 1.4) / 52) + 1
        if c.get("note"):
            put(frame, para(c["note"], "sans", 22, (*IVORY, 165), 560, 30), X, y + 38 + 52 * nlines + 8 + dy, "l", a)
        self.brand(frame)
        return frame

    def _card_w(self, cl: dict[str, Any], rgb: tuple) -> float:
        """One width for a column's card while its number counts, so the box does not
        twitch as digits change: the widest label and the widest the number can be."""
        key = id(cl)
        if key not in self._cw:
            labs = [cl.get("label", cl["country"]), cl.get("from_title", cl["country"])]
            wl = max(T(lb, "label", 20, rgb).w for lb in labs)
            wn = 0.0
            for v in (cl["from"], cl["to"]):
                txt = fmt(v, cl.get("prefix", ""), cl.get("suffix", ""), cl.get("decimals", 0))
                for d in "0123456789":
                    wn = max(wn, T(re.sub(r"\d", d, txt), "num", 64, INK).w)
            self._cw[key] = max(wl, wn)
        return self._cw[key]

    def _card(self, frame: Image.Image, x: float, y: float, label: str, value: str, rgb: tuple, a: float,
              align: str = "c", big: bool = True, above: bool = False, min_w: float = 0) -> None:
        if a <= 0:
            return
        lab = T(label, "label", 20, rgb)
        num = T(value, "num", 64 if big else 44, INK)
        w = max(lab.w, num.w, min_w) + 44
        hgt = 118 if big else 90
        x0 = {"c": x - w / 2, "l": x, "r": x - w}[align]
        y0 = y - hgt if above else y - hgt / 2
        card = Image.new("RGBA", (int(w) + 40, hgt + 40), (0, 0, 0, 0))
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([20, 26, 20 + w, 26 + hgt], fill=(0, 0, 0, 70))
        from PIL import ImageFilter

        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
        ImageDraw.Draw(card, "RGBA").rectangle([20, 20, 20 + w, 20 + hgt], fill=(242, 236, 224, 238))
        cx = 20 + w / 2 if align == "c" else 20 + 22
        al = "c" if align == "c" else "l"
        put(card, lab, cx, 20 + 34, al)
        put(card, num, cx - (0 if al == "c" else 3), 20 + (100 if big else 76), al)
        paste(frame, fx.with_alpha(card, a), x0 - 20, y0 - 20)


# --------------------------------------------------------------------------- #
# race: the Swiss line chart that runs with the narration
# --------------------------------------------------------------------------- #
def nice_step(span: float) -> float:
    raw = span / 3.2
    mag = 10 ** math.floor(math.log10(max(raw, 1e-9)))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


class Race(Scene):
    dark = False
    flat = True
    X0, X1, Y0, Y1 = 196, 1390, 336, 822

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.ents = list(c.get("entities") or self.data.keys())
        self.y_lo, self.y_hi = int(c["year_min"]), int(c["year_max"])
        self.series = {}
        for e in self.ents:
            d = self.data.get(e, {})
            ys = np.arange(self.y_lo, self.y_hi + 1)
            vals = np.array([d.get(int(y), np.nan) for y in ys], float)
            ok = ~np.isnan(vals)
            vals = np.interp(ys, ys[ok], vals[ok])
            self.series[e] = vals
        self.scale = float(c.get("value_scale", 1))
        self.prefix, self.suffix = c.get("prefix", ""), c.get("unit_suffix", "")
        self.dec = int(c.get("decimals", 0))
        self.hi = c.get("highlight")
        # when the chart reaches each key year
        start = float(c.get("start", self.y_lo))
        knots = [(0.0, start)]
        after = 0.0
        for kk in c.get("keys") or []:
            tt = self.when(kk.get("at"), -1, after=after)
            if tt < 0:
                continue
            after = tt
            knots.append((tt, float(kk["year"])))
        if len(knots) == 1:
            knots.append((max(1.0, self.total - 1.5), float(self.y_hi)))
        # hold the start until a little before the first key
        if knots[1][0] > 1.0:
            knots.insert(1, (min(0.6, knots[1][0] * 0.3), start))
        self.knots = knots
        n = int(round(self.total * FPS)) + 2
        self.now = np.array([self._now(i / FPS) for i in range(n)])
        # y range follows what has been drawn, smoothed
        floor = float(c.get("y_floor", 0))
        tgt = np.array([max(self._visible_max(y), floor) * 1.12 for y in self.now])
        ymax = np.empty_like(tgt)
        cur = tgt[0]
        for i, v in enumerate(tgt):
            cur += (v - cur) * (1 - math.exp(-1 / (FPS * 0.45)))
            ymax[i] = cur
        self.ymax = ymax if not c.get("y_max") else np.full_like(tgt, float(c["y_max"]) * self.scale)
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.t_deck = self.when(c.get("deck_at"), 0.9)
        if c.get("continues"):
            self.t_head = self.t_deck = -10.0
        self.marks = c.get("marks") or []
        self.moments = []
        after = 0.0
        for m in c.get("moments") or []:
            tt = self.when(m.get("at"), -1, after=after)
            if tt < 0:   # when the line reaches that year
                hit = np.nonzero(self.now >= m["year"])[0]
                tt = hit[0] / FPS if len(hit) else self.total + 1
            after = tt
            self.moments.append((m, tt))
        self.sil = {e: carto.silhouette(e, 38) for e in self.ents if e in carto.MAIN}

    def _now(self, t: float) -> float:
        ks = self.knots
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, y0), (t1, y1) in zip(ks, ks[1:]):
            if t <= t1:
                u = (t - t0) / max(1e-6, t1 - t0)
                u = 0.45 * u + 0.55 * ease_in_out(u)
                return y0 + (y1 - y0) * u
        return ks[-1][1]

    def _visible_max(self, now: float) -> float:
        k = int(min(len(self.series[self.ents[0]]) - 1, max(0, math.ceil(now - self.y_lo))))
        return max(float(np.max(self.series[e][:k + 1])) for e in self.ents)

    def val(self, e: str, year: float) -> float:
        s = self.series[e]
        u = year - self.y_lo
        i = int(min(max(math.floor(u), 0), len(s) - 2))
        f = clamp(u - i)
        return float(s[i] + (s[i + 1] - s[i]) * f)

    def X(self, year: float) -> float:
        return self.X0 + (year - self.y_lo) / (self.y_hi - self.y_lo) * (self.X1 - self.X0)

    def Y(self, v: float, ymax: float) -> float:
        return self.Y1 - v / ymax * (self.Y1 - self.Y0)

    def label_v(self, v: float) -> str:
        return fmt(v / self.scale, self.prefix, self.suffix, self.dec)

    def frame(self, t: float) -> Image.Image:
        c = self.c
        i = min(len(self.now) - 1, int(round(t * FPS)))
        now, ymax = float(self.now[i]), float(self.ymax[i])
        frame = self.canvas()
        s, cx = surface()
        # grid
        step = nice_step(ymax / self.scale) * self.scale
        half = step / 2
        labels = []
        v = 0.0
        while v <= ymax * 1.0001:
            y = self.Y(v, ymax)
            major = abs(v / step - round(v / step)) < 1e-6
            gap = (self.Y1 - self.Y0) * half / ymax
            a = 1.0 if major else clamp((gap - 70) / 40)
            if a > 0.01:
                cx.set_source_rgba(*rgb1(INK, (0.55 if v == 0 else 0.13) * a))
                cx.set_line_width(2.2 if v == 0 else 1.4)
                cx.move_to(self.X0, y)
                cx.line_to(self.X1 + 10, y)
                cx.stroke()
                labels.append((v, y, a))
            v += half
        # marks (dotted)
        for mk in self.marks:
            a = ease_out((now - mk["year"] + 0.4) / 1.5)
            if a <= 0:
                continue
            x = self.X(mk["year"])
            cx.set_source_rgba(*rgb1(INK, 0.38 * a))
            cx.set_line_width(1.6)
            cx.set_dash([2, 6])
            cx.move_to(x, self.Y0)
            cx.line_to(x, self.Y1)
            cx.stroke()
            cx.set_dash([])
        # lines
        order = [e for e in self.ents if e != self.hi] + ([self.hi] if self.hi in self.ents else [])
        heads = {}
        for e in order:
            ys = np.arange(self.y_lo, math.floor(now) + 1)
            pts = [(self.X(y), self.Y(self.series[e][int(y - self.y_lo)], ymax)) for y in ys]
            if now > ys[-1]:
                pts.append((self.X(now), self.Y(self.val(e, now), ymax)))
            cx.set_source_rgba(*rgb1(C.get(e, INK)))
            cx.set_line_width(5.4 if e == self.hi else 4.6)
            cx.move_to(*pts[0])
            for p in pts[1:]:
                cx.line_to(*p)
            cx.stroke()
            heads[e] = pts[-1]
        for e, (x, y) in heads.items():
            cx.arc(x, y, 8, 0, 2 * math.pi)
            cx.set_source_rgba(*rgb1(C.get(e, INK)))
            cx.fill()
        # who led
        if c.get("who_led", False):
            by0, by1 = 890, 912
            yr = self.y_lo
            prev = None
            while yr <= min(now, self.y_hi):
                lead = max(self.ents, key=lambda e: self.series[e][yr - self.y_lo])
                x0 = self.X(yr - 0.5 if yr > self.y_lo else yr)
                x1 = self.X(min(yr + 0.5, now))
                if x1 > x0:
                    cx.rectangle(x0, by0, x1 - x0 + 0.6, by1 - by0)
                    cx.set_source_rgba(*rgb1(C.get(lead, INK)))
                    cx.fill()
                if prev is not None and lead != prev:
                    cx.set_source_rgba(*rgb1(INK, 0.9))
                    cx.set_line_width(2)
                    cx.move_to(x0, by0 - 7)
                    cx.line_to(x0, by1 + 7)
                    cx.stroke()
                prev = lead
                yr += 1
        # moment rings
        live = [k for k, (_, tt) in enumerate(self.moments) if t >= tt]
        latest = live[-1] if live else -1
        for k, (m, tt) in enumerate(self.moments):
            u = ease_out((t - tt) / 0.7)
            if u <= 0:
                continue
            x, y = self.X(m["year"]), self.Y(self.val(m["entity"], m["year"]), ymax)
            nxt = self.moments[k + 1][1] if k + 1 < len(self.moments) else self.total + 9
            fade = 1 - 0.6 * ease_out((t - nxt) / 0.5)
            cx.set_source_rgba(*rgb1(GOLD_DK, 0.95 * fade))
            cx.set_line_width(3.2)
            cx.new_sub_path()
            cx.arc(x, y, 26, -math.pi / 2, -math.pi / 2 + 2 * math.pi * u)
            cx.stroke()
            v = ease_out((t - tt - 0.35) / 0.5) * (1 - ease_out((t - nxt) / 0.4))
            if v > 0 and y - 30 > self.Y0 - 12:
                cx.set_source_rgba(*rgb1(GOLD_DK, 0.9 * v))
                cx.move_to(x, y - 28)
                cx.line_to(x, y - 28 - (y - 28 - (self.Y0 - 12)) * v)
                cx.set_line_width(1.8)
                cx.stroke()
        frame.alpha_composite(carto.to_img(s))
        # text over the plot
        for v, y, a in labels:
            put(frame, T(self.label_v(v), "sans_m", 24, (*INK, 150)), self.X0 - 18, y + 8, "r", a)
        span = self.y_hi - self.y_lo
        stepx = 20 if span > 45 else 10 if span > 18 else 5
        yr0 = int(math.ceil(self.y_lo / stepx) * stepx)
        for yr in [self.y_lo] + list(range(yr0, self.y_hi + 1, stepx)):
            if yr != self.y_lo and yr - self.y_lo < stepx * 0.4:
                continue
            put(frame, T(str(yr), "sans_m", 24, (*INK, 160)), self.X(yr), self.Y1 + 38, "c")
        if c.get("who_led", False):
            put(frame, T("Who led", "label", 20, (*INK, 170)), self.X0 - 18, 909, "r")
        for mk in self.marks:
            a = ease_out((now - mk["year"] + 0.4) / 1.5)
            if a > 0:
                put(frame, T(mk["label"], "label", 19, (*INK, 165)), self.X(mk["year"]) + 10, self.Y0 + 22, "l", a)
        for k, (m, tt) in enumerate(self.moments):
            nxt = self.moments[k + 1][1] if k + 1 < len(self.moments) else self.total + 9
            v = ease_out((t - tt - 0.45) / 0.45) * (1 - ease_out((t - nxt) / 0.4))
            if v <= 0:
                continue
            x = self.X(m["year"])
            lab = T(m.get("label", ""), "label", 20, (*INK, 210))
            ttl = T(str(m.get("title", m["year"])), "num", 40, INK)
            wmax = max(lab.w, ttl.w)
            fx_ = min(max(x, self.X0 + wmax / 2), self.X1 + 120 - wmax / 2)
            put(frame, lab, fx_, self.Y0 - 58 + (1 - v) * 10, "c", v)
            put(frame, ttl, fx_, self.Y0 - 18 + (1 - v) * 10, "c", v)
        # line-head labels, kept apart
        tags = sorted(((y, e) for e, (x, y) in heads.items()), key=lambda q: q[0])
        placed = []
        for y, e in tags:
            if placed and y < placed[-1][0] + 50:
                y = placed[-1][0] + 50
            placed.append((y, e))
        for y, e in placed:
            x = heads[e][0] + 30
            sil = self.sil.get(e)
            if sil is not None:
                frame.alpha_composite(sil, (int(x), int(y - sil.height / 2)))
                x += sil.width + 12
            name = T(c.get("names", {}).get(e, e), "sans_b", 30, C.get(e, INK))
            put(frame, name, x, y + 11, "l")
            put(frame, T(self.label_v(self.val(e, now)), "sans_b", 30, INK), x + name.w + 12, y + 11, "l")
        # header
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        if c.get("deck"):
            a, dy = rise(t, self.t_deck)
            put(frame, para(c["deck"], "sans", 27, (*INK, 215), 560, 38, akind="sans_b", acolor=INK),
                1200, 112 + dy, "l", a)
        put(frame, T(c.get("source", "Source: World Bank"), "sans", 20, (*INK, 130)), 104, H - 40, "l")
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# kinetic: oversized numbers in columns
# --------------------------------------------------------------------------- #
class Kinetic(Scene):
    dark = True
    flat = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.t_kick = self.when(c.get("kicker_at"), 0.25)
        self.heads = []
        after = 0.0
        for i, hl in enumerate(c.get("headline") or []):
            hl = hl if isinstance(hl, dict) else {"text": hl}
            tt = self.when(hl.get("at"), 0.4 + 0.6 * i, after=after)
            after = tt
            self.heads.append((hl["text"], tt))
        self.cols = []
        after = 0.0
        for cl in c.get("columns") or []:
            tc = self.when(cl.get("at"), after + 1.0, after=after)
            rows = []
            ra = tc
            for r in cl.get("rows") or []:
                tr = self.when(r.get("at"), ra + 0.7, after=tc - 0.05)
                ra = max(ra, tr)
                rows.append((r, tr))
            after = tc
            self.cols.append((cl, tc, rows))

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        X = 104
        first = self.heads[0][1] if self.heads else self.total
        if c.get("intro"):
            a = ease_out((t - 0.15) / 0.6) * (1 - ease_out((t - first + 0.5) / 0.45))
            if a > 0:
                put(frame, T(c["intro"], "serif", 190, IVORY), W / 2, H / 2 + 60, "c", a, 1 + 0.03 * t / max(1.0, first))
        self.kicker(frame, c.get("kicker", ""), X, 98, t, first - 0.3 if c.get("intro") else self.t_kick)
        for i, (txt, tt) in enumerate(self.heads):
            a, dy = rise(t, tt)
            put(frame, T(txt, "serif", 64, IVORY), X - 2, 182 + i * 72 + dy, "l", a)
        n = len(self.cols)
        top = 182 + len(self.heads) * 72 + 70
        colw = (W - 2 * X) / max(1, n)
        nrows = max((len(r) for _, _, r in self.cols), default=1)
        avail = H - 90 - top
        rowh = avail / nrows
        size = int(min(200, rowh * 0.78))
        d = ImageDraw.Draw(frame, "RGBA")
        for ci, (cl, tc, rows) in enumerate(self.cols):
            x = X + ci * colw + (40 if ci else 0)
            if ci:
                a = ease_out((t - tc) / 0.8)
                d.line([(X + ci * colw, top - 20), (X + ci * colw, top - 20 + (H - 110 - top) * a)],
                       fill=(*IVORY, 46), width=2)
            a, dy = rise(t, tc)
            put(frame, T(cl.get("title", ""), "serif_i", 48, GOLD), x, top + dy, "l", a)
            for ri, (r, tr) in enumerate(rows):
                y = top + 40 + ri * rowh
                a, dy = rise(t, tr - 0.25)
                put(frame, T(r.get("label", r.get("country", "")), "label", 22, col(r.get("country", ""), True)),
                    x, y + 30 + dy, "l", a)
                u = ease_out((t - tr) / 0.7)
                if u <= 0:
                    continue
                v = r["value"] * u
                fm = c.get("format") or {}
                txt = fmt(v, fm.get("prefix", ""), fm.get("suffix", ""), fm.get("decimals", 1), fm.get("sign", False))
                ink = IVORY if r.get("hot") else col(r.get("country", ""), True)
                drop = 16 * (1 - u) * (1 if r["value"] < 0 else -1)
                put(frame, T(txt, "num", size, ink), x - 6, y + 34 + size * 0.86 + drop, "l", min(1, u * 2.5))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# district: isometric factory districts
# --------------------------------------------------------------------------- #
S_ISO = 40.0
A_ISO, B_ISO = math.cos(math.radians(30)) * S_ISO, 0.5 * S_ISO
WALL_L, WALL_R = (0.90, 0.875, 0.83), (0.74, 0.71, 0.665)
GLASS = (0.97, 0.95, 0.90)
ROOF = {"Bangladesh": (0.56, 0.15, 0.22), "Pakistan": (0.20, 0.32, 0.54), "India": (0.76, 0.40, 0.17)}


def _iso(ox, oy, i, j, z=0.0):
    return ox + (i - j) * A_ISO, oy + (i + j) * B_ISO - z


def _quad(c, pts):
    c.move_to(*pts[0])
    for p in pts[1:]:
        c.line_to(*p)
    c.close_path()


def building_sprite(i: int, j: int, h: float, roof: tuple, chimney: bool) -> tuple[Image.Image, float, float]:
    """One sawtooth-roofed factory as a sprite; returns (img, x, y) of its top-left in district space."""
    m = 0.14
    i0, j0, i1, j1 = i + m, j + m, i + 1 - m, j + 1 - m
    rh = S_ISO * 0.22
    top_z = h + (S_ISO * 0.9 if chimney else rh)
    xs = [_iso(0, 0, a, b)[0] for a in (i0, i1) for b in (j0, j1)]
    bx0, bx1 = min(xs) - 4, max(xs) + 4
    by0 = _iso(0, 0, i0, j0, top_z)[1] - 4
    by1 = _iso(0, 0, i1, j1)[1] + 4
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(bx1 - bx0) + 2, int(by1 - by0) + 2)
    c = cairo.Context(s)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    ox, oy = -bx0, -by0
    p = lambda a, b, z=0: _iso(ox, oy, a, b, z)  # noqa: E731
    _quad(c, [p(i0, j1), p(i1, j1), p(i1, j1, h), p(i0, j1, h)])
    c.set_source_rgb(*WALL_L)
    c.fill()
    _quad(c, [p(i1, j0), p(i1, j1), p(i1, j1, h), p(i1, j0, h)])
    c.set_source_rgb(*WALL_R)
    c.fill()
    for k in range(4):
        a0 = i0 + (k + 0.25) * (i1 - i0) / 4
        a1 = a0 + 0.5 * (i1 - i0) / 4
        _quad(c, [p(a0, j1, h * 0.35), p(a1, j1, h * 0.35), p(a1, j1, h * 0.68), p(a0, j1, h * 0.68)])
        c.set_source_rgb(0.62, 0.60, 0.56)
        c.fill()
    for k in range(3):
        a0 = j0 + k * (j1 - j0) / 3
        a1 = a0 + (j1 - j0) / 3
        _quad(c, [p(i0, a1, h), p(i1, a1, h), p(i1, a0, h + rh), p(i0, a0, h + rh)])
        c.set_source_rgb(*roof)
        c.fill()
        _quad(c, [p(i1, a0, h), p(i1, a1, h), p(i1, a0, h + rh)])
        c.set_source_rgb(*[v * 0.72 for v in roof])
        c.fill()
        _quad(c, [p(i0, a0, h), p(i1, a0, h), p(i1, a0, h + rh), p(i0, a0, h + rh)])
        c.set_source_rgb(*GLASS)
        c.fill()
    if chimney:
        ci, cj, r = i0 + 0.15, j0 + 0.2, 0.07
        _quad(c, [p(ci - r, cj + r, h), p(ci + r, cj + r, h), p(ci + r, cj + r, h + S_ISO * 0.9), p(ci - r, cj + r, h + S_ISO * 0.9)])
        c.set_source_rgb(*WALL_L)
        c.fill()
        _quad(c, [p(ci + r, cj - r, h), p(ci + r, cj + r, h), p(ci + r, cj + r, h + S_ISO * 0.9), p(ci + r, cj - r, h + S_ISO * 0.9)])
        c.set_source_rgb(*WALL_R)
        c.fill()
    return carto.to_img(s), bx0, by0


def shadow_sprite(i: int, j: int, h: float) -> tuple[Image.Image, float, float]:
    from PIL import ImageFilter

    d = h / S_ISO * 0.9
    pts = [_iso(0, 0, i + 0.14, j + 0.14), _iso(0, 0, i + 0.86 + d, j + 0.14 - d * 0.2),
           _iso(0, 0, i + 0.86 + d, j + 0.86 - d * 0.2), _iso(0, 0, i + 0.14, j + 0.86)]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    bx0, by0 = min(xs) - 14, min(ys) - 14
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(max(xs) - bx0) + 16, int(max(ys) - by0) + 16)
    c = cairo.Context(s)
    _quad(c, [(x - bx0, y - by0) for x, y in pts])
    c.set_source_rgba(0.25, 0.2, 0.15, 0.30)
    c.fill()
    return carto.to_img(s).filter(ImageFilter.GaussianBlur(6)), bx0, by0


class District(Scene):
    dark = False
    flat = True
    COLS = 10

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.ents = list(c.get("entities") or [])
        self.unit = float(c.get("unit", 1e9))
        origins = c.get("origins") or {self.ents[0]: [560, 530], self.ents[1]: [1390, 530]}
        self.origin = {e: tuple(origins[e]) for e in self.ents}
        # year per frame, like the race
        knots = [(0.0, float(c["keys"][0]["year"]))]
        after = 0.0
        for kk in c.get("keys") or []:
            tt = self.when(kk.get("at"), -1, after=after)
            if tt < 0:
                continue
            after = tt
            knots.append((tt, float(kk["year"])))
        n = int(round(self.total * FPS)) + 2
        self.year = np.empty(n)
        for f in range(n):
            t = f / FPS
            yv = knots[-1][1]
            for (t0, y0), (t1, y1) in zip(knots, knots[1:]):
                if t <= t1:
                    u = (t - t0) / max(1e-6, t1 - t0)
                    yv = y0 + (y1 - y0) * (0.4 * u + 0.6 * ease_in_out(u))
                    break
            self.year[f] = yv
        self.count = {e: np.array([round(self.value(e, y) / self.unit) for y in self.year]) for e in self.ents}
        # per-building growth (0..1) per frame
        self.grow = {}
        for e in self.ents:
            nmax = int(self.count[e].max())
            g = np.zeros((n, nmax))
            p = np.zeros(nmax)
            for f in range(n):
                vis = np.arange(nmax) < self.count[e][f]
                p = np.where(vis, np.minimum(1, p + 1 / (FPS * 0.45)), np.maximum(0, p - 1 / (FPS * 0.3)))
                g[f] = p
            self.grow[e] = g
        rng = np.random.default_rng(7)
        self.sprites = {}
        for e in self.ents:
            nmax = self.grow[e].shape[1]
            ox, oy = self.origin[e]
            lst = []
            for kk in range(nmax):
                i, j = kk % self.COLS, kk // self.COLS
                h = S_ISO * rng.uniform(0.55, 0.8)
                img, bx, by = building_sprite(i, j, h, ROOF.get(e, (0.3, 0.3, 0.3)), rng.random() < 0.25)
                sh, sx, sy = shadow_sprite(i, j, h)
                lst.append((i, j, img, ox + bx, oy + by, sh, ox + sx, oy + sy))
            lst.sort(key=lambda q: (q[0] + q[1], q[0]))
            self.sprites[e] = lst
        self.ground = {}
        for e in self.ents:
            rows = max(1, math.ceil(self.grow[e].shape[1] / self.COLS))
            s, cc = surface()
            ox, oy = self.origin[e]
            pad = 0.35
            _quad(cc, [_iso(ox, oy, -pad, -pad), _iso(ox, oy, self.COLS + pad, -pad),
                       _iso(ox, oy, self.COLS + pad, rows + pad), _iso(ox, oy, -pad, rows + pad)])
            cc.set_source_rgb(0.885, 0.86, 0.81)
            cc.fill()
            self.ground[e] = carto.to_img(s)
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.t_deck = self.when(c.get("deck_at"), 1.0)

    def value(self, e: str, year: float) -> float:
        d = self.data.get(e, {})
        y0 = int(math.floor(year))
        v0 = d.get(y0, d.get(y0 - 1, 0.0))
        v1 = d.get(y0 + 1, v0)
        return v0 + (v1 - v0) * (year - y0)

    def frame(self, t: float) -> Image.Image:
        c = self.c
        f = min(len(self.year) - 1, int(round(t * FPS)))
        year = float(self.year[f])
        frame = self.canvas()
        ga = ease_out(t / 0.6)
        for e in self.ents:
            frame.alpha_composite(fx.with_alpha(self.ground[e], ga))
            g = self.grow[e][f]
            spr = self.sprites[e]
            for kk, (i, j, img, x, y, sh, sx, sy) in enumerate(spr):
                pass
            # shadows first, then buildings back to front
            idx = {(q[0], q[1]): n for n, q in enumerate(spr)}
            for (i, j, img, x, y, sh, sx, sy) in spr:
                u = g[j * self.COLS + i]
                if u > 0:
                    frame.alpha_composite(fx.with_alpha(sh, u), (int(sx), int(sy)))
            for (i, j, img, x, y, sh, sx, sy) in spr:
                u = g[j * self.COLS + i]
                if u <= 0:
                    continue
                k = fx.ease_back(u, 1.4)
                hh = max(1, int(img.height * k))
                im = img.resize((img.width, hh), Image.BICUBIC) if hh != img.height else img
                frame.alpha_composite(fx.with_alpha(im, min(1, u * 2)), (int(x), int(y + img.height - hh)))
            del idx
        # header numbers
        for e, cxp in zip(self.ents, c.get("number_x") or [630, 1476]):
            v = self.value(e, year) / self.unit
            a, dy = rise(t, 0.4)
            put(frame, T(c.get("names", {}).get(e, e), "label", 24, C.get(e, INK)), cxp, 316 + dy, "c", a)
            hot = v >= max(self.value(o, year) / self.unit for o in self.ents) - 1e-9
            put(frame, T(fmt(v, "$", "bn", 1), "num", 124, INK if hot else (70, 66, 60)), cxp, 432 + dy, "c", a)
        put(frame, T(str(int(round(year))), "serif_i", 76, GOLD_DK), 1046, 690, "c", ease_out(t / 0.6))
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        if c.get("deck"):
            a, dy = rise(t, self.t_deck)
            put(frame, para(c["deck"], "sans", 27, (*INK, 215), 560, 38, akind="sans_b", acolor=INK),
                1240, 112 + dy, "l", a)
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*INK, 140)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# bars: big horizontal bars with silhouettes
# --------------------------------------------------------------------------- #
class Bars(Scene):
    dark = False
    flat = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.rows = []
        after = 0.0
        for r in c.get("rows") or []:
            t1 = self.when(r.get("at"), after + 1.2, after=after)
            t2 = self.when(r.get("mark_at"), t1 + 2.0, after=t1) if r.get("mark") is not None else t1
            after = t1
            self.rows.append((r, t1, t2))
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.sil = {r["country"]: carto.silhouette(r["country"], 120) for r, _, _ in self.rows}

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        vmax = float(c.get("max", 100))
        X0, X1 = 520, 1450
        fm = c.get("format") or {}
        d = ImageDraw.Draw(frame, "RGBA")
        for ri, (r, t1, t2) in enumerate(self.rows):
            y = 340 + ri * 205
            a, dy = rise(t, min(t1 - 0.3, 0.5 + 0.3 * ri))
            if a <= 0:
                continue
            sil = self.sil[r["country"]]
            frame.alpha_composite(fx.with_alpha(sil, a), (int(110 + (130 - sil.width) / 2), int(y + dy)))
            put(frame, T(r.get("label", r["country"]), "label", 24, C.get(r["country"], INK)), 280, y + 68 + dy, "l", a)
            u1 = ease_out((t - t1) / 1.0)
            v = r["value"] * u1
            bw = (X1 - X0) * v / vmax
            d.rectangle([X0, y + 20, X0 + bw, y + 104], fill=C.get(r["country"], INK))
            mk = r.get("mark")
            if mk is not None and t >= t2:
                u = ease_out((t - t2) / 0.5)
                gx = X0 + (X1 - X0) * mk / vmax
                d.line([(gx, y + 20), (gx, y + 104)], fill=(*IVORY, int(230 * u)), width=3)
                d.line([(gx, y + 4), (gx, y + 20)], fill=(*INK, int(200 * u)), width=2)
                put(frame, T(r.get("mark_label", ""), "label", 18, (*INK, 200)), gx, y - 2, "c", u)
            if u1 > 0:
                txt = fmt(v, fm.get("prefix", ""), fm.get("suffix", ""), fm.get("decimals", 1))
                put(frame, T(txt, "num", 96, INK), X0 + bw + 26, y + 98, "l", min(1, u1 * 3))
        d.line([(X0, 320), (X0, 340 + len(self.rows) * 205 - 60)], fill=(*INK, 150), width=2)
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*INK, 140)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# ledger: who leads what
# --------------------------------------------------------------------------- #
class Ledger(Scene):
    dark = False
    flat = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.cols = []
        after = 0.0
        for cl in c.get("columns") or []:
            tc = self.when(cl.get("at"), after + 1.5, after=after)
            items = []
            ta = tc
            for it in cl.get("items") or []:
                ti = self.when(it.get("at"), ta + 1.0, after=ta)
                ta = ti
                items.append((it, ti))
            after = tc
            self.cols.append((cl, tc, items))
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.sil = {cl["country"]: carto.silhouette(cl["country"], 230) for cl, _, _ in self.cols}

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        d = ImageDraw.Draw(frame, "RGBA")
        for ci, (cl, tc, items) in enumerate(self.cols):
            x = 112 + ci * 568
            sil = self.sil[cl["country"]]
            pre = 0.22 * ease_out((t - 0.5 - 0.3 * ci) / 0.6)
            a, dy = rise(t, tc, 0.7)
            frame.alpha_composite(fx.with_alpha(sil, max(pre, a)), (int(x), int(270 + (230 - sil.height) + dy)))
            if a <= 0:
                continue
            put(frame, T(cl.get("label", cl["country"]), "label", 24, C.get(cl["country"], INK)), x, 556 + dy, "l", a)
            n_lit = sum(1 for _, ti in items if t >= ti)
            num = T(str(n_lit), "num", 190, INK)
            put(frame, num, x - 6, 712 + dy, "l", a)
            put(frame, T("Leads", "label", 22, (*INK, 150)), x + num.w + 14, 706 + dy, "l", a)
            d.line([(x, 742), (x + 480 * a, 742)], fill=(*INK, 60), width=2)
            if not items:
                put(frame, T(cl.get("empty", ""), "sans", 27, (*INK, 150)), x, 790, "l", ease_out((t - tc - 0.6) / 0.5))
            for ii, (it, ti) in enumerate(items):
                v, dy2 = rise(t, ti, 0.45)
                if v <= 0:
                    continue
                lab = T(it["label"] + " ", "sans", 27, INK)
                put(frame, lab, x, 790 + ii * 48 + dy2, "l", v)
                put(frame, T(it["value"], "sans_b", 27, INK), x + lab.w, 790 + ii * 48 + dy2, "l", v)
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*INK, 140)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# close: the last line, on the night map
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def pill(label: str, filled: bool, dark: bool = True) -> Image.Image:
    """A button. On dark scenes ivory (filled) or an ivory outline; on light
    scenes ink (filled) or an ink outline."""
    fg, bg = (IVORY, CHAR) if dark else (INK, IVORY)
    sp = T(label, "label", 26, bg if filled else fg)
    w, h = int(sp.w + 96), 82
    S = 2
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * S, h * S)
    c = cairo.Context(s)
    r = h * S / 2
    c.arc(r, r, r - 2 * S, math.pi / 2, 3 * math.pi / 2)
    c.arc(w * S - r, r, r - 2 * S, -math.pi / 2, math.pi / 2)
    c.close_path()
    if filled:
        c.set_source_rgb(*rgb1(fg)[:3])
        c.fill()
    else:
        c.set_source_rgba(*rgb1(fg, 0.9))
        c.set_line_width(2.5 * S)
        c.stroke()
    img = carto.to_img(s).resize((w, h), Image.LANCZOS)
    put(img, sp, w / 2, h / 2 + 9, "c")
    return img


class Close(Scene):
    dark = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.map = carto.night(c.get("map", "wide"))
        plate = with_flags(self.map, self.map.plate(), c).copy()
        plate.alpha_composite(self.map.lights())
        self.plate = plate
        self.cam = PlateCam(c.get("zoom0", 1.06), 1.0, (1270, 560), 0, self.total)
        self.shade = radial_scrim(W / 2, H * 0.42, W * 0.62, H * 0.62, 0.72, rgb=(10, 11, 13))
        self.t_kick = self.when(c.get("kicker_at"), 0.3)
        self.words = self.words  # keep for when()
        self.lines = []
        after = self.when(c.get("at"), 0.4) - 0.01
        last = after
        for li, line in enumerate(c.get("lines") or []):
            ws = []
            for w in line.split():
                tw = self.when(w, -1, after=last)
                if tw < 0 or tw - last > 4:
                    tw = last + 0.22
                last = tw
                ws.append((w, tw))
            self.lines.append(ws)
        q = c.get("question") or {}
        self.q = q
        self.t_q = self.when(q.get("at"), self.total + 1, after=last)
        self.t_legend = self.when(c.get("legend_at"), last + 0.6, after=last)
        self.t_sub = self.when((c.get("subscribe") or {}).get("at"), self.total + 1) if c.get("subscribe") else None
        self.t_share = self.when((c.get("share") or {}).get("at"), self.total + 1) if c.get("share") else None
        self.t_like = self.when((c.get("like") or {}).get("at"), self.total + 1) if c.get("like") else None

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.cam.frame(self.plate, t)
        frame.alpha_composite(self.shade)
        self.kicker(frame, c.get("kicker", ""), W / 2, 214, t, self.t_kick, align="c")
        size, lh = 132, 140
        for li, ws in enumerate(self.lines):
            sps = [T(w, "serif", size, IVORY) for w, _ in ws]
            space = F("serif", size).getlength(" ")
            tot = sum(s.w for s in sps) + space * (len(sps) - 1)
            x = W / 2 - tot / 2
            for (w, tw), sp in zip(ws, sps):
                a, dy = rise(t, tw - 0.08, 0.5)
                put(frame, sp, x, 380 + li * lh + dy * 1.2, "l", a)
                x += sp.w + space
        legend = c.get("legend") or []
        if legend:
            a = max(0.0, ease_out((t - self.t_legend) / 0.6))
            sps = [T(n, "label", 22, col(n, True)) for n in legend] if a > 0 else []
            gap = 80
            tot = sum(s.w for s in sps) + gap * (len(sps) - 1)
            x = W / 2 - tot / 2
            for k, sp in enumerate(sps):
                put(frame, sp, x, 626, "l", a)
                if k < len(sps) - 1:
                    ImageDraw.Draw(frame, "RGBA").ellipse([x + sp.w + gap / 2 - 3, 616, x + sp.w + gap / 2 + 3, 622],
                                                  fill=(*IVORY, int(120 * a)))
                x += sp.w + gap
        if self.q:
            a, dy = rise(t, self.t_q, 0.6)
            put(frame, T(self.q.get("text", ""), "serif_i", 64, GOLD), W / 2, 738 + dy, "c", a)
        buttons = [(self.t_sub, "Subscribe", True), (self.t_share, "Share", False)]
        if self.t_like is not None:
            buttons.insert(0, (self.t_like, "Like", False))
        step = 300 if len(buttons) == 3 else 340
        for k, (tt, label, filled) in enumerate(buttons):
            dx = (k - (len(buttons) - 1) / 2) * step
            if tt is None or t < tt:
                continue
            u = fx.ease_back((t - tt) / 0.5, 1.6)
            img = pill(label, filled)
            fx.paste(frame, img, W / 2 + dx, 880, min(1, (t - tt) / 0.25), max(0.4, u))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
class Title(Scene):
    """The opening titles. The night map comes up out of black, each country lights
    up as the narrator names it (city lights, a wash of its colour, its name), then
    the title card settles over the map.

    chart:
      kind: title
      map: wide
      countries:
      - {country: India, at: india, note: 1.46 billion people, dy: 60}
      beats:                            # optional captions before the countries light
      - {at: '1947', big: '1947', label: British India is partitioned}
      flags: 0.72                       # optional: each country fills with its flag as it lights
      title: The South Asia Race
      title_at: south asia race
      kicker: Data in Motion · India in Data
      versus: [India, Pakistan, Bangladesh]
      years: 1960 – 2025
    """
    dark = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.map = carto.night(c.get("map", "wide"))
        self.base = self.map.plate()
        self.cam = PlateCam(1.0, c.get("zoom", 1.09), tuple(c.get("focus", (1270, 600))), 0, self.total)
        self.countries = []
        after = 0.0
        for cd in c.get("countries") or []:
            tt = self.when(cd.get("at"), after + 1.5, after=after)
            after = tt
            n = cd["country"]
            fa = float(cd.get("flag", c.get("flags", 0)) or 0)
            fat = tuple(cd["flag_at"]) if cd.get("flag_at") else None
            flag = fx.with_alpha(self.map.flag_of(n, fat, float(c.get("flag_fit", 0.8))), fa) if fa > 0 else None
            self.countries.append((cd, tt, self.map.lights_of(n), self.map.edge(n), flag))
        self.flag_rest = float(c.get("flags_under_title", 0.3))
        self.t_title = self.when(c.get("title_at"), max(after + 2.0, self.total - 4.5), after=after)
        # captions before the countries light: a year or a number, and a line under it
        first = self.countries[0][1] if self.countries else self.t_title
        self.beats = []
        last = 0.0
        for bt in c.get("beats") or []:
            tb = self.when(bt.get("at"), -1, after=last)
            if 0 <= tb < first:
                self.beats.append((bt, tb))
                last = tb
        self.t_first = first
        self.beat_shade = h_scrim(((0, 0.78), (0.26, 0.5), (0.42, 0.0), (1, 0)))
        self.shade = radial_scrim(W / 2, H * 0.47, W * 0.62, H * 0.5, 0.8, rgb=(9, 10, 12))
        self.black = Image.new("RGBA", (W, H), (7, 8, 10, 255))
        self._settled: dict[int, Image.Image] = {}

    def _plate(self, t: float) -> Image.Image:
        """The map with the countries lit so far. Flags (if any) sit under each
        outline and its city lights, and dim when the title comes in."""
        done = 0
        for cd, tt, *_ in self.countries:
            if t - tt >= 1.4:
                done += 1
            else:
                break
        fk = round(1 - (1 - self.flag_rest) * ease_in_out((t - self.t_title + 0.2) / 1.2), 3)
        key = (done, fk)
        if key not in self._settled:
            pl = self.base.copy()
            for _, _, lights, edge, flag in self.countries[:done]:
                if flag is not None:
                    pl.alpha_composite(fx.with_alpha(flag, fk))
                pl.alpha_composite(edge)
                pl.alpha_composite(lights)
            self._settled = {key: pl}
        plate = self._settled[key]
        rest = [(tt, lights, edge, flag) for _, tt, lights, edge, flag in self.countries[done:] if t > tt]
        if not rest:
            return plate
        plate = plate.copy()
        for tt, lights, edge, flag in rest:
            u = ease_out((t - tt) / 1.4)
            if flag is not None:
                plate.alpha_composite(fx.with_alpha(flag, u * fk))
            plate.alpha_composite(fx.with_alpha(edge, u))
            plate.alpha_composite(fx.with_alpha(lights, u))
        return plate

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.cam.frame(self._plate(t), t)
        tt0 = self.t_title
        sh = ease_in_out((t - tt0 + 0.2) / 1.2)
        if sh > 0:
            frame.alpha_composite(fx.with_alpha(self.shade, sh))
        # country names on the map, gone when the title arrives
        out = 1 - ease_out((t - tt0 + 0.3) / 0.5)
        for cd, tt, *_ in self.countries:
            a, dy = rise(t, tt + 0.25, 0.7)
            a *= out
            if a <= 0:
                continue
            lon, lat = carto.COUNTRY_POINTS[cd["country"]]
            x, y = self.cam.pt(t, *self.map.proj(lon, lat))
            x += cd.get("dx", 0)
            y += cd.get("dy", 0) + dy
            name = T(cd.get("label", cd["country"]).upper(), "label", 30, col(cd["country"], True))
            note = T(cd["note"], "sans", 24, (*IVORY, 225)) if cd.get("note") else None
            # a soft dark halo, so the name reads over a bright flag
            put(frame, halo(name), x, y, "c", a * 0.9, sub=True)
            put(frame, name, x, y, "c", a, sub=True)
            if note:
                put(frame, halo(note), x, y + 36, "c", a * 0.9, sub=True)
                put(frame, note, x, y + 36, "c", a, sub=True)
        # opening captions, bottom left, each until the next (the last until a country lights)
        if self.beats:
            sa = ease_out((t - self.beats[0][1] + 0.3) / 0.8) * (1 - ease_out((t - self.t_first + 0.15) / 0.6))
            if sa > 0:
                frame.alpha_composite(fx.with_alpha(self.beat_shade, sa))
        for i, (bt, tb) in enumerate(self.beats):
            nxt = self.beats[i + 1][1] if i + 1 < len(self.beats) else self.t_first
            a, dy = rise(t, tb, 0.7)
            a *= 1 - ease_out((t - nxt + 0.15) / 0.45)
            if a <= 0:
                continue
            if bt.get("label"):
                put(frame, T(bt["label"], "label", 24, GOLD), 104, 700 + dy, "l", a)
            put(frame, T(str(bt.get("big", "")), "num", 112, IVORY), 98, 818 + dy, "l", a)
        # the title card
        self.kicker(frame, c.get("kicker", ""), W / 2, 380, t, tt0 + 0.15, align="c")
        words = str(c.get("title", "")).split()
        if words:
            sps = [T(w, "serif", 150, IVORY) for w in words]
            space = 150 * 0.26
            x = W / 2 - (sum(sp.w for sp in sps) + space * (len(sps) - 1)) / 2
            for i, sp in enumerate(sps):
                a, dy = rise(t, tt0 + 0.35 + 0.17 * i, 0.75)
                if a > 0:
                    put(frame, sp, x, 560 + dy * 1.4, "l", a)
                x += sp.w + space
        u = ease_in_out((t - tt0 - 0.9) / 0.9)
        if u > 0:
            half = 230 * u
            ImageDraw.Draw(frame, "RGBA").line([(W / 2 - half, 616), (W / 2 + half, 616)], fill=(*GOLD, 230), width=2)
        vs = c.get("versus") or []
        if vs:
            a, dy = rise(t, tt0 + 1.15, 0.6)
            if a > 0:
                parts = []
                for i, n in enumerate(vs):
                    if i:
                        parts.append(T("vs", "serif_i", 32, (*IVORY, 170)))
                    parts.append(T(n.upper(), "label", 30, col(n, True)))
                gap = 22
                x = W / 2 - (sum(p_.w for p_ in parts) + gap * (len(parts) - 1)) / 2
                for p_ in parts:
                    put(frame, p_, x, 682 + dy, "l", a)
                    x += p_.w + gap
        if c.get("years"):
            a, dy = rise(t, tt0 + 1.5, 0.6)
            put(frame, T(str(c["years"]), "serif_i", 40, GOLD), W / 2, 752 + dy, "c", a)
        # up out of black
        b = 1 - ease_out(t / 1.8)
        if b > 0:
            frame.alpha_composite(fx.with_alpha(self.black, b))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# track: the race, run on a track
# --------------------------------------------------------------------------- #
def _sprite(w: int, h: int, draw: Callable[[cairo.Context], None], S: int = 4) -> Image.Image:
    """A small antialiased cairo drawing, made big and scaled down."""
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * S, h * S)
    c = cairo.Context(sf)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    c.scale(S, S)
    draw(c)
    return carto.to_img(sf).resize((w, h), Image.LANCZOS)


@lru_cache(maxsize=16)
def runner_head(country: str) -> Image.Image:
    """The front of a runner's trail: a disc in the country's colour with its
    shape in ivory."""
    r = 31

    def draw(c):
        c.arc(r + 3, r + 3, r, 0, 2 * math.pi)
        c.set_source_rgb(*rgb1(C.get(country, INK))[:3])
        c.fill_preserve()
        c.set_source_rgba(*rgb1(IVORY, 1))
        c.set_line_width(3.5)
        c.stroke()

    img = _sprite(2 * r + 6, 2 * r + 6, draw)
    sil = carto.silhouette(country, 36, IVORY)
    img.alpha_composite(sil, (int((img.width - sil.width) / 2), int((img.height - sil.height) / 2)))
    return img


@lru_cache(maxsize=2)
def ghost_ring() -> Image.Image:
    r = 31

    def draw(c):
        c.arc(r + 3, r + 3, r, 0, 2 * math.pi)
        c.set_source_rgba(*rgb1(IVORY, 0.92))
        c.fill_preserve()
        c.set_source_rgba(*rgb1(INK, 0.6))
        c.set_line_width(2.6)
        c.set_dash([5, 5])
        c.stroke()

    return _sprite(2 * r + 6, 2 * r + 6, draw)


class Track(Scene):
    """Each lane is a country; its runner is the size of its economy, moving
    as the economy grows, year by year (real growth, compounded).

      rows:  [{country, growth: [yearly %, ...], rate: 7.8, at: <cue for the rate>}]
      years: [2021, 2025]            first and last year of growth
      run_at / run_to                cues when the run starts and ends
      axis_max: 50                   per cent, at the right end of the track
      ghost: {country, rate, label, at}    where a slower pace would have got it
      double: {text, at}             a gold bracket from the ghost to the runner
    """
    dark = False
    flat = True
    X0, X1 = 560, 1600
    LANES = (430, 600, 770)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.y0, self.y1 = (c.get("years") or [2021, 2025])[:2]
        self.n = self.y1 - self.y0 + 1
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.t_run = self.when(c.get("run_at"), 1.0)
        self.t_end = max(self.t_run + 4.0, self.when(c.get("run_to"), self.t_run + 8.0, after=self.t_run))
        self.rows = []
        after = 0.0
        for r in c.get("rows") or []:
            tr = self.when(r.get("at"), after + 1.0, after=after)
            after = tr
            cum = [0.0]
            idx = 1.0
            for g in r["growth"][: self.n]:
                idx *= 1 + g / 100
                cum.append((idx - 1) * 100)
            self.rows.append((r, tr, cum))
        self.vmax = float(c.get("axis_max", 50))
        g = c.get("ghost") or {}
        self.ghost = g
        self.t_ghost = self.when(g.get("at"), -1.0) if g else -1.0
        self.ghost_v = ((1 + float(g.get("rate", 0)) / 100) ** self.n - 1) * 100 if g else 0.0
        d = c.get("double") or {}
        self.double = d
        self.t_double = self.when(d.get("at"), -1.0, after=max(0.0, self.t_ghost)) if d else -1.0
        self.sil = {r["country"]: carto.silhouette(r["country"], 84) for r, _, _ in self.rows}

    def X(self, v: float) -> float:
        return self.X0 + (self.X1 - self.X0) * v / self.vmax

    def progress(self, t: float) -> float:
        """Years run so far (0 .. n), easing in at the gun and out at the line."""
        u = clamp((t - self.t_run) / (self.t_end - self.t_run))
        return self.n * (0.35 * u + 0.65 * ease_in_out(u))

    @staticmethod
    def at(cum: list[float], p: float) -> float:
        k = int(min(max(math.floor(p), 0), len(cum) - 2))
        return cum[k] + (cum[k + 1] - cum[k]) * clamp(p - k)

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        p = self.progress(t)
        L = self.LANES
        half = (L[1] - L[0]) / 2
        top, bot = L[0] - half, L[-1] + half
        ga = ease_out((t - 0.3) / 0.8)
        s, cx = surface()
        # the track: lane lines, the start line, distance marks
        for i in range(len(L) + 1):
            y = top + i * 2 * half
            cx.set_source_rgba(*rgb1(INK, 0.2 * ga))
            cx.set_line_width(1.6)
            cx.move_to(self.X0 - 30, y)
            cx.line_to(self.X1 + 40, y)
            cx.stroke()
        step = 10.0
        v = step
        while v <= self.vmax + 1e-6:
            x = self.X(v)
            cx.set_source_rgba(*rgb1(INK, 0.11 * ga))
            cx.set_line_width(1.4)
            cx.set_dash([3, 7])
            cx.move_to(x, top)
            cx.line_to(x, bot)
            cx.stroke()
            cx.set_dash([])
            v += step
        cx.set_source_rgba(*rgb1(INK, 0.75 * ga))
        cx.set_line_width(4)
        cx.move_to(self.X0, top)
        cx.line_to(self.X0, bot)
        cx.stroke()
        # trails
        heads = []
        for (r, tr, cum), y in zip(self.rows, L):
            v = self.at(cum, p)
            x = self.X(v)
            if x > self.X0 + 1:
                cx.set_source_rgba(*rgb1(C.get(r["country"], INK), ga))
                cx.rectangle(self.X0, y - 9, x - self.X0, 18)
                cx.fill()
            heads.append((r, x, y, v))
        # the bracket from the slower pace to the runner
        gx = self.X(self.ghost_v) if self.ghost else 0
        gy = L[[r["country"] for r, _, _ in self.rows].index(self.ghost["country"])] if self.ghost else 0
        ub = ease_out((t - self.t_double) / 0.8) if self.t_double >= 0 else 0
        hx = next((x for r, x, y, v in heads if self.ghost and r["country"] == self.ghost["country"]), gx)
        if ub > 0:
            yb = gy + 50
            x1 = gx + (hx - gx) * ub
            cx.set_source_rgba(*rgb1(GOLD_DK, 0.95))
            cx.set_line_width(2.6)
            cx.move_to(gx, yb - 9)
            cx.line_to(gx, yb)
            cx.line_to(x1, yb)
            if ub > 0.98:
                cx.line_to(x1, yb - 9)
            cx.stroke()
        frame.alpha_composite(carto.to_img(s))
        # distance labels
        put(frame, T(c.get("axis_label", "Economy, growth since 2020"), "label", 19, (*INK, 150)),
            self.X0, top - 52, "l", ga)
        v = step
        while v <= self.vmax + 1e-6:
            put(frame, T(f"+{v:.0f}%", "sans_m", 22, (*INK, 140)), self.X(v), top - 14, "c", ga)
            v += step
        # lane labels: shape, name, then the yearly rate when it is said
        for (r, tr, cum), y in zip(self.rows, L):
            sil = self.sil[r["country"]]
            frame.alpha_composite(fx.with_alpha(sil, ga), (int(104 + (100 - sil.width) / 2), int(y - sil.height / 2)))
            put(frame, T(r.get("label", r["country"]), "label", 24, C.get(r["country"], INK)), 236, y - 8, "l", ga)
            if r.get("rate") is not None:
                ar, dr = rise(t, tr, 0.5)
                num = T(f"{r['rate']:.1f}%", "num", 44, INK)
                put(frame, num, 234, y + 42 + dr, "l", ar)
                put(frame, T("a year", "sans", 24, (*INK, 160)), 234 + num.w + 10, y + 40 + dr, "l", ar)
        # the slower pace, a dashed ring in the lane
        if self.t_ghost >= 0 and t >= self.t_ghost:
            ag = ease_out((t - self.t_ghost) / 0.6)
            ring = ghost_ring()
            paste(frame, fx.with_alpha(ring, ag), gx - ring.width / 2, gy - ring.height / 2)
            put(frame, T(self.ghost.get("label", "Old pace"), "label", 17, (*INK, 170)), gx, gy - 46, "c", ag)
        # runners
        for r, x, y, v in heads:
            img = runner_head(r["country"])
            paste(frame, fx.with_alpha(img, ga), x - img.width / 2, y - img.height / 2)
            if t >= self.t_run:
                put(frame, T(fmt(v, "+", "%", 1), "sans_b", 28, INK), x, y - 44, "c",
                    ease_out((t - self.t_run) / 0.4), sub=True)
        if ub > 0 and self.double.get("text"):
            put(frame, T(self.double["text"], "serif_i", 30, GOLD_DK), (gx + hx) / 2, gy + 82, "c", ub)
        # the year being run
        if t >= self.t_run - 0.3:
            yr = self.y0 + min(self.n - 1, int(p)) if p < self.n else self.y1
            ay = ease_out((t - self.t_run + 0.3) / 0.5)
            put(frame, T(str(yr), "serif_i", 76, GOLD_DK), W - 104, 212, "r", ay)
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*INK, 140)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# people: out of every hundred
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=32)
def person_icon(rgb: tuple, a: float = 1.0) -> Image.Image:
    """A pictogram of a woman: head and an A-line dress."""
    def draw(c):
        c.set_source_rgba(*rgb1(rgb, a))
        c.arc(15, 7.2, 6.4, 0, 2 * math.pi)
        c.fill()
        c.move_to(10.6, 15.5)
        c.line_to(19.4, 15.5)
        c.curve_to(21.5, 15.5, 22.4, 17, 23, 19)
        c.line_to(26.5, 33.5)
        c.line_to(3.5, 33.5)
        c.line_to(7, 19)
        c.curve_to(7.6, 17, 8.5, 15.5, 10.6, 15.5)
        c.close_path()
        c.fill()
        c.rectangle(10.6, 33, 3.2, 10)
        c.rectangle(16.2, 33, 3.2, 10)
        c.fill()

    return _sprite(30, 44, draw)


class People(Scene):
    """Ten-by-ten grids of figures, one grid per country, filling to a share.

      rows: [{country, value: 32.4, at, mark: 26.5, mark_at, mark_text: '+6 since 2019'}]
      unit: '%'
    The figures added since ``mark`` turn gold when it is said."""
    dark = False
    flat = True
    PX, PY = 46, 50
    GOLD_ON = (184, 138, 52)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.t_head = self.when(c.get("headline_at"), 0.2)
        self.rows = []
        after = 0.0
        for r in c.get("rows") or []:
            t1 = self.when(r.get("at"), after + 1.2, after=after)
            t2 = self.when(r.get("mark_at"), -1.0, after=t1) if r.get("mark") is not None else -1.0
            after = t1
            self.rows.append((r, t1, t2))
        gw = 9 * self.PX + 30
        gap = 150
        n = len(self.rows)
        x0 = (W - (n * gw + (n - 1) * gap)) / 2
        self.gx = [x0 + i * (gw + gap) for i in range(n)]
        self.gy = 452
        # bottom row first, left to right, so the share rises like a level
        self.order = [(i, j) for j in range(9, -1, -1) for i in range(10)]

    FILL = 1.6

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        a, dy = rise(t, self.t_head)
        self.kicker(frame, c.get("kicker", ""), 104, 124 + dy, t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 80, INK), 100, 212 + dy, "l", a)
        unit = c.get("unit", "%")
        faint = person_icon(INK, 0.12)
        for k, ((r, t1, t2), x0) in enumerate(zip(self.rows, self.gx)):
            ga, gdy = rise(t, min(t1 - 0.6, 0.6 + 0.25 * k), 0.6)
            if ga <= 0:
                continue
            n = int(round(r["value"]))
            m = int(r["mark"]) if r.get("mark") is not None else n
            full = person_icon(C.get(r["country"], INK))
            gold = person_icon(self.GOLD_ON)
            u = clamp((t - t1) / self.FILL)
            lit_f = n * u
            gu = ease_out((t - t2) / 0.7) if t2 >= 0 else 0.0
            for q, (i, j) in enumerate(self.order):
                x, y = x0 + i * self.PX, self.gy + j * self.PY + gdy
                frame.alpha_composite(fx.with_alpha(faint, ga), (int(x), int(y)))
                if q < n and lit_f > q:
                    pa = clamp((lit_f - q) / 2.5)
                    frame.alpha_composite(fx.with_alpha(full, pa), (int(x), int(y)))
                    if q >= m and gu > 0:
                        frame.alpha_composite(fx.with_alpha(gold, gu * pa), (int(x), int(y)))
            # name and the share, counting up as the grid fills
            put(frame, T(r.get("label", r["country"]), "label", 24, C.get(r["country"], INK)), x0, 330 + gdy, "l", ga)
            if t >= t1:
                num = T(fmt(r["value"] * ease_out(u), "", unit, 1), "num", 84, INK)
                put(frame, num, x0 - 4, 420 + gdy, "l", min(1.0, (t - t1) / 0.3))
                if gu > 0 and r.get("mark_text"):
                    full_num = T(fmt(r["value"], "", unit, 1), "num", 84, INK)
                    put(frame, T(r["mark_text"], "serif_i", 30, self.GOLD_ON), x0 + full_num.w + 14, 410 + gdy, "l", gu)
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*INK, 140)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


# --------------------------------------------------------------------------- #
# lifeline: years of life on an age ruler
# --------------------------------------------------------------------------- #
class Lifeline(Scene):
    """An age ruler; each country's line grows to its old value, then on to today's.

      from_label: '1980'   from_at: <cue>      the old values all appear then
      to_label: Today
      rows: [{country, from: 53.6, to: 72.2, at: <cue for today>, bracket_at, bracket: '+18.6 years',
              tag: 'Led in 1980', tag_at}]
      age_max: 80
    """
    dark = True
    flat = True
    X0, X1 = 456, 1660
    LANES = (506, 676, 846)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        c = self.c
        self.t_head = self.when(c.get("headline_at"), 0.4)
        self.t_from = self.when(c.get("from_at"), 1.5)
        self.rows = []
        after = self.t_from
        for r in c.get("rows") or []:
            t1 = self.when(r.get("at"), after + 1.5, after=after)
            tb = self.when(r.get("bracket_at"), -1.0, after=t1) if r.get("bracket") else -1.0
            tg = self.when(r.get("tag_at"), -1.0, after=self.t_from) if r.get("tag") else -1.0
            after = t1
            self.rows.append((r, t1, tb, tg))
        self.amax = float(c.get("age_max", 80))
        self.sil = {r["country"]: carto.silhouette(r["country"], 64, col(r["country"], True)) for r, *_ in self.rows}

    def X(self, age: float) -> float:
        return self.X0 + (self.X1 - self.X0) * age / self.amax

    def frame(self, t: float) -> Image.Image:
        c = self.c
        frame = self.canvas()
        self.kicker(frame, c.get("kicker", ""), 104, 98, t, 0.2)
        a, dy = rise(t, self.t_head)
        put(frame, T(c.get("headline", ""), "serif", 64, IVORY), 102, 182 + dy, "l", a)
        ga = ease_out((t - 0.3) / 0.8)
        top = 356
        s, cx = surface()
        # the ruler
        cx.set_source_rgba(*rgb1(IVORY, 0.5 * ga))
        cx.set_line_width(2)
        cx.move_to(self.X0, top)
        cx.line_to(self.X1, top)
        cx.stroke()
        for age in range(0, int(self.amax) + 1, 5):
            x = self.X(age)
            major = age % 10 == 0
            cx.set_source_rgba(*rgb1(IVORY, (0.5 if major else 0.3) * ga))
            cx.set_line_width(2 if major else 1.4)
            cx.move_to(x, top)
            cx.line_to(x, top + (14 if major else 8))
            cx.stroke()
            if major and age:
                cx.set_source_rgba(*rgb1(IVORY, 0.06 * ga))
                cx.set_line_width(1.4)
                cx.move_to(x, top + 30)
                cx.line_to(x, self.LANES[-1] + 60)
                cx.stroke()
        heads = []
        for (r, t1, tb, tg), y in zip(self.rows, self.LANES):
            k = self.rows.index((r, t1, tb, tg))
            rgb = col(r["country"], True)
            u0 = ease_in_out((t - self.t_from - 0.25 * k) / 1.3)
            u1 = ease_in_out((t - t1) / 1.2)
            x_old = self.X(r["from"] * u0)
            # the old life, thin and dim
            if u0 > 0:
                cx.set_source_rgba(*rgb1(rgb, 0.42))
                cx.set_line_width(6)
                cx.move_to(self.X0, y)
                cx.line_to(x_old, y)
                cx.stroke()
            # the years gained since, bright
            if u1 > 0:
                x_new = self.X(r["from"] + (r["to"] - r["from"]) * u1)
                cx.set_source_rgba(*rgb1(rgb, 1))
                cx.set_line_width(14)
                cx.set_line_cap(cairo.LINE_CAP_BUTT)
                cx.move_to(self.X0, y)
                cx.line_to(x_new, y)
                cx.stroke()
                cx.set_line_cap(cairo.LINE_CAP_ROUND)
                cx.arc(x_new, y, 12, 0, 2 * math.pi)
                cx.fill()
                heads.append((r, x_new, y, u1))
            if u0 > 0:
                # where it stood then: a ring that stays
                cx.set_source_rgba(*rgb1(IVORY, 0.9 * min(1.0, u0 * 3)))
                cx.set_line_width(2.6)
                cx.new_sub_path()
                cx.arc(x_old, y, 11, 0, 2 * math.pi)
                cx.stroke()
            if tb >= 0 and t >= tb:
                ub = ease_out((t - tb) / 0.7)
                xa, xb = self.X(r["from"]), self.X(r["to"])
                yb = y - 40
                cx.set_source_rgba(*rgb1(GOLD, 0.95))
                cx.set_line_width(2.6)
                cx.move_to(xa, yb + 10)
                cx.line_to(xa, yb)
                cx.line_to(xa + (xb - xa) * ub, yb)
                if ub > 0.98:
                    cx.line_to(xb, yb + 10)
                cx.stroke()
        frame.alpha_composite(carto.to_img(s))
        # ruler labels
        for age in range(10, int(self.amax) + 1, 10):
            put(frame, T(str(age), "sans_m", 22, (*IVORY, 150)), self.X(age), top - 16, "c", ga)
        put(frame, T(c.get("axis_label", "Age"), "label", 19, (*IVORY, 150)), self.X0, top - 16, "l", ga)
        # keys: then and now
        ka = ease_out((t - self.t_from) / 0.6)
        if ka > 0:
            d = ImageDraw.Draw(frame)
            to_l = T(str(c.get("to_label", "Today")), "label", 19, (*IVORY, int(200 * ka)))
            fr_l = T(str(c.get("from_label", "")), "label", 19, (*IVORY, int(200 * ka)))
            xr = self.X1 + 60
            put(frame, to_l, xr, 288, "r")
            xb = xr - to_l.w - 14
            d.rectangle([xb - 34, 280, xb, 288], fill=(*IVORY, int(230 * ka)))
            xf = xb - 34 - 40
            put(frame, fr_l, xf, 288, "r")
            xc = xf - fr_l.w - 22
            d.ellipse([xc - 9, 275, xc + 9, 293], outline=(*IVORY, int(230 * ka)), width=3)
        for (r, t1, tb, tg), y in zip(self.rows, self.LANES):
            rgb = col(r["country"], True)
            sil = self.sil[r["country"]]
            frame.alpha_composite(fx.with_alpha(sil, ga), (int(104 + (90 - sil.width) / 2), int(y - sil.height / 2)))
            put(frame, T(r.get("label", r["country"]), "label", 24, rgb), 214, y + 9, "l", ga)
            k = [q[0] for q in self.rows].index(r)
            u0 = ease_out((t - self.t_from - 0.25 * k - 0.9) / 0.5)
            if u0 > 0 and t < t1 + 0.6:
                put(frame, T(fmt(r["from"], decimals=1), "sans_b", 26, (*IVORY, 200)), self.X(r["from"]), y + 46, "c",
                    u0 * (1 - ease_out((t - t1) / 0.5)))
            if tb >= 0 and t >= tb:
                ub = ease_out((t - tb - 0.3) / 0.6)
                put(frame, T(r["bracket"], "serif_i", 32, GOLD), (self.X(r["from"]) + self.X(r["to"])) / 2, y - 54, "c", ub)
            if tg >= 0 and t >= tg:
                ug = ease_out((t - tg) / 0.6)
                put(frame, T(r["tag"], "serif_i", 30, (*IVORY, 210)), self.X(r["from"]), y - 30, "c", ug)
        for r, x, y, u1 in heads:
            v = r["from"] + (r["to"] - r["from"]) * u1
            put(frame, T(fmt(v, decimals=1), "num", 54, IVORY if r.get("hot") else col(r["country"], True)),
                x + 30, y + 19, "l", min(1.0, u1 * 3))
        if c.get("note"):
            put(frame, T(c["note"], "sans", 21, (*IVORY, 130)), 104, H - 40, "l", ease_out(t / 0.8))
        self.brand(frame)
        return frame


KINDS: dict[str, type[Scene]] = {"title": Title, "reveal": Reveal, "terrain": Terrain, "race": Race, "kinetic": Kinetic,
                                 "district": District, "bars": Bars, "ledger": Ledger, "close": Close,
                                 "track": Track, "people": People, "lifeline": Lifeline}


def make_scene(chart: dict[str, Any], cues, offset: float, total: float, data=None) -> Scene:
    kind = chart.get("kind")
    if kind not in KINDS:
        raise ValueError(f"doc scene kind must be one of {', '.join(KINDS)}")
    return KINDS[kind](chart, cues, offset, total, data)


def render_doc(chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
               out_path: Path, ffmpeg: str, footer: str = "Data in Motion", source: str = "World Bank",
               encode_args: list[str] | None = None, data: dict[str, dict[int, float]] | None = None,
               progress: Callable[[int, int], None] | None = None, preview: Path | None = None) -> float:
    scene = make_scene(chart, cues, offset, total, data)
    enc = fx.Encoder(out_path, ffmpeg, encode_args)
    n_frames = int(round(total * FPS))
    try:
        for f in range(n_frames):
            img = scene.render(f / FPS)
            enc.write(img)
            if progress:
                progress(f, n_frames)
            if preview is not None and (f % 45 == 0 or f == n_frames - 1):
                _save_preview(img, preview)
    finally:
        enc.close()
    return n_frames / FPS


def _save_preview(img: Image.Image, path: Path) -> None:
    """The frame just drawn, small, for the dashboard's live view."""
    try:
        tmp = path.with_suffix(".tmp.jpg")
        img.convert("RGB").resize((768, 432), Image.BILINEAR).save(tmp, quality=82)
        tmp.replace(path)
    except OSError:
        pass
