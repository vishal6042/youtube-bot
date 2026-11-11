"""Voyager 1 reaches one light-day from Earth (18 November 2026).

Seen in 3D: the camera hangs above and behind Earth, looking down 40 degrees
across the planets' plane. A light signal leaves Earth as a glowing bubble
(the bright ring is where it crosses the plane). The camera rides the
bubble: it stays the same size on screen while the Solar System shrinks
inside it, so the pull-back IS the distance. It opens on a close-up of Earth.
Each body lights up as the light reaches it, spoken on the word: the Sun at
8 minutes, Jupiter 43, Neptune 4 hours. Then 20 hours of nothing, until the
probe. Last beat: the light keeps going to Proxima Centauri, 4.2
light-years, and the trip at Voyager's speed (~75,000 years).

Honest numbers: planet positions are worked out for 18 Nov 2026 06:16 UTC
(NASA's time for the crossing) from JPL's orbital elements, so every light
time on screen is the real one from Earth that day. Voyager sits in its real
3D direction (35 degrees above the plane, with a drop line to show it).
Proxima (44 degrees below) is folded into the plane at its true longitude so
the light ring visibly reaches it. Planet sizes are exaggerated so they can
be seen; distances are not.

Hook: the first frame is the finished moment, the light just reaching
Voyager, with the question; then it rewinds into Earth and lets the light go.
"""
from __future__ import annotations

import math
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
from .canvas import GOLD, MUTED, WHITE, H, W, mix, scale

FPS = 60
JD = sp.julian(2026, 11, 18, 6 + 16 / 60)
VOY_DIR = sp.ecliptic_dir(258.25, 12.0)              # Voyager 1, Ophiuchus (2026)
PROX_DIR = sp.ecliptic_dir(217.429, -62.680)         # Proxima Centauri
PROX_LY = 4.2465
VOY_KMS = 16.95
LAUNCH_YEAR = 1977

# The camera (see space3d.Camera): looks down PHI from DIST x V behind Earth.
PHI, DIST, FOCAL = math.radians(40), 2.0, 700.0
EX, EY = 540.0, 1000.0          # Earth on screen (the camera aims at it)
R0 = 0.42                       # AU: the light's reach before the camera pulls back
TAU_S = 20.0                    # seconds: the log-time knee for the clock's pace
TOP_LABEL_Y, CLOCK_Y, DIST_Y = 130, 207, 280
WARM = (255, 226, 182)
HOOK_T0 = -0.45                 # the hook is already rising on frame one
VOICE, RATE = "en-US-AndrewNeural", "+0%"   # English-only Andrew (the Multilingual one read planet names as French)

HOOK = [[("A", WHITE), ("signal", WHITE), ("from", WHITE), ("Voyager", WHITE), ("1", WHITE)],
        [("now", WHITE), ("takes", WHITE), ("a", GOLD), ("full", GOLD), ("day.", GOLD)]]

SCRIPT = {
    "hook": ("A signal from Voyager 1 now takes a full day to reach us.", None),
    "ladder": ("Light from Earth reaches the Sun in 8 minutes. Jupiter, 43. Neptune, the last planet: 4 hours.",
               [("Light from Earth", 3), ("reaches the Sun", 3), ("in *8 minutes*", 3), ("Jupiter: *43 min*", 2),
                ("Neptune, the last planet:", 4), ("*4 hours*", 1)]),
    "gap": ("After that, no more planets. Just dark, for 20 more hours.",
            [("After that,", 2), ("no more planets", 3), ("Just dark", 2), ("for *20 more hours*", 4)]),
    "payoff": ("On November 18th, Voyager 1 becomes the first spacecraft ever to be one light-day from Earth. "
               "49 years after launch.",
               [("On *18 November*", 2), ("Voyager 1 becomes", 3), ("the first spacecraft ever", 4),
                ("to be *one light-day*", 4), ("from Earth", 2), ("*49 years* after launch", 3)]),
    "star": ("And the nearest star? 4.2 light-years away. At Voyager's speed, that's 75,000 years.",
             [("And the nearest star?", 4), ("*4.2 light-years* away", 3), ("At Voyager's speed", 3),
              ("that's *75,000 years*", 2)]),
}

