"""Do all the planets fit between Earth and the Moon? Only sometimes.

The seven other planets, to scale, stacked in the gap between Earth and the
Moon (Earth at the top of the frame, the Moon at the bottom). Opens on the
finished picture with the claim, rewinds, then the camera starts low behind
Earth looking down the row while each planet flies in on its spoken name, and
swings round to the flat side view as the row fills. At the Moon's average
distance Neptune does not fit (it waits beside the gap, its slot shown as a
ghost that runs past the Moon). Then the Moon drifts out to its farthest point,
Neptune slides in, and the spare room is measured.

Honest numbers: NASA equatorial diameters, which sum to 387,928 km. Gap =
centre distance minus Earth's and the Moon's radii: 376,292 km at 384,400 km
(the mean distance), 398,492 km at 406,600 km (about the farthest apogee).
Over 2026-35 the gap is wider than the planets about a third of the time,
7-11 days a month (worked out from the main terms of the lunar distance
series, Meeus ch. 47). Everything on screen, sizes and distances, is to scale.

No Moon map ships with the planet textures, so the Moon's surface (maria,
craters) is generated here.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import cairo
import numpy as np
from PIL import Image

from . import canvas as cv
from . import kit
from . import sound as snd
from . import space as sp
from . import space3d as s3
from . import voice
from .canvas import GOLD, MUTED, WHITE, H, W, scale

FPS = 60
VOICE, RATE = "en-US-AndrewNeural", "+0%"

R_EARTH, R_MOON = 6371.0, 1737.4
MOON_AVG, MOON_FAR = 384_400.0, 406_600.0
# name, equatorial diameter (km), spin (rad/s), pole (world: X right, Y up the row, Z away from camera)
PLANETS = [
    ("mercury", 4_879, 0.15, (0.0, 1.0, 0.0)),
    ("venus", 12_104, 0.08, (0.0, 1.0, 0.0)),
    ("mars", 6_779, 0.25, (0.25, 0.96, 0.1)),
    ("jupiter", 142_984, 0.32, (0.03, 1.0, -0.05)),
    ("saturn", 120_536, 0.3, (0.12, 0.94, -0.33)),
    ("uranus", 51_118, 0.22, (0.97, 0.12, -0.2)),
    ("neptune", 49_528, 0.22, (0.28, 0.95, -0.1)),
]
TOTAL = sum(p[1] for p in PLANETS)                     # 387,928 km
EARTH_POLE = (0.33, 0.93, 0.15)
LIGHT = np.array([-0.62, 0.48, -0.62])                  # the Sun: upper left, in front
LIGHT = LIGHT / np.linalg.norm(LIGHT)

TOP, BOT = 450.0, 1552.0          # the flat view: Earth's top edge to the far Moon's bottom edge
CX, CY = 540.0, (TOP + BOT) / 2
KPX = (BOT - TOP) / (R_EARTH + MOON_FAR + R_MOON)        # px per km in the flat view
S_MID = (MOON_FAR + R_MOON - R_EARTH) / 2
FLAT = dict(s=S_MID, e=0.0, az=-0.32, d=1.4e6, k=KPX, cy=CY)
LOW = dict(s=30_000.0, e=math.radians(45), az=-0.55, d=62_000.0, k=0.0135, cy=1020.0)

CORAL = (232, 128, 104)
NAME = (214, 218, 228)
LBL_Y, NUM_Y, DAYS_Y = 116, 178, 272
HOOK_T0 = -0.45

HOOK = [[("Every", GOLD), ("planet", GOLD), ("fits", WHITE), ("between", WHITE)],
        [("Earth", WHITE), ("and", WHITE), ("the", WHITE), ("Moon.", WHITE)]]

SCRIPT = {
    "hook": ("Every planet fits between Earth and the Moon.", None),
    "stack": ("Line them up. Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune.",
              [("Line them up.", 3), ("Mercury, Venus, Mars,", 3), ("Jupiter, Saturn,", 2), ("Uranus, Neptune", 2)]),
    "short": ("That's 388,000 kilometres. But on average, the gap is only 376,000. Neptune doesn't fit.",
              [("That's *388,000 km*", 3), ("But on average,", 3), ("the gap is only *376,000*", 5),
               ("Neptune doesn't fit", 3)]),
    "orbit": ("Except the Moon's orbit isn't a perfect circle. At its farthest, the gap grows to 398,000.",
              [("Except the Moon's orbit", 4), ("isn't a perfect circle", 4), ("At its farthest,", 3),
               ("the gap grows to *398,000*", 5)]),
    "payoff": ("Now every planet fits, with over 10,000 kilometres to spare. But only for about 9 days a month.",
               [("Now every planet fits,", 4), ("with over *10,000 km*", 4), ("to spare.", 2),
                ("But only for about", 4), ("*9 days* a month", 3)]),
}


# --------------------------------------------------------------------------- #
# Geometry: km along the row from Earth's centre (s), world Y = -s
# --------------------------------------------------------------------------- #
def slots() -> dict[str, float]:
    out, edge = {}, R_EARTH
    for name, dia, *_ in PLANETS:
        out[name] = edge + dia / 2
        edge += dia
    return out


SLOT = slots()
RAD = {p[0]: p[1] / 2 for p in PLANETS}
RAD.update(earth=R_EARTH, moon=R_MOON)
NEP_FAR = SLOT["neptune"] + RAD["neptune"]              # 394,299 km: where the row ends


def gap_of(D: float) -> float:
    return D - R_EARTH - R_MOON


class Cam:
    """Perspective camera aimed at a point on the row. e tilts the view from
    side-on (0) towards looking down the row from behind Earth; az turns it
    around the row. k is the scale (px per km) at the aim point."""

    def __init__(self, s: float, e: float, az: float, d: float, k: float, cy: float):
        n = np.array([math.sin(az), 0.0, math.cos(az)])
        self.look = math.cos(e) * n + math.sin(e) * np.array([0.0, -1.0, 0.0])
        Y = np.array([0.0, 1.0, 0.0])
        up = Y - (Y @ self.look) * self.look
        self.up = up / np.linalg.norm(up)
        self.right = np.cross(self.up, self.look)
        self.C = np.array([0.0, -s, 0.0]) - d * self.look
        self.f, self.cx, self.cy = k * d, CX, cy

    def cam(self, P) -> np.ndarray:
        r = np.asarray(P, float) - self.C
        return np.stack([r @ self.right, r @ self.up, r @ self.look], axis=-1)

    def project(self, P):
        c = self.cam(P)
        z = c[..., 2]
        return self.cx + self.f * c[..., 0] / z, self.cy - self.f * c[..., 1] / z, z

    def to_cam_dir(self, v) -> np.ndarray:
        v = np.asarray(v, float)
        return np.array([v @ self.right, v @ self.up, v @ self.look])


def earth_y(c: dict) -> float:
    """Where Earth sits on screen for a camera setting."""
    return c["cy"] - c["k"] * c["d"] * c["s"] * math.cos(c["e"]) / (c["d"] - c["s"] * math.sin(c["e"]))


def cam_between(a: dict, b: dict, u: float) -> Cam:
    """Blend two settings. The aim point is solved so Earth glides straight
    between its two screen heights (it never rides up under the captions)."""
    u = max(0.0, min(1.0, u))
    lin = lambda k: a[k] + (b[k] - a[k]) * u
    geo = lambda k: math.exp(math.log(a[k]) + (math.log(b[k]) - math.log(a[k])) * u)
    e, d, k, cy = lin("e"), geo("d"), geo("k"), lin("cy")
    ye = earth_y(a) + (earth_y(b) - earth_y(a)) * u
    A = (cy - ye) / (k * d)
    s = A * d / (math.cos(e) + A * math.sin(e))
    return Cam(s, e, lin("az"), d, k, cy)


# --------------------------------------------------------------------------- #
# A Moon map, made here (maria, craters, a few bright young craters)
# --------------------------------------------------------------------------- #
class ArrayTexture(s3.Texture):
    def __init__(self, arr: np.ndarray):
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        self.levels = []
        while True:
            self.levels.append(np.asarray(im, np.float32))
            if im.width <= 64:
                break
            im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)


def _waves(p: np.ndarray, n: int, f0: float, f1: float, rng) -> np.ndarray:
    """Smooth noise on the sphere: a sum of random plane waves (no seams, no poles)."""
    out = np.zeros(p.shape[:-1], np.float32)
    for _ in range(n):
        k = rng.normal(size=3)
        k /= np.linalg.norm(k)
        f = f0 * (f1 / f0) ** rng.random()
        out += np.sin((p @ k) * f + rng.uniform(0, 2 * math.pi)).astype(np.float32) / f
    return out / np.abs(out).max()


@lru_cache(maxsize=1)
def moon_map(w: int = 1024, h: int = 512, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lon = (np.arange(w) + 0.5) / w * 2 * math.pi
    lat = math.pi / 2 - (np.arange(h) + 0.5) / h * math.pi
    LON, LAT = np.meshgrid(lon, lat)
    p = np.stack([np.cos(LAT) * np.cos(LON), np.cos(LAT) * np.sin(LON), np.sin(LAT)], -1).astype(np.float32)
    # Maria: broad dark seas, mostly on one hemisphere (the side that faces us).
    seas = _waves(p, 22, 1.6, 4.5, rng) + 0.55 * np.clip(p[..., 0], 0, 1) - 0.12
    mare = np.clip((seas - 0.08) / 0.18, 0, 1) ** 1.3
    fine = _waves(p, 70, 10, 60, rng)
    val = 0.66 - 0.33 * mare + 0.07 * fine
    # Craters: power-law sizes; dark floor, bright rim, faint ejecta skirt.
    for i in range(650):
        c = rng.normal(size=3)
        c /= np.linalg.norm(c)
        rho = 0.006 * (1 - rng.random()) ** -0.9
        rho = min(rho, 0.16)
        lat_c = math.asin(c[2])
        band = np.abs(lat - lat_c) < rho * 2.4 + 0.01
        if not band.any():
            continue
        pp = p[band]
        dlt = np.arccos(np.clip(pp @ c.astype(np.float32), -1, 1)) / rho
        young = rng.random() < 0.05
        prof = (-0.10 * np.clip(1 - dlt ** 2, 0, 1)
                + 0.13 * np.exp(-((dlt - 1) / 0.16) ** 2)
                + (0.10 if young else 0.03) * np.exp(-np.clip(dlt - 1, 0, None) / 0.8) * (dlt > 1))
        val[band] += prof * (0.7 if mare[band].mean() > 0.5 else 1.0)
    val = np.clip(val, 0.08, 1.0)
    tint = np.array([255, 248, 238], np.float32)
    return val[..., None] * tint


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class Plan:
    def __init__(self, L: dict[str, voice.Line]):
        self.hook_at = 0.25
        self.rew = max(3.6, self.hook_at + L["hook"].secs + 0.4)
        self.rew_end = self.rew + 1.05
        self.stack_at = self.rew_end + 0.2
        st = L["stack"]
        self.land = {name: self.stack_at + _word(st, name.capitalize(), 0.2 + 0.1 * i) + 0.05
                     for i, (name, *_) in enumerate(PLANETS)}
        self.cam0 = self.land["jupiter"] - 0.35
        self.cam1 = self.land["neptune"] + 0.75
        self.short_at = self.stack_at + st.secs + 0.35
        sh = L["short"]
        self.t_total = self.short_at + _word(sh, "388", 0.05)
        self.t_avg = self.short_at + _word(sh, "376", 0.6)
        self.t_ghost = self.short_at + _word(sh, "Neptune", 0.85) - 0.1
        self.orbit_at = self.short_at + sh.secs + 0.4
        ob = L["orbit"]
        self.moon0 = self.orbit_at + _word(ob, "farthest", 0.45) - 0.1
        self.moon1 = self.moon0 + 1.9
        self.payoff_at = max(self.orbit_at + ob.secs + 0.35, self.moon1 + 0.2)
        po = L["payoff"]
        self.t_fit = self.payoff_at + _word(po, "fits", 0.2) - 0.25
        self.t_spare = self.t_fit + 0.75
        self.t_days = self.payoff_at + _word(po, "9", 0.85)
        self.total = self.payoff_at + po.secs + 1.5

    # ---- the camera ----
    def camera(self, t: float) -> Cam:
        if t < self.rew:
            push = 1.0 + 0.03 * smooth(t / self.rew)
            return cam_between(dict(FLAT, k=KPX * push), LOW, 0.0)
        if t < self.rew_end:
            u = cv.ease((t - self.rew) / (self.rew_end - self.rew))
            return cam_between(dict(FLAT, k=KPX * 1.03), LOW, u)
        if t < self.cam0:
            drift = (t - self.rew_end) * 0.035
            return cam_between(dict(LOW, az=LOW["az"] + drift), FLAT, 0.0)
        if t < self.cam1:
            u = cv.ease((t - self.cam0) / (self.cam1 - self.cam0))
            low = dict(LOW, az=LOW["az"] + (self.cam0 - self.rew_end) * 0.035)
            return cam_between(low, FLAT, u)
        drift = (t - self.cam1) * 0.012
        return cam_between(dict(FLAT, az=FLAT["az"] + drift), FLAT, 0.0)

    # ---- the Moon's distance ----
    def moon_d(self, t: float) -> float:
        if t < self.rew:
            return MOON_FAR
        if t < self.rew_end:
            return MOON_FAR + (MOON_AVG - MOON_FAR) * cv.ease((t - self.rew) / (self.rew_end - self.rew))
        if t < self.moon0:
            return MOON_AVG
        return MOON_AVG + (MOON_FAR - MOON_AVG) * cv.ease((t - self.moon0) / (self.moon1 - self.moon0))

    # ---- each planet: how far in it is (0 = away, 1 = in its place) ----
    def placed(self, name: str, i: int, t: float) -> float:
        if t < self.rew:
            return 1.0
        if t < self.stack_at:
            u = (t - self.rew - (6 - i) * 0.07) / 0.5
            return 1 - cv.ease(max(0.0, min(1.0, u)))
        return max(0.0, min(1.0, (t - (self.land[name] - 0.6)) / 0.6))

    def neptune_in(self, t: float) -> float:
        """0: waiting beside the gap; 1: in its slot."""
        if t < self.rew:
            return 1.0
        if t < self.stack_at:
            return 1.0 - smooth((t - self.rew) / 0.4)
        return cv.ease((t - self.t_fit) / 0.7)


# --------------------------------------------------------------------------- #
# Drawing helpers
# --------------------------------------------------------------------------- #
def overlay():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return surf, ctx


def composite(img: Image.Image, surf) -> Image.Image:
    surf.flush()
    buf = np.ndarray((H, surf.get_stride() // 4, 4), np.uint8, surf.get_data())[:, :W].astype(np.float32)
    a = buf[..., 3:4] / 255
    if not a.any():
        return img
    base = np.asarray(img, np.float32)
    out = base * (1 - a) + buf[..., 2::-1]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def rgba(ctx, col, a: float) -> None:
    ctx.set_source_rgba(col[0] / 255, col[1] / 255, col[2] / 255, max(0.0, min(1.0, a)))


def label(img, x: float, y: float, rows, align: str, alpha: float) -> None:
    """rows: [(text, colour, font[, own alpha])] stacked down from y."""
    if alpha <= 0.01:
        return
    yy = y
    for i, row in enumerate(rows):
        txt, col, fnt = row[:3]
        a = alpha * (row[3] if len(row) > 3 else 1.0)
        if i:
            yy += (rows[i - 1][2].size + fnt.size) * 0.62
        if a <= 0.01:
            continue
        wdt = fnt.getlength(txt)
        lx = x if align == "left" else (x - wdt if align == "right" else x - wdt / 2)
        lx = max(30, min(W - 30 - wdt, lx))
        kit.solid_text(img, 0, yy, [(txt, col)], fnt, alpha=a, shadow=0.85, left=lx)


def fixed_digits(img, cx: float, y: float, s: str, fnt, col, alpha: float) -> None:
    """Digits in equal cells, so a ticking number never jitters."""
    if alpha <= 0.01:
        return
    cell = max(fnt.getlength(str(d)) for d in range(10))
    widths = [cell if ch.isdigit() else fnt.getlength(ch) for ch in s]
    x = cx - sum(widths) / 2
    for ch, wd in zip(s, widths):
        if ch != " ":
            off = (wd - fnt.getlength(ch)) / 2
            kit.solid_text(img, 0, y, [(ch, col)], fnt, alpha=alpha, shadow=0.8, left=x + off)
        x += wd


def bracket(ctx, x: float, y0: float, y1: float, col, a: float, side: int = 1) -> None:
    """A thin vertical dimension line with end ticks (ticks point back at the column)."""
    if a <= 0.01 or abs(y1 - y0) < 0.5:
        return
    rgba(ctx, col, a)
    ctx.set_line_width(2.2)
    ctx.move_to(x, y0)
    ctx.line_to(x, y1)
    for y in (y0, y1):
        ctx.move_to(x, y)
        ctx.line_to(x - side * 12, y)
    ctx.stroke()


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


def _soundtrack(plan: Plan, path: Path, clips) -> None:
    total = plan.total
    m = snd.Mixer(total)
    m.add(0.0, pad(total, [55.0, 82.4, 110.0, 146.8]), 0.3)
    m.add(0.2, snd.pluck(snd.scale_freq(12), dur=1.6, bright=0.5), 0.25)
    m.add(plan.rew - 0.05, whoosh(1.1, 1500, 140), 0.5)
    for i, (name, *_) in enumerate(PLANETS):
        big = name in ("jupiter", "saturn")
        m.add(plan.land[name] - 0.02, snd.pluck(snd.scale_freq(4 + i), dur=1.2, bright=0.6),
              0.3 if big else 0.2, float(np.clip((i - 3) / 6, -0.4, 0.4)))
        if big:
            m.add(plan.land[name] - 0.02, snd.thud(70, 0.3), 0.4)
    # Neptune bumps: a low knock, twice
    for dt_ in (0.0, 0.16):
        m.add(plan.land["neptune"] + 0.05 + dt_, snd.thud(58, 0.22), 0.5)
    m.add(plan.t_ghost, snd.pluck(snd.scale_freq(1), dur=1.4, bright=0.3), 0.22)
    m.add(plan.moon0, whoosh(plan.moon1 - plan.moon0 + 0.3, 90, 260, seed=9), 0.4)
    m.add(plan.t_fit + 0.55, snd.chord([snd.scale_freq(i) for i in (7, 9, 11, 14)], dur=3.0), 0.55)
    m.add(plan.t_fit + 0.55, snd.pluck(snd.scale_freq(14), dur=1.6, bright=0.8), 0.28)
    m.add(plan.t_days, snd.chord([snd.scale_freq(i) for i in (4, 7, 9, 11)], dur=plan.total - plan.t_days), 0.65)
    voice.voice_over(m, list(clips), bed=0.75)
    m.write(path, total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    clips = [(plan.hook_at, lines["hook"]), (plan.stack_at, lines["stack"]), (plan.short_at, lines["short"]),
             (plan.orbit_at, lines["orbit"]), (plan.payoff_at, lines["payoff"])]
    caps = []
    for (at, line), key in zip(clips[1:], ["stack", "short", "orbit", "payoff"]):
        caps += kit.captions(at, line, SCRIPT[key][1])

    bg0 = sp.starfield(seed=6, cx=CX, cy=900, band_angle=-34.0)
    bg = np.concatenate([bg0, bg0[::-1]], axis=0)
    tex = s3.textures()
    tex["moon"] = ArrayTexture(moon_map())

    f_name, f_small = kit.sans(26, "bold"), kit.sans(22, "bold")
    f_num, f_tag = kit.sans(64, "black"), kit.sans(30, "bold")
    f_hero = kit.sans(32, "bold")
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)
    order = {p[0]: i for i, p in enumerate(PLANETS)}
    spin = {p[0]: p[2] for p in PLANETS}
    pole = {p[0]: p[3] for p in PLANETS}
    spin.update(earth=0.3, moon=0.02)
    pole.update(earth=EARTH_POLE, moon=(0.0, 1.0, 0.0))
    sides = {"mercury": 1, "venus": -1, "mars": 1, "jupiter": -1, "saturn": 1, "uranus": -1, "neptune": -1}

    def frame(t: float) -> Image.Image:
        cam = plan.camera(t)
        D = plan.moon_d(t)
        shift = int(round(260 * (math.asin(max(-1.0, min(1.0, -cam.look[1]))) / LOW["e"])))
        arr = bg[shift:shift + H].copy()
        light = cam.to_cam_dir(LIGHT)
        nep_in = plan.neptune_in(t)
        in_flat = t < plan.rew or t >= plan.cam1

        # ---- where everything is ----
        bodies = {}
        for name in ["earth", "moon"] + [p[0] for p in PLANETS]:
            s = 0.0 if name == "earth" else (D if name == "moon" else SLOT[name])
            x, y, z = (float(v) for v in cam.project(np.array([0.0, -s, 0.0])))
            if z <= 1000:
                continue
            r = cam.f * RAD[name] / z
            a, dx, dy = 1.0, 0.0, 0.0
            if name in order:
                u = plan.placed(name, order[name], t)
                if u <= 0.0:
                    continue
                k = 1 - cv.ease_out(u) if t >= plan.stack_at else 1 - u
                dx, dy = sides[name] * (720 + r) * k, -160 * k
                a = smooth(u * 2.5)
            bodies[name] = dict(x=x + dx, y=y + dy, z=z, r=r, a=a, sx=x, sy=y, s=s)
        nb = bodies.get("neptune")
        if nb and nep_in < 1:
            wait = -(2 * nb["r"] + 70)
            knock = 0.0
            if t >= plan.land["neptune"]:
                tb = t - plan.land["neptune"]
                knock = 22 * math.sin(min(tb, 0.5) / 0.5 * math.pi * 2) * math.exp(-tb * 4) if tb < 0.5 else 0.0
            nb["x"] += (wait + knock) * (1 - nep_in)

        mo = bodies.get("moon")
        if mo and mo["r"] > 1.0:          # a faint cool halo, so the eye finds the small Moon
            s3.glow(arr, mo["x"], mo["y"], mo["r"], 0.35, col=(200, 212, 235), reach=2.0)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        # ---- ghost slot and measurements (under the planets) ----
        surf, ctx = overlay()
        y_of = lambda s: float(cam.project(np.array([0.0, -s, 0.0]))[1])
        nep_r = bodies["neptune"]["r"] if "neptune" in bodies else 0.0
        ghost = smooth((t - plan.t_ghost) / 0.35) * (1 - smooth((t - plan.t_fit) / 0.3)) if t >= plan.stack_at else 0.0
        fits_now = gap_of(D) >= TOTAL
        if ghost > 0.01 and nb:
            gcol = CORAL if not fits_now else (232, 214, 170)
            rgba(ctx, gcol, 0.85 * ghost)
            ctx.set_line_width(2.0)
            ctx.set_dash([7, 7])
            ctx.arc(nb["sx"], nb["sy"], nep_r, 0, 2 * math.pi)
            ctx.stroke()
            ctx.set_dash([])
            over = NEP_FAR - (D - R_MOON)
            if over > 0:
                xb = CX + nep_r + 30
                bracket(ctx, xb, y_of(D - R_MOON), y_of(NEP_FAR), CORAL, 0.95 * ghost, side=1)
        spare_a = smooth((t - plan.t_spare) / 0.4) if t >= plan.stack_at else 1.0
        if spare_a > 0.01 and in_flat:
            xb = CX + nep_r + 30
            bracket(ctx, xb, y_of(NEP_FAR), y_of(D - R_MOON), GOLD, spare_a, side=1)
        img = composite(img, surf)

        # ---- the bodies, far to near ----
        for name, b in sorted(bodies.items(), key=lambda kv: -kv[1]["z"]):
            nm = name
            ring = None
            if name == "saturn":
                ring = np.array(pole["saturn"]) / np.linalg.norm(pole["saturn"])
            s3.draw_planet(img, cam, nm, b["x"], b["y"], b["r"], light, rot=1.1 + t * spin[name], alpha=b["a"],
                           pole=pole[name], ring_normal=ring, clouds_rot=t * 0.04)

        # ---- labels (left of the row, nudged apart top to bottom) ----
        lab_a = 1.0 if t < plan.rew else (1 - smooth((t - plan.rew) / 0.3) if t < plan.stack_at else 1.0)
        rows = []
        for name in ["earth"] + [p[0] for p in PLANETS]:
            b = bodies.get(name)
            if not b or not (-40 < b["y"] < H + 40):
                continue
            ext = b["r"] * (2.28 if name == "saturn" else 1.0)
            a = lab_a * (1.0 if name == "earth" else smooth((plan.placed(name, order[name], t) - 0.75) / 0.25))
            if name == "neptune" and nep_in < 1:
                a *= 1.0
            rows.append([b["y"], b["x"] - ext - 30, name, a])
        rows.sort(key=lambda r: r[0])
        last = -1e9
        for r in rows:
            r[0] = max(r[0], last + 28)
            last = r[0]
        for y, x, name, a in rows:
            a *= smooth((x - 150) / 60)                 # no room beside a huge planet: hide the name
            if 380 < y < 1640:
                col = WHITE if name == "earth" else NAME
                label(img, x, y, [(name.upper(), col, f_name if name in ("earth", "jupiter", "saturn") else f_small)],
                      "right", a)
        if mo and 380 < mo["y"] < 1700:
            label(img, mo["x"], mo["y"] + mo["r"] + 24, [("MOON", WHITE, f_name)], "centre",
                  smooth((mo["r"] - 1.2) / 1.5))

        # ---- measurement labels ----
        if ghost > 0.01 and nb and NEP_FAR - (D - R_MOON) > 600:
            over = NEP_FAR - (D - R_MOON)
            yy = (y_of(D - R_MOON) + y_of(NEP_FAR)) / 2
            label(img, CX + nep_r + 50, yy - 14, [(f"{over:,.0f} km".replace(",", ","), CORAL, f_tag),
                                                 ("too long", CORAL, f_small)], "left", ghost)
        if spare_a > 0.01 and in_flat:
            spare = (D - R_MOON) - NEP_FAR
            yy = (y_of(D - R_MOON) + y_of(NEP_FAR)) / 2
            label(img, CX + nep_r + 50, yy - 14, [(f"{round(spare, -2):,.0f} km", GOLD, f_tag),
                                                 ("to spare", GOLD, f_small)], "left", spare_a)

        # ---- the scoreboard ----
        sa = smooth((t - plan.stack_at - 0.1) / 0.4) if t >= plan.stack_at else 0.0
        if sa > 0:
            gap = gap_of(D)
            done = t >= plan.t_fit + 0.6
            label(img, 270, LBL_Y, [("GAP: EARTH TO MOON", MUTED, f_small)], "centre", sa)
            fixed_digits(img, 270, NUM_Y, f"{gap:,.0f} km", f_num, GOLD if done else WHITE, sa)
            have = 0.0
            for name, dia, *_ in PLANETS:
                u = (t - plan.land[name] + 0.05) / 0.35
                have += dia * cv.ease(max(0.0, min(1.0, u)))
            label(img, 810, LBL_Y, [("ALL 7 PLANETS", MUTED, f_small)], "centre", sa)
            over = have > gap + 1 and t < plan.t_fit + 0.6
            fixed_digits(img, 810, NUM_Y, f"{have:,.0f} km", f_num, CORAL if over else WHITE, sa)
            da = smooth((t - plan.t_days) / 0.4) if t >= plan.stack_at else 0.0
            if da > 0:
                kit.solid_text(img, W / 2, DAYS_Y, [("FITS ABOUT ", MUTED), ("9 DAYS", GOLD), (" A MONTH", MUTED)],
                               f_hero, alpha=da, shadow=0.85)
        if t < plan.rew + 0.4:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            kit.hook(img, HOOK, t if t < hook_end + 0.1 else 99.0, t0=HOOK_T0, alpha=ha)
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, path, clips)

    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
