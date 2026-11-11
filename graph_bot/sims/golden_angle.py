"""Why do sunflowers turn every seed by 137.5°? The golden angle, grown live.

Seeds are placed one at a time: seed n turns n x (angle) around the centre and
sits at radius c·√(n + ½) (Vogel's model of a sunflower head, equal area per
seed). We try angles in turn (90°, 120°, 135°, 137°) and count the seeds jammed
against a neighbour; then 137.5° (the golden angle) packs all 800 with none
jammed, petals open, and the two spiral families light up: 34 one way, 55 the
other, both Fibonacci numbers.

Hook: the first frame is the finished sunflower with the question over it,
spoken. Then it rewinds into the centre and grows back up, one seed at a time.

Honest: every position comes from the formula, the jammed counts are computed
from the seeds on screen (nearest neighbour closer than 0.75 of the average
spacing), and the lit spirals join seeds 34 (or 55) apart that really are neighbours.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from . import canvas as cv
from . import kit
from . import sound as snd
from . import voice
from .canvas import CYAN, GOLD, MUTED, PINK, WHITE, W, mix, scale

FPS = 60
N = 800
CX, CY = 525, 842
R_D = 310                         # seed disc radius
C = R_D / math.sqrt(N + 0.5)
SEED_R = 8.4
SPACING = C * math.sqrt(math.pi)  # average distance between neighbours
JAM = 0.75 * SPACING
GOLDEN = 360 * (1 - 2 / (1 + math.sqrt(5)))   # 137.5077…°
TRIES = [90.0, 120.0, 135.0, 137.0, GOLDEN]
R_P0, P_LEN, P_WID, N_PET = R_D - 30, 150, 50, 34   # petals
BOX = (CX - 470, CY - 470, CX + 470, CY + 470)      # flower region (line-work, petals)
CREAM = (250, 238, 214)

LAB_Y, NUM_Y = 1300, 1374
HOOK_T0 = -0.3                    # the hook is already rising on frame one
Z0, Z_FRAME = 5.0, 300.0          # first-try camera: max zoom; outer seed kept ~300 px out
COL_L, COL_R = 300, 748
TAG_Y = 1468

HOOK = [[("Why", WHITE), ("do", WHITE), ("sunflowers", WHITE), ("turn", WHITE)],
        [("each", WHITE), ("seed", WHITE), ("137.5°?", GOLD)]]

# Voice-over: (spoken text, [(caption, words it covers)])
SCRIPT = {
    "hook": ("Why do sunflowers turn each seed by 137.5 degrees?", None),
    "rule": ("Each new seed turns by the same angle, a little further out.",
             [("Each new seed turns", 4), ("by the same angle", 4), ("a little further out", 4)]),
    "try": ("A quarter turn? Four lines. Every seed jammed.",
            [("A quarter turn?", 3), ("*Four lines*", 2), ("Every seed jammed", 3)]),
    "gold": ("But at 137.5, the golden angle, nothing lines up. Zero jammed.",
             [("But at 137.5°", 3), ("*the golden angle*", 3), ("nothing lines up", 3), ("Zero jammed", 2)]),
    "fib": ("Count the spirals. 34 one way, 55 the other. Fibonacci numbers.",
            [("Count the spirals", 3), ("34 one way", 3), ("55 the other", 3),
             ("*Fibonacci numbers*", 2)]),
}


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
IDX = np.arange(N)
RAD = C * np.sqrt(IDX + 0.5)
RHO = RAD / R_D


def positions(deg: float, rot: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    a = np.radians(IDX * deg + rot) - math.pi / 2
    return CX + RAD * np.cos(a), CY + RAD * np.sin(a)


def jam_index(deg: float) -> np.ndarray:
    """For each seed, the seed count at which it first has a too-close neighbour
    (N+1 if never). jammed(n) = count of seeds with jam_index < n."""
    x, y = positions(deg)
    pairs = cKDTree(np.c_[x, y]).query_pairs(JAM, output_type="ndarray")
    first = np.full(N, N + 1, np.int64)
    if len(pairs):
        i, j = pairs[:, 0], pairs[:, 1]
        k = np.maximum(i, j)               # the pair exists once both are placed
        np.minimum.at(first, i, k)
        np.minimum.at(first, j, k)
    return first


def jammed(first: np.ndarray, n: int) -> int:
    return int((first < n).sum())


def arms(F: int, deg: float = GOLDEN) -> list[list[tuple[float, float]]]:
    """Seeds F apart that really are neighbours, chained into F spiral arms
    (one list of points per arm, inner to outer)."""
    x, y = positions(deg)
    out = []
    for j in range(F):
        idx = np.arange(j, N, F)
        pts, run = [], []
        for a, b in zip(idx, idx[1:]):
            if math.hypot(x[b] - x[a], y[b] - y[a]) < 1.32 * SPACING:
                if not run:
                    run = [(x[a], y[a])]
                run.append((x[b], y[b]))
            elif len(run) > len(pts):
                pts, run = run, []
            else:
                run = []
        if len(run) > len(pts):
            pts = run
        if len(pts) >= 3:
            out.append(pts)
    # Light them in order around the flower (by the angle of the outer end).
    out.sort(key=lambda p: math.atan2(p[-1][1] - CY, p[-1][0] - CX))
    return out


# --------------------------------------------------------------------------- #
# Sprites
# --------------------------------------------------------------------------- #
_BRIGHT = [(228, 132, 46), (247, 174, 64), GOLD]
_FLOWER = [(96, 50, 22), (150, 84, 32), (214, 142, 54)]


def _ramp(stops, f: float):
    f = min(1.0, max(0.0, f)) * (len(stops) - 1)
    i = min(len(stops) - 2, int(f))
    return mix(stops[i], stops[i + 1], f - i)


def seed_color(rho: float, flower: float) -> tuple[int, int, int]:
    q = round(rho * 7) / 7
    fl = round(flower * 6) / 6
    return mix(_ramp(_BRIGHT, q), _ramp(_FLOWER, q), fl)


class SeedSprites:
    """Glossy seeds at any colour and radius (cached by 0.25 px and 1/4 px offset)."""

    def __init__(self, sub: int = 4):
        self.sub, self.cache = sub, {}

    def paste(self, img: Image.Image, col, x: float, y: float, r: float) -> None:
        if r < 0.6:
            return
        big = r > 12
        rq = round(r) if big else round(r * 4) / 4
        sub = 2 if big else self.sub
        fx, fy = math.floor(x), math.floor(y)
        ox, oy = int((x - fx) * sub), int((y - fy) * sub)
        key = (col, rq, ox, oy)
        spr = self.cache.get(key)
        if spr is None:
            size = int(math.ceil(rq * 2 + 4)) // 2 * 2 + 2
            spr = cv.sphere(col, rq, ox / sub, oy / sub, size, ss=4 if big else 8)
            self.cache[key] = spr
        img.paste(spr, (fx - spr.width // 2, fy - spr.height // 2), spr)


def _petal(length: int, width: int, shade: float) -> Image.Image:
    """One petal pointing up, base at the bottom centre (RGBA, supersampled)."""
    ss = 4
    Lw, Ww = length * ss, width * ss
    pad = 4 * ss
    img = Image.new("RGBA", (Ww + 2 * pad, Lw + 2 * pad), (0, 0, 0, 0))
    u = np.linspace(0, 1, 90)
    half = 0.5 * Ww * np.sin(np.pi * u) ** 0.7 * (1 - 0.18 * u)
    ys = pad + Lw * (1 - u)
    left = list(zip(pad + Ww / 2 - half, ys))
    right = list(zip(pad + Ww / 2 + half, ys))[::-1]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(left + right, fill=255)
    # Colour: deep orange at the base to warm yellow at the tip, a soft midrib,
    # darker towards the edges (gives the petal a curve).
    hh, ww = img.size[1], img.size[0]
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    along = np.clip(1 - (yy - pad) / Lw, 0, 1)[..., None]
    across = np.abs(xx - ww / 2) / (Ww / 2)
    base, mid, tip = (np.array(c, np.float32) for c in ((214, 104, 20), (250, 178, 38), (255, 214, 92)))
    col = np.where(along < 0.45, base + (mid - base) * (along / 0.45),
                   mid + (tip - mid) * ((along - 0.45) / 0.55))
    col = col * (1 - 0.22 * np.clip(across, 0, 1)[..., None] ** 2)
    rib = np.exp(-(across * 9) ** 2)[..., None] * (along > 0.06) * (along < 0.85)
    col = col * (1 - 0.12 * rib) * shade
    rgba = np.concatenate([np.clip(col, 0, 255), np.asarray(mask, np.float32)[..., None]], axis=-1)
    big = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    return big.resize((ww // ss, hh // ss), Image.LANCZOS)


class Petals:
    def __init__(self):
        self.front = _petal(P_LEN, P_WID, 1.0)
        self.back = _petal(P_LEN + 18, P_WID + 4, 0.72)
        self.cache = {}

    def _get(self, which: str, i: int, lv: int, rot: float):
        key = (which, i, lv, round(rot, 1))
        spr = self.cache.get(key)
        if spr is None:
            base = self.front if which == "f" else self.back
            f = lv / 10
            w = max(4, int(base.width * (0.55 + 0.45 * f)))
            h = max(4, int(base.height * (0.25 + 0.75 * f)))
            s = base.resize((w, h), Image.LANCZOS)
            ang = self.angle(which, i) + rot
            s = s.rotate(-ang, resample=Image.BICUBIC, expand=True)
            if f < 1:
                a = np.asarray(s, np.float32).copy()
                a[..., 3] *= min(1.0, f * 1.6)
                s = Image.fromarray(a.astype(np.uint8), "RGBA")
            if len(self.cache) > 6000:
                self.cache.clear()
            spr = self.cache[key] = (s, h)
        return spr

    @staticmethod
    def angle(which: str, i: int) -> float:
        return i * 360 / N_PET + (180 / N_PET if which == "b" else 0)

    def draw(self, img: Image.Image, prog, rot: float = 0.0) -> None:
        """prog(i) -> 0..1 bloom of petal i (both rings)."""
        for which in ("b", "f"):
            for i in range(N_PET):
                p = prog(i)
                if p <= 0.02:
                    continue
                lv = max(1, min(10, int(round(p * 10))))
                spr, h = self._get(which, i, lv, round(rot * 2) / 2)
                a = math.radians(self.angle(which, i) + rot) - math.pi / 2
                rc = R_P0 + h / 2 - 6
                cv.add_rgba(img, spr, CX + rc * math.cos(a), CY + rc * math.sin(a))


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
SOLO = np.cumsum([0.4, 0.5, 0.42, 0.36, 0.3, 0.26, 0.22, 0.19])


def grow_times(t0: float, dur: float, n: int = N, solo: bool = False) -> np.ndarray:
    """Arrival time of each seed: a few solo seeds first (first try), then an
    accelerating stream that fills the rest by t0 + dur."""
    if solo:
        k = len(SOLO)
        ts = t0 + SOLO
        u = np.linspace(0, 1, n - k + 1)[1:]
        rest = ts[-1] + (dur - SOLO[-1]) * (u ** 0.45)
        return np.concatenate([ts, rest])
    u = np.linspace(0, 1, n + 1)[1:]
    return t0 + dur * u ** 0.62


class Plan:
    """Every phase's start time, worked out from the voice lengths."""

    def __init__(self, lines: dict[str, voice.Line]):
        L = lines
        self.hook_at = 0.3
        self.rew = max(3.7, self.hook_at + L["hook"].secs + 0.3)   # rewind starts
        self.rew_end = self.rew + 0.75
        t = self.rew_end + 0.1
        self.tries = []                  # (deg, collapse_start, grow_start, grow_dur, hold_end)
        self.rule_at = t + 0.05
        g = (t, 5.4)                     # first try: solo seeds then the crowd
        self.try_at = max(t + 3.4, self.rule_at + L["rule"].secs + 0.2)
        hold = max(g[0] + g[1] + 0.7, self.try_at + L["try"].secs + 0.15)
        self.tries.append((TRIES[0], None, g[0], g[1], hold))
        t = hold
        for deg in TRIES[1:4]:
            c0 = t
            gs = c0 + 0.38
            gd = 0.95
            he = gs + gd + 0.6
            self.tries.append((deg, c0, gs, gd, he))
            t = he
        # 137°: hold a beat longer, so the near-miss count registers.
        last = list(self.tries[-1])
        last[4] += 0.35
        self.tries[-1] = tuple(last)
        t = last[4]
        gs = t + 0.38
        gd = 1.7
        self.tries.append((GOLDEN, t, gs, gd, 10_000))
        self.gold_done = gs + gd
        self.gold_at = self.gold_done - 0.25
        self.bloom = self.gold_done + 0.7
        self.fib_at = max(self.bloom + 1.5, self.gold_at + L["gold"].secs + 0.25)
        f = L["fib"]
        self.arm34 = self.fib_at + _word(f, "34", 0.38) - 0.05
        self.arm55 = self.fib_at + _word(f, "55", 0.6) - 0.05
        self.arm_dur = (1.15, 1.25)
        self.tag = self.fib_at + _word(f, "Both", 0.8)
        self.total = self.fib_at + f.secs + 1.9