# name, display size (AU at V = 1; grows as V**0.45 so planets stay visible),
# shows its light time, spin (rad/s)
BODIES = [
    ("mercury", 0.13, False, 0.12),
    ("venus", 0.21, False, 0.06),
    ("mars", 0.17, False, 0.2),
    ("jupiter", 0.46, True, 0.5),
    ("saturn", 0.40, True, 0.45),
    ("uranus", 0.30, True, 0.3),
    ("neptune", 0.30, True, 0.3),
]
EARTH_SIZE, SUN_SIZE = 0.29, 0.24
SIZE_EXP = 0.45
SATURN_POLE = np.array([math.sin(math.radians(26.7)), 0.0, math.cos(math.radians(26.7))])
KEY = np.array([-0.45, 0.55, -0.7])             # fill light from the camera's upper left


# --------------------------------------------------------------------------- #
# Geometry: world coords (AU) with Earth at the origin, X right, Y forward
# (towards Voyager's longitude), Z up (ecliptic north)
# --------------------------------------------------------------------------- #
def layout() -> dict:
    E = sp.helio("earth", JD)
    lv = math.atan2(VOY_DIR[1], VOY_DIR[0])
    F = np.array([math.cos(lv), math.sin(lv), 0.0])
    X = np.array([math.sin(lv), -math.cos(lv), 0.0])
    Z = np.array([0.0, 0.0, 1.0])

    def world(v) -> np.ndarray:
        return np.array([v @ X, v @ F, v @ Z])
    out = {"sun": dict(P=world(-E))}
    for name, *_ in BODIES:
        out[name] = dict(P=world(sp.helio(name, JD) - E))
    voy = world(VOY_DIR)
    out["voyager"] = dict(P=voy / np.linalg.norm(voy) * sp.LIGHT_DAY_AU)
    pr = world(PROX_DIR)
    pr[2] = 0.0          # folded into the plane, so the light ring visibly reaches it
    out["proxima"] = dict(P=pr / np.linalg.norm(pr) * PROX_LY * sp.LY_AU)
    for v in out.values():
        v["d"] = float(np.linalg.norm(v["P"]))
    return out


def q_of(tau: float) -> float:
    return math.log1p(tau / TAU_S)


def tau_of(q: float) -> float:
    return TAU_S * math.expm1(q)


def reff(R: float) -> float:
    """What the camera frames: the light front, but never less than R0 (soft)."""
    return (R ** 4 + R0 ** 4) ** 0.25


# Timeline
# --------------------------------------------------------------------------- #
class Plan:
    def __init__(self, L: dict[str, voice.Line], geo: dict):
        self.hook_at = 0.25
        self.rew = max(3.7, self.hook_at + L["hook"].secs + 0.4)
        self.rew_end = self.rew + 0.95
        self.launch = self.rew_end + 0.35
        self.ladder_at = self.launch + 0.05
        lad = L["ladder"]
        self.t_sun = self.ladder_at + _word(lad, "Sun", 0.3) + 0.12
        self.t_jup = self.ladder_at + _word(lad, "Jupiter", 0.55)
        self.t_nep = self.ladder_at + _word(lad, "Neptune", 0.75)
        self.gap_at = self.ladder_at + lad.secs + 0.35
        self.t_voy = self.gap_at + L["gap"].secs + 0.55
        self.payoff_at = self.t_voy + 0.6
        self.t49 = self.payoff_at + _word(L["payoff"], "49", 0.8)
        self.star_at = self.payoff_at + L["payoff"].secs + 0.5
        st = L["star"]
        self.zoom0 = self.star_at + 0.15
        self.t_prox = self.star_at + _word(st, "light", 0.4) + 0.25
        self.t75 = self.star_at + _word(st, "75", 0.8)
        self.total = self.star_at + st.secs + 1.7

        tau_s = lambda name: geo[name]["d"] * sp.AU_LIGHT_S
        knots_t = [self.launch, self.t_sun, self.t_jup, self.t_nep, self.t_voy]
        knots_q = [0.0, q_of(tau_s("sun")), q_of(tau_s("jupiter")), q_of(tau_s("neptune")), q_of(86400.0)]
        self.ride = PchipInterpolator(knots_t, knots_q)
        self.q_day = q_of(86400.0)
        self.q_prox = q_of(geo["proxima"]["d"] * sp.AU_LIGHT_S)
        self.q_cold0 = q_of(20.5 * 3600)
        self.cold_hit = self.rew - 0.45
        # When the front reaches each body (for pings and labels).
        ts = np.linspace(self.launch, self.t_voy, 6000)
        qs = self.ride(ts)
        self.hit = {}
        for name in ["sun"] + [b[0] for b in BODIES]:
            self.hit[name] = float(np.interp(q_of(tau_s(name)), qs, ts))
        self.hit["voyager"] = self.t_voy
        self.hit["proxima"] = self.t_prox

    def q(self, t: float) -> float:
        if t < self.rew:
            u = min(1.0, t / self.cold_hit)
            return self.q_cold0 + (self.q_day - self.q_cold0) * (1 - (1 - u) ** 2.2)
        if t < self.rew_end:
            u = (t - self.rew) / (self.rew_end - self.rew)
            return self.q_day * (1 - cv.ease(u))
        if t < self.launch:
            return 0.0
        if t < self.t_voy:
            return float(self.ride(t))
        if t < self.zoom0:
            return self.q_day
        u = cv.ease((t - self.zoom0) / (self.t_prox - self.zoom0))
        return self.q_day + (self.q_prox - self.q_day) * u

    def push(self, t: float) -> float:
        """A slow push-in while the picture holds still."""
        if t < self.rew:
            return 1.0 + 0.035 * t / self.rew
        if t < self.rew_end:
            return 1.035 - 0.035 * cv.ease((t - self.rew) / (self.rew_end - self.rew))
        if self.t_voy <= t < self.zoom0:
            return 1.0 + 0.05 * cv.ease((t - self.t_voy) / (self.zoom0 - self.t_voy))
        if t >= self.zoom0:
            return 1.05 - 0.05 * cv.ease((t - self.zoom0) / (self.t_prox - self.zoom0))
        return 1.0

    def phase_after_day(self, t: float) -> bool:
        return t >= self.t_voy - 0.02 or t < self.rew_end


