"""If Betelgeuse replaced the Sun: a size ladder from Earth to a red supergiant.

The camera pulls back in one continuous log-scale move: Earth, Jupiter, the
Sun, Sirius A, Arcturus, Rigel, Betelgeuse. Each body sits beside the one
before it, to scale, and the pull-back is a pure zoom about a fixed point, so
the last body shrinks smoothly into the corner while the next one fills the
frame. Then Betelgeuse is put where the Sun is: seen from above the planets'
plane, it grows out from the centre and swallows Mercury, Venus, Earth, Mars
and the asteroid belt, each on the spoken word, stopping short of Jupiter.

Hook: the first frame is that finished picture with the question, then it
rewinds (the star shrinks back to the Sun) and dives into Earth.

Honest numbers (radii): Earth 6,371 km and Jupiter 69,911 km (NASA mean radii);
the Sun 695,700 km (IAU nominal); Sirius A 1.711 R_sun (Davis et al. 2011,
interferometry); Arcturus 25.4 R_sun (Ramirez & Allende Prieto 2011); Rigel
78.9 R_sun (Moravveji et al. 2012); Betelgeuse 764 (+116/-62) R_sun (Joyce et
al. 2020), said as "about 760". 760 R_sun = 3.53 AU: past Mars (1.52 AU) and
the asteroid belt (2.2-3.3 AU), short of Jupiter (5.20 AU). Planet sizes in the
top-down view are enlarged so they can be seen; orbits and the star are to
scale. Star surfaces are illustrated (granulation from cellular noise, colour
from temperature, limb darkening).
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy.interpolate import PchipInterpolator

from . import canvas as cv
from . import kit
from . import sound as snd
from . import space as sp
from . import space3d as s3
from . import voice
from .canvas import GOLD, MUTED, WHITE, H, W, scale

FPS = 60
VOICE, RATE = "en-US-AndrewNeural", "+0%"   # the Space in Motion voice
RSUN = 695_700.0               # km
AU_KM = 149_597_870.7
CY = 1060.0                    # bodies' centre line (ladder) and the star's centre (top-down)
TOP_LABEL_Y, READ_Y = 140, 218
HOOK_T0 = -0.45
HOOK_YS = (178, 256, 334)

HOOK = [[("If", WHITE), ("Betelgeuse", WHITE)],
        [("replaced", WHITE), ("the", WHITE), ("Sun,", WHITE)],
        [("it", WHITE), ("would", WHITE), ("swallow", GOLD), ("Mars.", GOLD)]]

SCRIPT = {
    "hook": ("If Betelgeuse replaced the Sun, it would swallow Mars.", None),
    "earth": ("Start with Earth. Jupiter is 11 Earths wide.",
              [("Start with Earth", 3), ("Jupiter is", 2), ("*11 Earths* wide", 3)]),
    "sun": ("The Sun: 109 Earths across.", [("The Sun:", 2), ("*109 Earths* across", 3)]),
    "sirius": ("Sirius, the brightest star in our night sky: 1.7 Suns.",
               [("Sirius,", 1), ("the brightest star", 3), ("in our night sky:", 4), ("*1.7 Suns*", 2)]),
    "arcturus": ("Arcturus: 25 Suns.", [("Arcturus:", 1), ("*25 Suns*", 2)]),
    "rigel": ("Rigel: 79.", [("Rigel:", 1), ("*79*", 1)]),
    "betel": ("And Betelgeuse: about 760 Suns across.",
              [("And Betelgeuse:", 2), ("about *760 Suns*", 3), ("across", 1)]),
    "payoff": ("Put it where the Sun is, and it would swallow Mercury, Venus, Earth, Mars, and the asteroid belt.",
               [("Put it where", 3), ("the Sun is,", 3), ("and it would swallow", 4), ("Mercury,", 1),
                ("Venus,", 1), ("Earth,", 1), ("*Mars,*", 1), ("and the asteroid belt", 4)]),
}

# key, label, radius (km), ratio label, kind, framed radius (px), framed centre x (fraction of W)
LADDER = [
    ("earth", "EARTH", 6_371.0, None, "planet", 220, 0.50),
    ("jupiter", "JUPITER", 69_911.0, "11 × Earth", "planet", 250, 0.56),
    ("sun", "THE SUN", RSUN, "109 × Earth", "sun", 250, 0.56),
    ("sirius", "SIRIUS", 1.711 * RSUN, "1.7 × Sun", "star", 250, 0.62),
    ("arcturus", "ARCTURUS", 25.4 * RSUN, "25 × Sun", "star", 262, 0.56),
    ("rigel", "RIGEL", 78.9 * RSUN, "79 × Sun", "star", 266, 0.56),
    ("betelgeuse", "BETELGEUSE", 760.0 * RSUN, "760 × Sun", "star", 300, 0.56),
]
LINE_OF = {"jupiter": "earth", "sun": "sun", "sirius": "sirius", "arcturus": "arcturus",
           "rigel": "rigel", "betelgeuse": "betel"}
WORD_OF = {"jupiter": "Jupiter", "sun": "Sun", "sirius": "Sirius", "arcturus": "Arcturus",
           "rigel": "Rigel", "betelgeuse": "Betelgeuse"}
TRANS_DUR = {"jupiter": 1.15, "sun": 1.15, "sirius": 1.0, "arcturus": 1.15, "rigel": 1.05, "betelgeuse": 1.7}

# Star looks: colour ramp by brightness (dark lanes red, hot cells white, like a
# glowing body), limb darkening u, texture contrast (lo, hi), glow colour and gain.
STARS = {
    "sirius": dict(ramp=[(0.0, (40, 60, 120)), (0.35, (120, 150, 230)), (0.62, (196, 214, 255)),
                         (0.85, (226, 236, 255)), (1.0, (246, 250, 255))],
                   u=0.72, lo=0.68, hi=1.0, glow=(185, 205, 255), gain=0.75),
    "arcturus": dict(ramp=[(0.0, (70, 18, 4)), (0.3, (180, 72, 22)), (0.55, (240, 136, 58)),
                           (0.78, (255, 184, 104)), (0.92, (255, 220, 160)), (1.0, (255, 240, 210))],
                     u=0.55, lo=0.62, hi=1.0, glow=(255, 170, 105), gain=0.6),
    "rigel": dict(ramp=[(0.0, (30, 50, 120)), (0.35, (105, 140, 235)), (0.62, (182, 204, 255)),
                        (0.85, (214, 228, 255)), (1.0, (238, 245, 255))],
                  u=0.72, lo=0.68, hi=1.0, glow=(165, 192, 255), gain=0.7),
    "betelgeuse": dict(ramp=[(0.0, (50, 6, 2)), (0.25, (140, 30, 8)), (0.45, (210, 70, 22)),
                             (0.65, (250, 122, 48)), (0.82, (255, 172, 88)), (0.94, (255, 214, 140)),
                             (1.0, (255, 236, 190))],
                       u=0.6, lo=0.36, hi=1.0, glow=(255, 108, 58), gain=0.6),
}
SUN_GLOW = (255, 214, 160)

# Top-down view: K px per AU, looking down ELEV at the planets' plane.
K = 94.0
ELEV = math.radians(24.0)
SIN_E = math.sin(ELEV)
R_FULL = 760.0 * RSUN / AU_KM          # 3.53 AU
R_SUN_AU = RSUN / AU_KM
SUN_MIN_PX = 16.0
# name, orbit (AU), start angle (deg, 0 = right, negative = towards us), drawn radius px
PLANETS = [("mercury", 0.387, -100.0, 5.5), ("venus", 0.723, -35.0, 8.5), ("earth", 1.0, -128.0, 9.5),
           ("mars", 1.524, -62.0, 7.5), ("jupiter", 5.203, 160.0, 17.0)]
EARTH_PX = 220.0
KEY = np.array([-0.55, 0.5, -0.7])
LADDER_PHI = math.radians(14.0)
EARTH_POLE = (math.sin(math.radians(23.4)), 0.0, math.cos(math.radians(23.4)))


def omega(a: float) -> float:
    """Slow orbital drift (rad/s), Kepler-shaped: inner planets move faster."""
    return 0.06 * a ** -1.5


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


# --------------------------------------------------------------------------- #
# Star surfaces: cellular noise on the sphere (no seams, no pinched poles)
# --------------------------------------------------------------------------- #
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "star_tex"
TEX_VER = 5


def _sphere_points(w: int, h: int) -> np.ndarray:
    lon = (np.arange(w) + 0.5) / w * 2 * math.pi
    lat = (0.5 - (np.arange(h) + 0.5) / h) * math.pi
    lo, la = np.meshgrid(lon, lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1).reshape(-1, 3)


def _cells(P: np.ndarray, n: int, rng, sharp: float) -> np.ndarray:
    """Convection cells: bright centres, dark lanes between them (0..1)."""
    from scipy.spatial import cKDTree

    seeds = rng.normal(size=(n, 3))
    seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
    d, i = cKDTree(seeds).query(P, k=2, workers=-1)
    spacing = math.sqrt(4 * math.pi / n)
    lane = (d[:, 1] - d[:, 0]) / spacing
    bright = rng.uniform(0.0, 1.0, n)[i[:, 0]]
    centre = np.clip(1 - (d[:, 0] / (spacing * 0.8)) ** 2, 0, 1)
    return (0.4 + 0.6 * bright) * (1 - np.exp(-lane / sharp)) * (0.72 + 0.28 * centre)


def _blobs(P: np.ndarray, n: int, rng, width: float) -> np.ndarray:
    c = rng.normal(size=(n, 3))
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    out = np.zeros(len(P))
    for k in range(n):
        d2 = np.sum((P - c[k]) ** 2, axis=1)
        out += rng.uniform(-1, 1) * np.exp(-d2 / (width * rng.uniform(0.6, 1.4)) ** 2)
    return out


def _make_tex(name: str) -> np.ndarray:
    w = {"betelgeuse": 2048, "arcturus": 1536}.get(name, 1024)
    h = w // 2
    P = _sphere_points(w, h)
    rng = np.random.default_rng({"sirius": 11, "arcturus": 12, "rigel": 13, "betelgeuse": 14}[name])
    if name == "betelgeuse":
        v = (0.55 * _cells(P, 34, rng, 0.2) + 0.26 * _cells(P, 300, rng, 0.18)
             + 0.12 * _cells(P, 3200, rng, 0.2) + 0.22 * _blobs(P, 9, rng, 0.55))
    elif name == "arcturus":
        v = 0.55 * _cells(P, 900, rng, 0.16) + 0.3 * _cells(P, 7000, rng, 0.2) + 0.12 * _blobs(P, 8, rng, 0.5)
    else:
        v = 0.45 * _blobs(P, 10, rng, 0.45) + 0.55 * _cells(P, 9000, rng, 0.25)
    lo, hi = np.percentile(v, [0.5, 99.6])
    v = np.clip((v - lo) / (hi - lo), 0, 1).reshape(h, w)
    # Soften: a star's surface is plasma, not cracked rock.
    from scipy.ndimage import gaussian_filter
    blur = {"betelgeuse": 6.0, "arcturus": 3.0}.get(name, 1.5) * w / 2048
    v = gaussian_filter(v, (blur, blur), mode=("nearest", "wrap"))
    lo, hi = np.percentile(v, [0.3, 99.8])
    v = np.clip((v - lo) / (hi - lo), 0, 1)
    return (v * 255).astype(np.uint8)


def _tex_from(arr: np.ndarray) -> s3.Texture:
    t = s3.Texture.__new__(s3.Texture)
    a = arr.astype(np.float32)[..., None]
    t.levels = [a]
    while a.shape[1] > 64:
        hh, ww = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
        a = a[:hh, :ww].reshape(hh // 2, 2, ww // 2, 2, 1).mean(axis=(1, 3))
        t.levels.append(a)
    return t


@lru_cache(maxsize=1)
def star_textures() -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in STARS:
        f = CACHE / f"{name}_v{TEX_VER}.png"
        if not f.exists():
            tmp = f.with_suffix(f".{os.getpid()}.png")
            Image.fromarray(_make_tex(name)).save(tmp)
            os.replace(tmp, f)
        out[name] = _tex_from(np.asarray(Image.open(f).convert("L")))
    return out


def _ramp(stops, x: np.ndarray) -> np.ndarray:
    xs = np.array([a for a, _ in stops], np.float32)
    cs = np.array([c for _, c in stops], np.float32)
    x = np.clip(x, 0, 1)
    return np.stack([np.interp(x, xs, cs[:, k]) for k in range(3)], -1)


def draw_star(img: Image.Image, cam, name: str, cx: float, cy: float, r: float, rot: float,
              alpha: float = 1.0, flash: float = 0.0) -> None:
    """A star as a textured, limb-darkened, gently rotating sphere (opaque)."""
    if alpha <= 0.01 or r < 0.6:
        return
    spec = STARS[name]
    half = r + 2
    bx0, by0 = max(0, int(math.floor(cx - half))), max(0, int(math.floor(cy - half)))
    bx1, by1 = min(W, int(math.ceil(cx + half)) + 1), min(H, int(math.ceil(cy + half)) + 1)
    if bx0 >= bx1 or by0 >= by1:
        return
    yy, xx = np.mgrid[by0:by1, bx0:bx1].astype(np.float32)
    sx, sy = (xx + 0.5 - cx) / r, -(yy + 0.5 - cy) / r
    rho2 = sx * sx + sy * sy
    cover = np.clip((1 - np.sqrt(rho2)) * r + 0.5, 0, 1)
    nz = -np.sqrt(np.clip(1 - rho2, 0, 1))
    n_w = sx[..., None] * cam.right + sy[..., None] * cam.up + nz[..., None] * cam.look
    e1, e2, p = s3._basis(np.array([0.08, 0.0, 1.0]))
    lat = np.arcsin(np.clip(n_w @ p, -1, 1))
    lon = np.arctan2(n_w @ e2, n_w @ e1) + rot
    tex = star_textures()[name]
    # never ask for more detail than the largest level has (Texture.sample would
    # then fall back to its smallest level)
    m = tex.sample(lon, lat, min(r, tex.levels[0].shape[1] / (2 * math.pi * 1.3)))[..., 0] / 255.0
    mu = np.clip(-nz, 0, 1)
    limb = 1 - spec["u"] * (1 - mu ** 0.7)
    inten = (spec["lo"] + (spec["hi"] - spec["lo"]) * m) * limb
    out = _ramp(spec["ramp"], inten)
    if flash > 0:
        out = out + flash * 60
    a = (cover * alpha)[..., None]
    reg = np.asarray(img.crop((bx0, by0, bx1, by1)), np.float32)
    reg = reg * (1 - a) + np.clip(out, 0, 255) * a
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), (bx0, by0))


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
class Plan:
    def __init__(self, L: dict):
        self.hook_at = 0.25
        self.rew = max(3.7, self.hook_at + L["hook"].secs + 0.35)
        self.shrink_end = self.rew + 0.5
        self.dive_end = self.shrink_end + 1.1
        self.at = {"earth": self.dive_end - 0.1}
        self.trans = {}                    # body -> (start, duration)
        self.arrive = {"earth": self.dive_end}
        order = ["earth", "sun", "sirius", "arcturus", "rigel", "betel"]
        prev_line, prev_end = None, 0.0
        for body in [b[0] for b in LADDER[1:]]:
            line = LINE_OF[body]
            if line not in self.at:
                self.at[line] = max(self.at[prev_line] + L[prev_line].secs + 0.3, prev_end + 0.2)
            t0 = self.at[line] + _word(L[line], WORD_OF[body], 0.1) - 0.12
            self.trans[body] = (t0, TRANS_DUR[body])
            prev_end = t0 + TRANS_DUR[body]
            self.arrive[body] = prev_end
            prev_line = line
        assert list(self.at) == order
        self.payoff_at = max(self.at["betel"] + L["betel"].secs + 0.45, prev_end + 0.35)
        self.cross0 = self.payoff_at - 0.1
        self.cross1 = self.payoff_at + 0.65
        po = L["payoff"]
        w = lambda s, f: self.payoff_at + _word(po, s, f)
        tk = [w("swallow", 0.25), w("Mercury", 0.33) + 0.12, w("Venus", 0.45) + 0.1, w("Earth", 0.6) + 0.1,
              w("Mars", 0.7) + 0.1, w("asteroid", 0.85) + 0.05, self.payoff_at + po.secs + 0.05]
        tk.append(tk[-1] + 0.75)
        rk = [R_SUN_AU, 0.41, 0.75, 1.04, 1.58, 2.3, 3.32, R_FULL]
        for i in range(1, len(tk)):
            tk[i] = max(tk[i], tk[i - 1] + 0.12)
        self.grow = PchipInterpolator(tk, rk)
        self.g0, self.g1 = tk[0], tk[-1]
        self.total = self.payoff_at + po.secs + 2.4
        # when the star's edge passes each planet (on screen)
        ts = np.linspace(self.g0, self.g1, 4000)
        rp = np.array([star_px(self.R(t), K) for t in ts])
        self.swallow = {}
        for name, a, *_ in PLANETS:
            if a < R_FULL:
                self.swallow[name] = float(ts[np.argmax(rp >= a * K)])
        self.belt_t = float(ts[np.argmax(rp >= 3.3 * K)])

    def R(self, t: float) -> float:
        """Radius (AU) of the star in the top-down view."""
        if t < self.rew:
            return R_FULL
        if t < self.shrink_end:
            u = smooth((t - self.rew) / (self.shrink_end - self.rew))
            return math.exp(math.log(R_FULL) * (1 - u) + math.log(R_SUN_AU) * u)
        if t < self.g0:
            return R_SUN_AU
        if t < self.g1:
            return float(self.grow(t))
        return R_FULL

    def ladder_state(self, t: float):
        """(index of the body framed, transition progress 0..1 or None)."""
        bodies = [b[0] for b in LADDER]
        for k, name in enumerate(bodies[1:], start=1):
            t0, d = self.trans[name]
            if t < t0:
                return k - 1, None
            if t < t0 + d:
                return k - 1, (t - t0) / d
        return len(bodies) - 1, None


def star_px(R_au: float, k: float) -> float:
    """Screen radius of the star: true size, but never smaller than a visible Sun."""
    x = R_au * k
    return x + SUN_MIN_PX * math.exp(-x / SUN_MIN_PX)


# --------------------------------------------------------------------------- #
# Ladder camera: positions in km along a line, a zoom about a fixed point
# --------------------------------------------------------------------------- #
def ladder_layout():
    xs, states = [0.0], []
    for k, (_, _, r, _, _, rf, fx) in enumerate(LADDER):
        if k:
            r0 = LADDER[k - 1][2]
            s0 = states[-1][0]
            # the next body stays just off the right edge while this one is framed
            off = (W + 50 - LADDER[k - 1][6] * W - LADDER[k - 1][5]) / s0
            xs.append(xs[-1] + r0 + max(0.35 * r0 + 0.06 * r, off) + r)
        s = rf / r
        states.append((s, xs[k] - (fx * W - W / 2) / s))
    return xs, states


def zoom_between(a, b, u: float):
    """Camera (scale, centre) part-way from a to b: log-scale, about the fixed point."""
    (s0, x0), (s1, x1) = a, b
    s = s0 * (s1 / s0) ** u
    if abs(s1 - s0) < 1e-12:
        return s, x0 + (x1 - x0) * u
    p = (x1 * s1 - x0 * s0) / (s1 - s0)
    return s, p - (p - x0) * s0 / s


def pushed(state, focus_x: float, f: float):
    s, xc = state
    X = W / 2 + (focus_x - xc) * s
    s2 = s * f
    return s2, focus_x - (X - W / 2) / s2


# --------------------------------------------------------------------------- #
# Drawing helpers
# --------------------------------------------------------------------------- #
def cairo_layer():
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_ADD)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return surf, ctx


def layer_rgb(surf) -> np.ndarray:
    surf.flush()
    buf = np.ndarray((H, surf.get_stride() // 4, 4), np.uint8, surf.get_data())[:, :W]
    return buf[..., 2::-1].astype(np.float32)


def rgb(ctx, col, a: float) -> None:
    ctx.set_source_rgb(col[0] / 255 * a, col[1] / 255 * a, col[2] / 255 * a)


def ellipse_arc(ctx, cx, cy, rx, ry, a0, a1) -> None:
    if rx < 0.5:
        return
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(rx, max(ry, 0.01))
    ctx.new_path()
    ctx.arc(0, 0, 1, a0, a1)
    ctx.restore()
    ctx.stroke()


def splat(arr: np.ndarray, xs, ys, col, vals) -> None:
    """Additive points with bilinear weights (sub-pixel smooth)."""
    ok = (xs > 1) & (xs < W - 2) & (ys > 1) & (ys < H - 2)
    xs, ys, vals = xs[ok], ys[ok], vals[ok]
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    c = np.array(col, np.float32)
    for dx, dy, wgt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(arr, (y0 + dy, x0 + dx), (wgt * vals)[:, None] * c)


def label(img, x: float, y: float, rows, align: str, alpha: float) -> None:
    """rows: [(text, colour, font[, own alpha])], stacked down from y."""
    if alpha <= 0.01:
        return
    yy = y
    for i, row in enumerate(rows):
        txt, col, fnt = row[:3]
        a = alpha * (row[3] if len(row) > 3 else 1.0)
        if i:
            yy += (rows[i - 1][2].size + fnt.size) * 0.64
        if a <= 0.01:
            continue
        wdt = fnt.getlength(txt)
        lx = x if align == "left" else (x - wdt if align == "right" else x - wdt / 2)
        lx = max(36, min(W - 36 - wdt, lx))
        kit.solid_text(img, 0, yy, [(txt, col)], fnt, alpha=a, shadow=0.85, left=lx)


def fixed_digits(img, cx: float, y: float, s: str, fnt, col, alpha: float) -> None:
    """Text with every digit in a cell of the same width (no jitter as it ticks)."""
    cell = max(fnt.getlength(str(d)) for d in range(10))
    widths = [cell if ch.isdigit() else fnt.getlength(ch) for ch in s]
    x = cx - sum(widths) / 2
    for ch, wd in zip(s, widths):
        if ch != " ":
            off = (wd - fnt.getlength(ch)) / 2
            kit.solid_text(img, 0, y, [(ch, col)], fnt, alpha=alpha, shadow=0.8, left=x + off)
        x += wd


def diam_text(km: float) -> str:
    if km < 1e6:
        return f"{km:,.0f} km"
    if km < 1e9:
        v = km / 1e6
        return f"{v:.2f} million km" if v < 10 else (f"{v:.1f} million km" if v < 100 else f"{v:.0f} million km")
    return f"{km / 1e9:.2f} billion km"


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def whoosh(dur, f0, f1, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = np.zeros_like(t)
    for _ in range(14):
        f = f0 * (f1 / f0) ** u * rng.uniform(0.8, 1.25)
        out += np.sin(2 * np.pi * np.cumsum(f) / snd.SR + rng.uniform(0, 6.3)) * rng.uniform(0.4, 1.0)
    return (out / 14 * np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6).astype(np.float32)


def pad(dur: float, freqs, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    out = np.zeros_like(t)
    for f in freqs:
        for det in (-0.6, 0.0, 0.7):
            out += np.sin(2 * np.pi * (f + det) * t + rng.uniform(0, 6.3))
    out /= len(freqs) * 3
    env = np.clip(t / 2.5, 0, 1) * np.clip((dur - t) / 2.0, 0, 1)
    return (out * env * (0.8 + 0.2 * np.sin(2 * np.pi * t / 7.0))).astype(np.float32)


def swell(dur: float, f: float = 41.2) -> np.ndarray:
    """A low rumble that grows: the star expanding."""
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.5 * t + 1.0)
           + 0.3 * np.sin(2 * np.pi * f * 2 * t + 2.0))
    return (out / 1.8 * (u ** 1.4) * np.clip((1 - u) / 0.08, 0, 1)).astype(np.float32)


def _soundtrack(plan: Plan, path: Path, clips) -> None:
    m = snd.Mixer(plan.total)
    m.add(0.0, pad(plan.total, [55.0, 82.4, 110.0, 164.8]), 0.3)
    m.add(0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7)], dur=3.6), 0.55)
    m.add(plan.rew - 0.05, whoosh(0.7, 900, 160, seed=3), 0.4)
    m.add(plan.shrink_end - 0.05, whoosh(1.15, 1600, 150, seed=4), 0.5)
    m.add(plan.dive_end - 0.04, snd.pluck(snd.scale_freq(15), dur=1.2, bright=0.6), 0.28)
    notes = {"jupiter": 13, "sun": 11, "sirius": 10, "arcturus": 7, "rigel": 5, "betelgeuse": 1}
    for i, (body, (t0, d)) in enumerate(plan.trans.items()):
        m.add(t0, whoosh(d + 0.2, 300, 85, seed=20 + i), 0.22)
        m.add(t0 + d - 0.03, snd.pluck(snd.scale_freq(notes[body]), dur=1.6, bright=0.55), 0.34)
        if body in ("sun", "betelgeuse"):
            m.add(t0 + d - 0.03, snd.thud(70, 0.4), 0.45)
    m.add(plan.arrive["betelgeuse"], snd.chord([snd.scale_freq(i) for i in (0, 2, 5, 7)], dur=3.0), 0.5)
    m.add(plan.g0, swell(plan.g1 - plan.g0 + 0.2), 0.5)
    for i, (name, ts) in enumerate(sorted(plan.swallow.items(), key=lambda kv: kv[1])):
        m.add(ts, snd.thud(62 + 6 * i, 0.35), 0.5)
        m.add(ts, snd.pluck(snd.scale_freq(4 - i % 3), dur=1.0, bright=0.4), 0.18)
    m.add(plan.g1 - 0.2, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7, 10)], dur=plan.total - plan.g1 + 0.2),
          0.7)
    voice.voice_over(m, list(clips), bed=0.75)
    m.write(path, plan.total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    keys = ["earth", "sun", "sirius", "arcturus", "rigel", "betel", "payoff"]
    starts = dict(plan.at, payoff=plan.payoff_at)
    clips = [(plan.hook_at, lines["hook"])] + [(starts[k], lines[k]) for k in keys]
    caps = []
    for k in keys:
        caps += kit.captions(starts[k], lines[k], SCRIPT[k][1])

    bg = sp.starfield(seed=6, cx=W / 2, cy=CY, band_angle=-34.0)
    s3.textures()
    star_textures()
    xs, states = ladder_layout()
    cam_l = s3.Camera(1.0, LADDER_PHI, 1.0, 1.0, 0.0, 0.0)
    cam_o = s3.Camera(1.0, ELEV, 1.0, 1.0, 0.0, 0.0)
    key_n = KEY / np.linalg.norm(KEY)
    rng = np.random.default_rng(seed)
    nb = 2600
    belt_a = rng.uniform(2.2, 3.3, nb) ** 1.0
    belt_th = rng.uniform(0, 2 * math.pi, nb)
    belt_v = rng.uniform(0.25, 1.0, nb) ** 2 * 0.9
    plan_a = {p[0]: p[1] for p in PLANETS}

    f_name, f_small = kit.sans(28, "bold"), kit.sans(24, "bold")
    f_ratio, f_read = kit.sans(34, "bold"), kit.sans(88, "black")
    name_col = (214, 218, 228)
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)

    def theta(name: str, a: float, th0: float, t: float) -> float:
        return math.radians(th0) - omega(a) * t

    # ---------------- the top-down view (hook, rewind, dive, payoff) ----------------
    def top_down(t: float, dive: float | None = None) -> Image.Image:
        R = plan.R(t)
        th_e = theta("earth", 1.0, -128.0, t)
        ex_w, ey_w = math.cos(th_e), math.sin(th_e)
        e0x, e0y = W / 2 + ex_w * K, CY - ey_w * SIN_E * K
        if dive is None:
            Kz, ox, oy, ax, ay = K, W / 2, CY, 0.0, 0.0
            fade = 1.0
        else:
            u = smooth(dive)
            z1 = (EARTH_PX / (6371.0 / AU_KM)) / K
            Kz = K * z1 ** (u ** 1.6)
            ox, oy = e0x + (W / 2 - e0x) * u, e0y + (CY - e0y) * u
            ax, ay = ex_w, ey_w
            fade = (1 - smooth(dive / 0.55))

        def proj(xw, yw):
            return ox + (xw - ax) * Kz, oy - (yw - ay) * SIN_E * Kz

        scx, scy = proj(0.0, 0.0)
        rp = star_px(R, Kz) if dive is None else R * Kz + SUN_MIN_PX * math.exp(-R * K / SUN_MIN_PX)
        wmix = smooth((rp - SUN_MIN_PX - 4) / 40) if dive is None else 0.0
        arr = bg.copy()
        gcol = tuple(np.array(SUN_GLOW) * (1 - wmix) + np.array(STARS["betelgeuse"]["glow"]) * wmix)
        if -rp * 3 < scx < W + rp * 3 and -rp * 3 < scy < H + rp * 3:
            s3.glow(arr, scx, scy, rp, (0.9 * (1 - wmix) + 0.55 * wmix) * (fade if dive is not None else 1.0),
                    col=gcol, reach=4.0 if wmix < 0.5 else 1.6)

        # back halves of the orbits
        surf, ctx = cairo_layer()
        orb_a = 0.36 * fade
        if orb_a > 0.01:
            for name, a, *_ in PLANETS:
                rgb(ctx, (150, 168, 200), orb_a * (0.8 if name == "jupiter" else 1.0))
                ctx.set_line_width(1.5)
                ellipse_arc(ctx, scx, scy, a * Kz, a * Kz * SIN_E, math.pi, 2 * math.pi)
        arr += layer_rgb(surf)
        # the asteroid belt (back part)
        bth = belt_th - 0.06 * belt_a ** -1.5 * t
        bx = scx + belt_a * np.cos(bth) * Kz
        by = scy - belt_a * np.sin(bth) * SIN_E * Kz
        back = np.sin(bth) > 0
        alive = belt_a * Kz > rp
        if fade > 0.01:
            splat(arr, bx[back], by[back], (205, 190, 165), belt_v[back] * fade * 0.85)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        def planet(name, a, th0, r_px, front: bool, alpha_mul: float):
            th = theta(name, a, th0, t)
            if (math.sin(th) < 0) != front:
                return
            x, y = proj(a * math.cos(th), a * math.sin(th))
            if not (-60 < x < W + 60 and -60 < y < H + 60):
                return
            vis = smooth((a * Kz - rp) / 7 + 0.5)
            if name == "earth" and dive is not None:
                return
            if vis <= 0.01:
                return
            P = np.array([a * math.cos(th), a * math.sin(th), 0.0])
            Lc = cam_o.to_cam_dir(-P / np.linalg.norm(P))
            light = 0.45 * Lc + 0.55 * key_n
            s3.draw_planet(img, cam_o, name, x, y, r_px, light, rot=1.1 + t * 0.3, alpha=vis * alpha_mul,
                           pole=EARTH_POLE if name == "earth" else (0, 0, 1), clouds_rot=t * 0.05)

        for name, a, th0, r_px in PLANETS:
            planet(name, a, th0, r_px, False, fade)
        # the star (Betelgeuse growing out of the Sun)
        if wmix > 0.001:
            draw_star(img, cam_o, "betelgeuse", scx, scy, rp, rot=0.4 + t * 0.02)
        if wmix < 0.999 and -rp < scx < W + rp:
            s3.draw_planet(img, cam_o, "sun", scx, scy, rp, np.array([0, 0, -1.0]), rot=t * 0.05,
                           emissive=True, alpha=1 - wmix)

        # front: orbit arcs still outside the star, ghosts of swallowed ones, callouts
        arr2 = np.asarray(img, np.float32).copy()
        surf, ctx = cairo_layer()
        if orb_a > 0.01:
            for name, a, *_ in PLANETS:
                if a * Kz > rp:
                    rgb(ctx, (150, 168, 200), orb_a * (0.8 if name == "jupiter" else 1.0))
                    ctx.set_line_width(1.5)
                    ellipse_arc(ctx, scx, scy, a * Kz, a * Kz * SIN_E, 0, math.pi)
                elif dive is None and wmix > 0.3:
                    ga = 0.24 * smooth((rp - a * Kz) / 25)
                    ctx.set_dash([7, 9])
                    rgb(ctx, (255, 238, 215), ga)
                    ctx.set_line_width(1.6)
                    ellipse_arc(ctx, scx, scy, a * Kz, a * Kz * SIN_E, 0, 2 * math.pi)
                    ctx.set_dash([])
        callouts = []
        if dive is None:
            for name, a, side in (("earth", 1.0, -1), ("mars", 1.524, 1)):
                if t < plan.rew:
                    ca = 1.0
                elif t < plan.shrink_end:
                    ca = 1 - smooth((t - plan.rew) / 0.3)
                elif t < plan.g0:
                    ca = 0.0
                else:
                    ca = smooth((t - plan.swallow[name] - 0.15) / 0.45)
                if ca <= 0.01:
                    continue
                px0, py0 = scx + side * a * Kz, scy
                lx, ly = scx + side * 362, scy - 262
                rgb(ctx, (232, 232, 238), 0.6 * ca)
                ctx.set_line_width(1.6)
                ctx.move_to(px0, py0)
                ctx.line_to(lx, ly)
                ctx.stroke()
                ctx.arc(px0, py0, 3.2, 0, 2 * math.pi)
                ctx.fill()
                callouts.append((name, lx, ly, side, ca))
        arr2 += layer_rgb(surf)
        front = ~back & alive
        if fade > 0.01:
            splat(arr2, bx[front], by[front], (205, 190, 165), belt_v[front] * fade * 0.85)
        # a flash where the surface swallows each planet
        if dive is None and plan.g0 <= t < plan.g1 + 0.5:
            for name, ts in plan.swallow.items():
                fl = kit.flash(t, ts + 0.05, 0.32)
                if fl > 0.02:
                    a = plan_a[name]
                    th = theta(name, a, [p[2] for p in PLANETS if p[0] == name][0], ts)
                    x, y = proj(a * math.cos(th), a * math.sin(th))
                    s3.glow(arr2, x, y, 8, fl * 1.1, col=(255, 200, 150), reach=3.0)
            fl = kit.flash(t, plan.belt_t + 0.05, 0.4)
            if fl > 0.02:
                s3.glow(arr2, scx, scy, rp, fl * 0.35, col=(255, 170, 110), reach=1.0)
        img = Image.fromarray(np.clip(arr2, 0, 255).astype(np.uint8))
        for name, a, th0, r_px in PLANETS:
            planet(name, a, th0, r_px, True, fade)

        # Earth, which the dive flies into
        if dive is not None:
            u = smooth(dive)
            ex, ey = proj(ex_w, ey_w)
            r_e = 9.5 * (EARTH_PX / 9.5) ** (u ** 1.6)
            P = np.array([ex_w, ey_w, 0.0])
            Lo = 0.6 * cam_o.to_cam_dir(-P) + 0.4 * key_n
            cam_d = s3.Camera(1.0, ELEV + (LADDER_PHI - ELEV) * u, 1.0, 1.0, 0.0, 0.0)
            light = Lo * (1 - u) + key_n * u
            s3.draw_planet(img, cam_d, "earth", ex, ey, r_e, light, rot=1.1 + t * 0.3, pole=EARTH_POLE,
                           clouds_rot=t * 0.05)

        # labels
        if dive is None:
            for name, lx, ly, side, ca in callouts:
                label(img, lx, ly - 30, [(name.upper(), WHITE, f_name)], "centre", ca)
            th = theta("jupiter", 5.203, 160.0, t)
            jx, jy = proj(5.203 * math.cos(th), 5.203 * math.sin(th))
            ja = 1.0 if t < plan.rew else (1 - smooth((t - plan.rew) / 0.3) if t < plan.cross0
                                             else smooth((t - plan.cross1 + 0.3) / 0.5))
            label(img, jx + 4, jy - 46, [("JUPITER", name_col, f_small)], "centre", ja)
            if plan.cross0 <= t < plan.g0 + 0.6:
                sa = smooth((t - plan.cross1 + 0.4) / 0.4) * (1 - smooth((t - plan.g0 - 0.2) / 0.4))
                label(img, scx, scy + rp + 34, [("THE SUN", name_col, f_small)], "centre", sa)
        return img

    # ---------------- the ladder ----------------
    def ladder(t: float) -> Image.Image:
        k, u = plan.ladder_state(t)
        name_k = LADDER[k][0]
        t_arr = plan.arrive[name_k]
        nxt = plan.trans[LADDER[k + 1][0]][0] if k + 1 < len(LADDER) else plan.total

        def push_at(tt):
            return 1.0 + 0.03 * smooth((tt - t_arr) / max(0.5, nxt - t_arr + 1.2))
        if u is None:
            st = pushed(states[k], xs[k], push_at(t))
        else:
            st0 = pushed(states[k], xs[k], push_at(plan.trans[LADDER[k + 1][0]][0]))
            st = zoom_between(st0, states[k + 1], smooth(u) if LADDER[k + 1][0] != "betelgeuse"
                              else smooth(u) ** 1.15)
        s, xc = st
        arr = bg.copy()
        scr = []
        for i, (key, lab, r_km, ratio, kind, _, _) in enumerate(LADDER):
            if i > k + (0 if u is None else 1):
                continue                     # the next body waits off-screen
            X, r = W / 2 + (xs[i] - xc) * s, r_km * s
            if X + r < -80 or X - r > W + 80:
                continue
            scr.append((i, X, r))
            g = 1.0 if i <= k else smooth(u * 1.6)
            if kind == "sun":
                s3.glow(arr, X, CY, max(r, 1.5), 0.85 * g, col=SUN_GLOW, reach=4.0 if r < 120 else 2.0)
            elif kind == "star":
                spec = STARS[key]
                s3.glow(arr, X, CY, max(r, 1.5), spec["gain"] * g, col=spec["glow"],
                        reach=4.0 if r < 120 else 1.7)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        for i, X, r in scr:
            key, kind = LADDER[i][0], LADDER[i][4]
            if r < 0.7:
                continue
            if kind == "planet":
                s3.draw_planet(img, cam_l, key, X, CY, r, key_n, rot=1.1 + t * 0.3, clouds_rot=t * 0.05,
                               pole=EARTH_POLE if key == "earth" else (0.05, 0, 1))
            elif kind == "sun":
                s3.draw_planet(img, cam_l, "sun", X, CY, r, np.array([0, 0, -1.0]), rot=t * 0.05, emissive=True)
            else:
                draw_star(img, cam_l, key, X, CY, r, rot=0.6 * i + t * 0.035)
        for i, X, r in scr:
            key, lab, _, ratio, *_ = LADDER[i]
            seen = smooth((t - plan.arrive[key] + 0.35) / 0.45)
            la = seen * smooth((r - 11) / 12)
            if la <= 0.01:
                continue
            fn = f_name if r > 60 else f_small
            rows = [(lab, WHITE if r > 60 else name_col, fn)]
            if ratio:
                rows.append((ratio, GOLD, f_ratio if r > 60 else f_small))
            label(img, X, CY + r + 26 + fn.size * 0.5, rows, "centre", la)
        return img

    def readout(img, t: float) -> None:
        if t < plan.dive_end - 0.25:
            return
        a = smooth((t - plan.dive_end + 0.25) / 0.4)
        k, u = plan.ladder_state(t) if t < plan.cross0 else (len(LADDER) - 1, None)
        d0 = 2 * LADDER[k][2]
        if u is None:
            km, lab = d0, LADDER[k][1]
        else:
            d1 = 2 * LADDER[k + 1][2]
            km = math.exp(math.log(d0) + (math.log(d1) - math.log(d0)) * smooth(u))
            lab = LADDER[k + 1][1] if u > 0.5 else LADDER[k][1]
        gold = t >= plan.arrive["betelgeuse"] - 0.05
        label(img, W / 2, TOP_LABEL_Y, [(f"{lab} · DIAMETER", MUTED, f_small)], "centre", a)
        fixed_digits(img, W / 2, READ_Y, diam_text(km), f_read, GOLD if gold else WHITE, a)

    def frame(t: float) -> Image.Image:
        if t < plan.shrink_end:
            img = top_down(t)
        elif t < plan.dive_end:
            img = top_down(t, dive=(t - plan.shrink_end) / (plan.dive_end - plan.shrink_end))
        elif t < plan.cross0:
            img = ladder(t)
        elif t < plan.cross1:
            f = smooth((t - plan.cross0) / (plan.cross1 - plan.cross0))
            img = Image.blend(ladder(t), top_down(t), f)
        else:
            img = top_down(t)
        readout(img, t)
        if t < plan.rew + 0.4:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            kit.hook(img, HOOK, t if t < hook_end + 0.1 else 99.0, t0=HOOK_T0, alpha=ha, size=66, ys=HOOK_YS)
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, path, clips)

    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