def _word(line: voice.Line, w: str, frac: float) -> float:
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def whoosh(dur: float, f0: float, f1: float, seed: int = 5) -> np.ndarray:
    """An airy swoop: a cluster of detuned glides with a soft swell."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = np.zeros_like(t)
    for _ in range(14):
        k = rng.uniform(0.8, 1.25)
        f = f0 * (f1 / f0) ** u * k
        ph = 2 * np.pi * np.cumsum(f) / snd.SR + rng.uniform(0, 6.3)
        out += np.sin(ph) * rng.uniform(0.4, 1.0)
    env = np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6
    return (out / 14 * env).astype(np.float32)


def _soundtrack(plan: Plan, grow: list, total: float, path: Path, clips) -> None:
    mixer = snd.Mixer(total)
    rng = np.random.default_rng(42)
    pad = [snd.scale_freq(i) for i in (5, 7, 9, 12)]
    mixer.add(0.0, snd.chord(pad, dur=plan.rew + 0.6), 0.55)
    for j, n in enumerate([9, 12, 14, 17]):
        mixer.add(0.15 + j * 0.16, snd.pluck(snd.scale_freq(n), dur=1.2, bright=0.6), 0.35)
    mixer.add(plan.rew, whoosh(0.8, 1600, 220), 0.5)

    for k, (deg, c0, gs, gd, he) in enumerate(plan.tries):
        times = grow[k]
        golden = k == len(plan.tries) - 1
        if c0 is not None:
            mixer.add(c0 - 0.05, whoosh(0.5, 1200, 260, seed=k), 0.32)
        gap = np.gradient(times)
        rate = 1 / np.maximum(gap, 1e-4)
        keep = rng.random(N) < np.minimum(1.0, 34.0 / rate)
        keep[: len(SOLO)] = True
        idx = np.where(keep)[0]
        gains = snd.density_gains(times[idx], base=0.5, window=0.12, calm=1.4)
        x, _ = positions(deg)
        for i, g in zip(idx, gains):
            if i < len(SOLO) and k == 0:
                note = snd.pluck(snd.scale_freq(8 + i), dur=0.7, bright=0.9)
                g = 0.62
            else:
                note = snd.pluck(snd.scale_freq(8 + int(RHO[i] * 9)), dur=0.5,
                                 bright=0.9 if golden else 0.45)
            mixer.add(float(times[i]), note, float(g), float((x[i] - CX) / R_D * 0.7))
    # Golden: rising notes and a warm chord; petals chime as they open.
    for j, n in enumerate([5, 7, 9, 10, 12, 14]):
        mixer.add(plan.gold_done + j * 0.13, snd.pluck(snd.scale_freq(n), dur=1.4), 0.75)
    mixer.add(plan.gold_done + 0.75, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 10)],
                                               dur=total - plan.gold_done), 1.1)
    for i in range(N_PET):
        mixer.add(plan.bloom + 0.9 * i / N_PET, snd.pluck(snd.scale_freq(15 + (i % 5)), dur=0.5, bright=0.4),
                  0.12, math.sin(2 * math.pi * i / N_PET) * 0.6)
    for (start, dur, count, base) in ((plan.arm34, plan.arm_dur[0], 34, 10), (plan.arm55, plan.arm_dur[1], 55, 12)):
        for i in range(count):
            mixer.add(start + dur * i / count, snd.pluck(snd.scale_freq(base + int(6 * i / count)), dur=0.25,
                                                         bright=0.7), 0.16)
    voice.voice_over(mixer, list(clips), bed=0.65)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def zoom_for(n: float) -> float:
    """Camera zoom in the first try: close on the first seeds, out as they spread."""
    outer = C * math.sqrt(max(1.0, n) + 0.5) + SEED_R
    return min(Z0, max(1.0, Z_FRAME / outer))


def _hand(img: Image.Image, deg: float, n_new: int, u: float, z: float = 1.0, fade: float = 1.0) -> None:
    """The turning hand in the solo phase: a line to the newest seed and the
    angle it turned from the one before, with the angle written on the arc."""
    ss = 3
    x0, y0, x1, y1 = BOX
    big = Image.new("RGB", ((x1 - x0) * ss, (y1 - y0) * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    a_new = n_new * deg - 90
    a_old = (n_new - 1) * deg - 90
    cx, cy = (CX - x0) * ss, (CY - y0) * ss
    reach = min(440.0, RAD[n_new] * z + SEED_R * z + 40) * ss
    ar = math.radians(a_new)
    d.line([(cx, cy), (cx + reach * math.cos(ar), cy + reach * math.sin(ar))],
           fill=scale(CREAM, 0.8 * fade), width=3 * ss)
    if n_new >= 1:
        ao = math.radians(a_old)
        d.line([(cx, cy), (cx + reach * math.cos(ao), cy + reach * math.sin(ao))],
               fill=scale(MUTED, 0.45 * fade), width=3 * ss)
        r = 96 * ss
        sweep = (a_new - a_old) * cv.ease_out(u)
        start = a_old % 360
        d.arc((cx - r, cy - r, cx + r, cy + r), start, start + sweep, fill=scale(GOLD, fade), width=4 * ss)
    sharp = np.asarray(big.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    kit.add(img, BOX, kit.glow_of(sharp, 5, 0.6))
    if n_new >= 1:
        mid = math.radians(a_old + (a_new - a_old) / 2)
        kit.text_parts(img, CX + 150 * math.cos(mid), CY + 150 * math.sin(mid),
                       [(f"{deg:g}°", scale(GOLD, fade))], kit.sans(42, "black"), glow=0.3)


def _arms_layer(lit: list[tuple[list, float]], color) -> np.ndarray:
    ss = 3
    x0, y0, x1, y1 = BOX
    big = Image.new("RGB", ((x1 - x0) * ss, (y1 - y0) * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    for pts, p in lit:
        if p <= 0:
            continue
        m = (len(pts) - 1) * min(1.0, p)
        k = int(m)
        q = [((x - x0) * ss, (y - y0) * ss) for x, y in pts[: k + 1]]
        if k < len(pts) - 1:
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            f = m - k
            q.append(((ax + (bx - ax) * f - x0) * ss, (ay + (by - ay) * f - y0) * ss))
        if len(q) > 1:
            d.line(q, fill=color, width=int(2.7 * ss), joint="curve")
    sharp = np.asarray(big.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    return kit.glow_of(sharp, 6, 0.9)


def _column(img, x, label, value, vcol, a, size=86):
    if a <= 0:
        return
    kit.text_parts(img, x, LAB_Y, [(label, scale(mix(MUTED, WHITE, 0.3), a))], kit.sans(27, "bold"))
    kit.text_parts(img, x, NUM_Y, [(value, scale(vcol, a))], kit.sans(size, "black"), glow=0.35 * a)


def _tracked(s: str) -> str:
    return " ".join(s)          # small caps label with letter spacing


def build(ffmpeg: str):
    """Everything needed to draw any frame: (total seconds, frame(t) -> Image, sound(path))."""
    jam_first = {deg: jam_index(deg) for deg in TRIES}
    script = SCRIPT
    lines = kit.spoken(script, ffmpeg)
    plan = Plan(lines)
    total = plan.total
    clips = [(plan.hook_at, lines["hook"]), (plan.rule_at, lines["rule"]), (plan.try_at, lines["try"]),
             (plan.gold_at, lines["gold"]), (plan.fib_at, lines["fib"])]
    caps = []
    for (at, line), key in zip(clips[1:], ["rule", "try", "gold", "fib"]):
        caps += kit.captions(at, line, script[key][1])

    grow = [grow_times(gs, gd, solo=(k == 0)) for k, (_, _, gs, gd, _) in enumerate(plan.tries)]
    pos = {deg: positions(deg) for deg in TRIES}
    a34, a55 = arms(34), arms(55)

    bg = kit.backdrop(CX, CY)
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)
    with_hook = bg.copy()
    kit.hook(with_hook, HOOK, 99.0)
    seeds = SeedSprites()
    petals = Petals()
    n_frames = int(total * FPS)
    lab_turn, lab_jam = _tracked("TURN PER SEED"), _tracked("SEEDS JAMMED")

    def petal_prog(t: float, rew: bool):
        if t < plan.rew:
            return lambda i: 1.0
        if rew:
            f = 1 - cv.ease((t - plan.rew) / 0.32)
            return lambda i: f
        def p(i):
            return cv.ease_out((t - plan.bloom - 0.85 * (i / N_PET)) / 0.6)
        return p

    def frame(t: float) -> Image.Image:
            img = with_hook.copy() if t > hook_end + 0.05 else bg.copy()
            if t <= hook_end + 0.05:
                kit.hook(img, HOOK, t, t0=HOOK_T0)

            # ---------------- cold open + rewind: the finished sunflower ----------------
            if t < plan.rew_end:
                rot = 5.0 * t
                if t < plan.rew + 0.33:
                    petals.draw(img, petal_prog(t, t >= plan.rew), rot)
                x, y = positions(GOLDEN, rot)
                flower = 1.0
                if t < plan.rew + 0.2:
                    n_vis, shrink_from = N, None
                else:
                    u = cv.ease((t - plan.rew - 0.2) / 0.55)
                    n_vis = int(round(N * (1 - u)))
                breathe = 1 + 0.012 * math.sin(t * 2.2)
                for i in range(n_vis):
                    r = SEED_R * breathe
                    if t >= plan.rew + 0.2 and i > n_vis - 40:
                        r *= max(0.0, (n_vis - i) / 40)
                    seeds.paste(img, seed_color(RHO[i], flower), x[i], y[i], r)
            else:
                # ---------------- the tries ----------------
                k = max(j for j, tr in enumerate(plan.tries) if (tr[1] if tr[1] is not None else tr[2]) <= t
                        ) if t >= plan.tries[0][2] else 0
                deg, c0, gs, gd, he = plan.tries[k]
                times = grow[k]
                x, y = pos[deg]
                golden = k == len(plan.tries) - 1
                flower = cv.ease((t - plan.bloom) / 1.4) if golden else 0.0
                if golden and t >= plan.bloom:
                    petals.draw(img, petal_prog(t, False), 0.0)
                if c0 is not None and t < gs:
                    # collapse the previous try back into the centre
                    pd = plan.tries[k - 1][0]
                    px, py = pos[pd]
                    u = cv.ease((t - c0) / 0.34)
                    n_vis = int(round(N * (1 - u)))
                    for i in range(n_vis):
                        r = SEED_R * (max(0.0, (n_vis - i) / 30) if i > n_vis - 30 else 1.0)
                        seeds.paste(img, seed_color(RHO[i], 0), px[i], py[i], r)
                    n = 0
                else:
                    n = int(np.searchsorted(times, t, side="right"))
                    z = 1.0
                    if k == 0 and n:
                        n_f = float(np.interp(t, times, np.arange(1, N + 1)))
                        z = zoom_for(n_f)
                    for i in range(n):
                        age = t - times[i]
                        pop = 1 + 0.45 * math.exp(-age * 14) * min(1.0, age * 40) if age < 0.4 else 1.0
                        r = SEED_R * pop
                        g = 1.0
                        if k == 0 and i < len(SOLO):
                            g = cv.ease_out(age / 0.32)          # glide out from the centre
                            r = SEED_R * (0.5 + 0.5 * g) * pop
                        sx, sy = CX + (x[i] - CX) * g * z, CY + (y[i] - CY) * g * z
                        seeds.paste(img, seed_color(RHO[i], flower), sx, sy, r * z)
                    if k == 0 and n:
                        nn = min(n, len(SOLO)) - 1
                        fade = 1.0 if n <= len(SOLO) else max(0.0, 1 - (t - times[len(SOLO)]) / 0.5)
                        if fade > 0:
                            _hand(img, deg, nn, (t - times[nn]) / 0.32, z, fade)

                # ---------------- read-outs ----------------
                a_ro = cv.ease((t - plan.tries[0][2] - 0.2) / 0.5) * (1 - cv.ease((t - plan.fib_at + 0.1) / 0.4))
                if a_ro > 0:
                    collapsing = c0 is not None and t < gs
                    sd = plan.tries[k - 1][0] if collapsing else deg   # rewinding: keep the last try's numbers
                    shown_deg = "137.5°" if golden and not collapsing else f"{sd:g}°"
                    jam = jammed(jam_first[sd], N if collapsing else n) if (n or collapsing) else 0
                    golden = golden and not collapsing
                    jcol = GOLD if golden else (PINK if jam else WHITE)
                    _column(img, COL_L, lab_turn, shown_deg, mix(WHITE, GOLD, 1.0 if golden else 0.35), a_ro)
                    _column(img, COL_R, lab_jam, f"{jam:,}", jcol, a_ro)

                # ---------------- spirals ----------------
                if golden and t >= plan.arm34:
                    for arm_set, start, dur, col in ((a34, plan.arm34, plan.arm_dur[0], CREAM),
                                                     (a55, plan.arm55, plan.arm_dur[1], CYAN)):
                        if t < start:
                            continue
                        m = len(arm_set)
                        lit = [(pts, (t - start - dur * j / m) / 0.35) for j, pts in enumerate(arm_set)]
                        # One family at a time reads as spirals; both at full strength is a mesh.
                        settle = plan.arm55 + plan.arm_dur[1] + 0.9
                        if arm_set is a34:
                            lv = 1 - 0.68 * cv.ease((t - plan.arm55 + 0.1) / 0.4)
                        else:
                            lv = 1 - 0.45 * cv.ease((t - settle) / 0.8)
                        kit.add(img, BOX, _arms_layer(lit, scale(col, 0.92)) * lv)
                    a_f = cv.ease((t - plan.arm34 + 0.15) / 0.3)
                    c34 = min(34, int((t - plan.arm34) / plan.arm_dur[0] * 34) + 1)
                    _column(img, COL_L, _tracked("SPIRALS ONE WAY"), f"{c34}", CREAM, a_f, size=96)
                    if t >= plan.arm55 - 0.15:
                        a_g = cv.ease((t - plan.arm55 + 0.15) / 0.3)
                        c55 = min(55, max(1, int((t - plan.arm55) / plan.arm_dur[1] * 55) + 1))
                        _column(img, COL_R, _tracked("THE OTHER WAY"), f"{c55}", CYAN, a_g, size=96)
                    a_t = cv.ease((t - plan.tag) / 0.5)
                    if a_t > 0:
                        kit.text_parts(img, W / 2, TAG_Y, [("Both ", scale(WHITE, a_t)),
                                                           ("Fibonacci numbers", scale(GOLD, a_t))],
                                       kit.serif(46, italic=True), glow=0.3 * a_t)

            kit.draw_captions(img, caps, t)
            return img

    def sound(path: Path) -> None:
        _soundtrack(plan, grow, total, path, clips)

    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={})