def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


# --------------------------------------------------------------------------- #
# Drawing helpers
# --------------------------------------------------------------------------- #
def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


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


def label(img, x: float, y: float, lines, align: str, alpha: float) -> None:
    """lines: [(text, colour, font[, own alpha])], stacked down from y (the first
    line's centre). align: left | right | centre."""
    if alpha <= 0.01:
        return
    yy = y
    for i, row in enumerate(lines):
        txt, col, fnt = row[:3]
        a = alpha * (row[3] if len(row) > 3 else 1.0)
        if i:
            yy += (lines[i - 1][2].size + fnt.size) * 0.62
        if a <= 0.01:
            continue
        wdt = fnt.getlength(txt)
        lx = x if align == "left" else (x - wdt if align == "right" else x - wdt / 2)
        lx = max(36, min(W - 36 - wdt, lx))
        kit.solid_text(img, 0, yy, [(txt, col)], fnt, alpha=a, shadow=0.85, left=lx)


def label_height(lines) -> float:
    return sum((a[2].size + b[2].size) * 0.62 for a, b in zip(lines, lines[1:]))


def tracked(s: str) -> str:
    return s.upper()


def fixed_digits(img, cx: float, y: float, s: str, fnt, col, alpha: float) -> None:
    """Draw text with every digit in a cell of the same width (no jitter as it ticks)."""
    cell = max(fnt.getlength(str(d)) for d in range(10))
    widths = [cell if ch.isdigit() else fnt.getlength(ch) for ch in s]
    x = cx - sum(widths) / 2
    for ch, wd in zip(s, widths):
        if ch != " ":
            off = (wd - fnt.getlength(ch)) / 2
            kit.solid_text(img, 0, y, [(ch, col)], fnt, alpha=alpha, shadow=0.8, left=x + off)
        x += wd


def clock_text(tau: float) -> str:
    if tau < 2 * 86400:
        s = int(round(tau))
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    days = tau / 86400
    if days < 365.25:
        return f"{days:,.0f} days"
    return f"{days / 365.25:.1f} years"


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
    """A slow, soft drone: detuned sines with a gentle swell."""
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
    m.add(0.0, pad(total, [55.0, 82.4, 110.0, 164.8]), 0.32)
    m.add(plan.cold_hit, snd.pluck(snd.scale_freq(12), dur=1.6, bright=0.5), 0.3)
    m.add(plan.rew - 0.05, whoosh(1.0, 1500, 140), 0.5)
    m.add(plan.launch - 0.03, snd.thud(80, 0.3), 0.55)
    order = ["sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]
    hits = sorted(order, key=lambda n: plan.hit[n])
    for i, n in enumerate(hits):
        big = n in ("sun", "jupiter", "neptune")
        m.add(plan.hit[n], snd.pluck(snd.scale_freq(5 + i), dur=1.1, bright=0.6),
              0.34 if big else 0.16, float(np.clip((i - 4) / 6, -0.5, 0.5)))
    m.add(plan.t_voy, snd.chord([snd.scale_freq(i) for i in (8, 10, 12, 15)], dur=4.0), 0.6)
    m.add(plan.t_voy, snd.pluck(snd.scale_freq(15), dur=1.8, bright=0.8), 0.3)
    m.add(plan.zoom0, whoosh(plan.t_prox - plan.zoom0 + 0.3, 320, 70, seed=9), 0.45)
    m.add(plan.t_prox, snd.pluck(snd.scale_freq(9), dur=1.8, bright=0.5), 0.3)
    m.add(plan.t75, snd.chord([snd.scale_freq(i) for i in (5, 8, 10, 12)], dur=plan.total - plan.t75), 0.75)
    voice.voice_over(m, list(clips), bed=0.75)
    m.write(path, total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _poly(ctx, xs, ys, zs, zmin) -> None:
    """Stroke a projected polyline, breaking it where it passes behind the camera."""
    started = False
    for x, y, z in zip(xs, ys, zs):
        if z < zmin or not (-4000 < x < 5000 and -4000 < y < 6000):
            started = False
            continue
        if started:
            ctx.line_to(x, y)
        else:
            ctx.move_to(x, y)
            started = True
    ctx.stroke()


def build(ffmpeg: str, seed: int = 7):
    geo = layout()
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines, geo)
    total = plan.total
    clips = [(plan.hook_at, lines["hook"]), (plan.ladder_at, lines["ladder"]), (plan.gap_at, lines["gap"]),
             (plan.payoff_at, lines["payoff"]), (plan.star_at, lines["star"])]
    caps = []
    for (at, line), key in zip(clips[1:], ["ladder", "gap", "payoff", "star"]):
        caps += kit.captions(at, line, SCRIPT[key][1])

    bg = sp.starfield(seed=4, cx=EX, cy=EY)
    s3.textures()
    probe = s3.probe_master(560)
    sun_P = geo["sun"]["P"]
    voy_P = geo["voyager"]["P"]
    prox_P = geo["proxima"]["P"]
    size = {b[0]: b[1] for b in BODIES}
    size.update(earth=EARTH_SIZE, sun=SUN_SIZE)
    spin = {b[0]: b[3] for b in BODIES}
    spin.update(earth=0.32, sun=0.04)
    timed = {b[0]: b[2] for b in BODIES}
    timed["sun"] = True
    circle = np.linspace(0, 2 * math.pi, 241)
    ref_cam = s3.Camera(sp.LIGHT_DAY_AU, PHI, DIST, FOCAL, EX, EY)
    voy_zref = float(ref_cam.project(voy_P)[2])

    f_name, f_small = kit.sans(24, "bold"), kit.sans(22, "bold")
    f_time, f_clock = kit.sans(30, "bold"), kit.sans(96, "black")
    f_dist, f_big = kit.sans(34, "semi"), kit.sans(96, "black")
    name_col = (214, 218, 228)
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)

    def frame(t: float) -> Image.Image:
        q = plan.q(t)
        tau = tau_of(q)
        R = tau / sp.AU_LIGHT_S
        push = plan.push(t)
        V = reff(R) / push
        cam = s3.Camera(V, PHI, DIST, FOCAL, EX, EY)
        prox_phase = t >= plan.zoom0
        rewinding = plan.rew <= t < plan.launch
        arr = bg.copy()

        # ---- where everything is on screen ----
        bodies = {}
        for name in ["sun", "earth"] + [b[0] for b in BODIES]:
            P = np.zeros(3) if name == "earth" else geo[name]["P"]
            x, y, z = cam.project(P)
            if z <= V * 0.05:
                continue
            r = FOCAL * size[name] * V ** SIZE_EXP / z
            bodies[name] = dict(P=P, x=float(x), y=float(y), z=float(z), r=float(r))
        e = bodies["earth"]
        vx, vy, vz = (float(v) for v in cam.project(voy_P))
        voy_w = min(250.0, 172.0 * voy_zref / vz) if vz > 0 else 0.0

        # ---- the light: a glowing bubble, brightest where it crosses the plane ----
        b_gain = 1.0
        if plan.rew_end <= t < plan.launch:
            b_gain = 0.0
        elif plan.launch <= t < plan.launch + 0.3:
            b_gain = smooth((t - plan.launch) / 0.3)
        gold = 0.0
        if t >= plan.t_voy - 0.05 and not prox_phase:
            gold = 0.7 * kit.flash(t, plan.t_voy + 0.2, 0.6)
        col = tuple(np.array([1.0, 0.88, 0.70]) * (1 - gold) + np.array([1.0, 0.78, 0.40]) * gold)
        s3.bubble(arr, cam, R, b_gain, col)

        # ---- line work ----
        surf, ctx = cairo_layer()
        zmin = V * 0.08
        sx, sy = bodies["sun"]["x"], bodies["sun"]["y"]
        for name in ["earth"] + [b[0] for b in BODIES]:
            P = np.zeros(3) if name == "earth" else geo[name]["P"]
            rad = float(np.hypot(*(P - sun_P)[:2]))
            pts = sun_P[None, :] + np.stack([np.cos(circle) * rad, np.sin(circle) * rad, 0 * circle], -1)
            xs, ys, zs = cam.project(pts)
            size_px = FOCAL * rad / max(float(cam.project(sun_P)[2]), 1e-6)
            a = 0.34 * smooth((size_px - 4) / 12)
            if a > 0.005:
                rgb(ctx, (150, 168, 200), a)
                ctx.set_line_width(1.4)
                _poly(ctx, xs, ys, zs, zmin)
        # where the light crosses the planets' plane: a bright ring
        if b_gain > 0 and R > 0:
            pts = np.stack([np.cos(circle) * R, np.sin(circle) * R, 0 * circle], -1)
            xs, ys, zs = cam.project(pts)
            for wdt, a in ((7.0, 0.16), (2.0, 0.85)):
                rgb(ctx, tuple(int(255 * c) for c in col), a * b_gain)
                ctx.set_line_width(wdt)
                _poly(ctx, xs, ys, zs, zmin)
        # Voyager: its path out of the plane, and a drop line showing its height
        path_a = (1.0 if t < plan.rew else smooth((R - 40) / 40) if t >= plan.launch else 0.0)
        path_a *= 1 - smooth((t - plan.zoom0) / 0.8)
        if path_a > 0.01:
            foot = np.array([voy_P[0], voy_P[1], 0.0])
            fx, fy, fz = (float(v) for v in cam.project(foot))
            ctx.set_dash([5, 9])
            rgb(ctx, (176, 184, 202), 0.45 * path_a)
            ctx.set_line_width(1.6)
            ctx.move_to(sx, sy)
            ctx.line_to(vx, vy)
            ctx.stroke()
            rgb(ctx, (176, 184, 202), 0.35 * path_a)
            ctx.move_to(vx, vy)
            ctx.line_to(fx, fy)
            ctx.stroke()
            ctx.set_dash([])
            rgb(ctx, (176, 184, 202), 0.35 * path_a)
            ctx.save()
            ctx.translate(fx, fy)
            ctx.scale(1.0, math.sin(PHI))
            ctx.arc(0, 0, 9, 0, 2 * math.pi)
            ctx.restore()
            ctx.stroke()
        for name, t_hit in plan.hit.items():
            if name in ("proxima", "voyager") or not (t_hit <= t < t_hit + 0.9) or t < plan.launch:
                continue
            b = bodies.get(name)
            if not b:
                continue
            u = (t - t_hit) / 0.9
            rgb(ctx, WARM, 0.8 * (1 - u) ** 1.6)
            ctx.set_line_width(2.0)
            ctx.arc(b["x"], b["y"], b["r"] * 1.15 + 8 + 50 * cv.ease_out(u), 0, 2 * math.pi)
            ctx.stroke()
        if prox_phase:
            r_ld = FOCAL * sp.LIGHT_DAY_AU / e["z"]
            a = smooth((r_ld - 1.5) / 6)
            if a > 0:
                rgb(ctx, GOLD, 0.75 * a)
                ctx.set_line_width(2.0)
                ctx.arc(e["x"], e["y"], r_ld, 0, 2 * math.pi)
                ctx.stroke()
            px_, py_, pz_ = (float(v) for v in cam.project(prox_P))
            la = smooth((t - plan.t_prox + 0.6) / 0.6)
            if la > 0 and pz_ > 0:
                foot = np.array([prox_P[0], prox_P[1], 0.0])
                fx, fy, _ = (float(v) for v in cam.project(foot))
                ctx.set_dash([5, 9])
                rgb(ctx, (190, 196, 210), 0.4 * la)
                ctx.set_line_width(1.6)
                ctx.move_to(e["x"], e["y"])
                ctx.line_to(px_, py_)
                ctx.stroke()
                rgb(ctx, (190, 196, 210), 0.3 * la)
                ctx.move_to(px_, py_)
                ctx.line_to(fx, fy)
                ctx.stroke()
                ctx.set_dash([])
        arr += layer_rgb(surf)

        # ---- glows: the Sun, and a flash where the light arrives ----
        sb = bodies["sun"]
        s3.glow(arr, sb["x"], sb["y"], max(sb["r"], 6), 1.0)
        if t >= plan.launch:
            for name, t_hit in plan.hit.items():
                fl = kit.flash(t, t_hit + 0.1, 0.3)
                if fl < 0.02:
                    continue
                if name == "voyager":
                    s3.glow(arr, vx, vy, voy_w * 0.25, fl * 1.3)
                elif name == "proxima":
                    pass
                elif name in bodies:
                    b = bodies[name]
                    s3.glow(arr, b["x"], b["y"], max(b["r"], 5), fl * 0.8)
        if t < plan.rew:
            fl = kit.flash(t, plan.cold_hit + 0.15, 0.45)
            if fl > 0.02:
                s3.glow(arr, vx, vy, voy_w * 0.25, fl * 1.3)
        if prox_phase:
            px_, py_, pz_ = (float(v) for v in cam.project(prox_P))
            if pz_ > 0:
                s3.glow(arr, px_, py_, 5, 0.9 + 1.2 * kit.flash(t, plan.t_prox + 0.1, 0.35), col=(255, 150, 110))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        # ---- the bodies, far to near ----
        for name, b in sorted(bodies.items(), key=lambda kv: -kv[1]["z"]):
            if name not in ("sun", "earth"):
                sd = math.hypot(b["x"] - e["x"], b["y"] - e["y"])
                a = smooth((sd - (b["r"] + e["r"]) * 0.6) / max(6, b["r"]))
            elif name == "earth":
                a = 1 - smooth((t - plan.zoom0 - 0.6) / 0.8)
            else:
                a = 1.0
            if name == "sun":
                s3.draw_planet(img, cam, "sun", b["x"], b["y"], b["r"], np.array([0, 0, -1.0]), rot=t * spin["sun"],
                               emissive=True)
                continue
            Lw = sun_P - b["P"]
            n = np.linalg.norm(Lw)
            Lc = cam.to_cam_dir(Lw / n if n > 0 else np.array([0, 1.0, 0]))
            light = 0.55 * Lc + 0.45 * KEY / np.linalg.norm(KEY)
            fl = kit.flash(t, plan.hit[name] + 0.1, 0.3) if (name in plan.hit and t >= plan.launch) else 0.0
            s3.draw_planet(img, cam, name, b["x"], b["y"], b["r"], light, rot=1.3 + t * spin[name], alpha=a,
                           pole=SATURN_POLE if name == "saturn" else (0, 0, 1),
                           ring_normal=SATURN_POLE if name == "saturn" else None,
                           clouds_rot=t * 0.05, flash=fl * 0.6)
        # Voyager
        v_a = (1.0 if (vz > 0 and vy > -200) else 0.0) * (1 - smooth((t - plan.zoom0 - 0.2) / 0.5))
        if v_a > 0 and voy_w > 2:
            s3.paste_scaled(img, probe, vx, vy, voy_w, v_a)

        # ---- labels ----
        lab_a = 1.0 if t >= plan.launch else (1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.3))
        if t >= plan.launch:
            ea = smooth((2.2 - R) / 0.8)
            label(img, e["x"], e["y"] + e["r"] + 30, [(tracked("Earth"), name_col, f_name)], "centre", ea)
            for name in ["sun"] + [b[0] for b in BODIES if b[0] not in ("mercury", "venus")]:
                b = bodies.get(name)
                if not b:
                    continue
                sd = math.hypot(b["x"] - e["x"], b["y"] - e["y"])
                crowd = smooth((sd - b["r"] - 80) / 30)
                onscreen = 30 < b["x"] < W - 30 and 330 < b["y"] < H - 60
                if crowd <= 0 or not onscreen:
                    continue
                big = name in ("sun", "jupiter", "saturn", "uranus", "neptune")
                fn = f_name if big else f_small
                rows = [(tracked(name), name_col if big else scale(name_col, 0.85), fn)]
                if timed[name]:
                    ta = smooth((t - plan.hit[name]) / 0.3)
                    rows.append((sp.light_time(geo[name]["d"] * sp.AU_LIGHT_S / 60), GOLD, f_time, ta))
                ext = b["r"] * (2.3 if name == "saturn" else 1.0)
                ly = b["y"] - min(ext, b["r"] * 1.1) - 16 - label_height(rows) - fn.size * 0.4
                if ly < 340:                       # no room above: put it below
                    ly = b["y"] + ext * 0.6 + 18 + fn.size * 0.5
                label(img, b["x"], ly, rows, "centre", crowd)
        if t >= plan.t_nep + 0.5 or t < plan.rew_end:
            # "All 8 planets" once they huddle together
            nb = bodies.get("neptune")
            if nb:
                nep_w = FOCAL * float(np.hypot(*(geo["neptune"]["P"] - sun_P)[:2])) / bodies["sun"]["z"]
                ga = smooth((150 - nep_w) / 40) * smooth((nep_w - 14) / 10)
                label(img, e["x"] + nep_w + 22, e["y"] - 4, [("ALL 8 PLANETS", scale(name_col, 0.9), f_small)],
                      "left", ga * (lab_a if t < plan.rew_end else 1.0))
        if v_a > 0 and 40 < vy < H:
            rows = [("VOYAGER 1", WHITE, kit.sans(30, "bold"))]
            if t >= plan.t_voy:
                rows.append((sp.km_text(sp.LIGHT_DAY_AU * sp.AU_KM), GOLD, f_time,
                             smooth((t - plan.t_voy - 0.2) / 0.4)))
                rows.append((f"Launched {LAUNCH_YEAR}", name_col, f_small, smooth((t - plan.t49) / 0.4)))
            seen = smooth((R - 70) / 30) if t >= plan.launch else lab_a
            label(img, vx + voy_w * 0.42, vy - voy_w * 0.32 - 12 - label_height(rows), rows, "left", v_a * seen)
        if prox_phase:
            px_, py_, pz_ = (float(v) for v in cam.project(prox_P))
            pa = smooth((t - plan.t_prox + 0.1) / 0.4)
            label(img, px_ + 22, py_ - 20, [("PROXIMA CENTAURI", WHITE, kit.sans(28, "bold")),
                                            ("4.2 light-years", GOLD, f_time, pa)], "left", pa)
            r_ld = FOCAL * sp.LIGHT_DAY_AU / e["z"]
            la = smooth((r_ld - 70) / 50) * smooth((t - plan.zoom0) / 0.3)
            if la > 0:
                label(img, e["x"], e["y"] - r_ld - 30, [("1 LIGHT-DAY", GOLD, f_small)], "centre", la)

        # ---- the clock (top) ----
        ca = smooth((t - plan.launch + 0.1) / 0.4)
        if ca > 0:
            label(img, W / 2, TOP_LABEL_Y, [(tracked("Light-travel time from Earth"), MUTED, f_small)], "centre", ca)
            fin = t >= plan.t_voy - 0.01
            ccol = GOLD if (fin and (t < plan.zoom0 or t >= plan.t_prox)) else WHITE
            fixed_digits(img, W / 2, CLOCK_Y, clock_text(tau), f_clock, ccol, ca)
            label(img, W / 2, DIST_Y, [(sp.km_text(R * sp.AU_KM), (196, 200, 210), f_dist)], "centre", ca)
        if t < plan.rew + 0.4:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            kit.hook(img, HOOK, t if t < hook_end + 0.1 else 99.0, t0=HOOK_T0, alpha=ha)
        if t >= plan.t75 - 0.05:
            u = cv.ease_out((t - plan.t75) / 0.5)
            kit.solid_text(img, W / 2, 1440 + 20 * (1 - u), [("75,000", GOLD), (" years", WHITE)], f_big,
                           alpha=u, shadow=0.85)
            label(img, W / 2, 1532, [(tracked("At Voyager's speed"), MUTED, f_small)], "centre",
                  smooth((t - plan.t75 - 0.2) / 0.4))
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, path, clips)

    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
