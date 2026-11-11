"""Every dot is random. So why this shape? The chaos game, live.

Three corners. From any point, pick a corner at random, jump halfway to it and
leave a dot. Repeat. After 150,000 jumps the dots have drawn a Sierpinski
triangle: halfway to a corner always lands inside that corner's half-size
triangle, so the middle can never be hit, and the same holds inside every
smaller triangle.

Each dot takes the colour of the corner it just jumped towards, so the three
half-size copies glow gold, pink and cyan. The payoff zooms 4x into a corner and
the same picture comes back.

The zoom is honest too: a point halfway between a real dot's previous position
and any corner is exactly where the chaos game could have put it, so the zoom
adds those (never invents structure), and keeps the screen's dot density steady.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import canvas as cv
from . import kit
from . import sound as snd
from . import voice
from .canvas import CYAN, GOLD, MUTED, PINK, WHITE, W, mix, scale

FPS = 60
N = 150_000
SIDE = 780
CX = 525
APEX_Y = 478
HGT = SIDE * math.sqrt(3) / 2
CORNERS = np.array([(CX, APEX_Y), (CX - SIDE / 2, APEX_Y + HGT), (CX + SIDE / 2, APEX_Y + HGT)])
COLS = [GOLD, PINK, CYAN]
B = 1                              # zoom into the bottom-left (pink) corner
M = 20
BOX = (int(CX - SIDE / 2 - M), int(APEX_Y - M), int(CX + SIDE / 2 + M), int(APEX_Y + HGT + M))
BW, BH = BOX[2] - BOX[0], BOX[3] - BOX[1]
BW -= BW % 4
BH -= BH % 4
BOX = (BOX[0], BOX[1], BOX[0] + BW, BOX[1] + BH)

S_BIG, S_MIN, S_EXP = 10.0, 1.25, 0.2
N_FINE = int(math.ceil((S_BIG / S_MIN) ** (1 / S_EXP)))
POP = 0.35
LAB_Y, NUM_Y = 1252, 1324
HOOK_T0 = -0.3

HOOK = [[("Every", WHITE), ("dot", WHITE), ("is", WHITE), ("random.", GOLD)],
        [("So", WHITE), ("why", WHITE), ("this", WHITE), ("shape?", WHITE)]]

SCRIPT = {
    "hook": ("Every dot here landed at random. So why does it make this?", None),
    "rule": ("Pick a random corner. Jump halfway there. Leave a dot. Repeat.",
             [("Pick a random corner", 4), ("Jump *halfway* there", 3), ("Leave a dot", 3), ("Repeat", 1)]),
    "mess": ("That should make a random mess, right?",
             [("That should make", 3), ("a random mess, right?", 4)]),
    "why": ("No. Halfway to a corner always lands in that corner's smaller triangle. "
            "So the middle stays empty, at every size.",
            [("No.", 1), ("Halfway to a corner", 4), ("always lands in", 3), ("that corner's smaller triangle", 4),
             ("So the *middle stays empty*", 5), ("at every size", 3)]),
    "end": ("The Sierpinski triangle. Zoom in, and it never ends.",
            [("The *Sierpinski triangle*", 3), ("Zoom in", 2), ("and it never ends", 4)]),
}


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def simulate(seed: int, n: int = N) -> dict:
    rng = np.random.default_rng(seed)
    h = rng.integers(0, 3, n)
    # A random start inside the triangle.
    a, b = rng.random(2)
    if a + b > 1:
        a, b = 1 - a, 1 - b
    start = CORNERS[0] + a * (CORNERS[1] - CORNERS[0]) + b * (CORNERS[2] - CORNERS[0])
    p = np.empty((n, 2))
    cur = start.copy()
    for i in range(n):
        cur = (cur + CORNERS[h[i]]) / 2
        p[i] = cur
    prev = np.vstack([start[None], p[:-1]])
    return dict(p=p, h=h, start=start, prev=prev)


FIRST = np.cumsum([0.55, .72, .62, .54, .47, .41, .36, .32, .28, .25, .22, .2])
N_SOLO = 6                          # jumps shown with the travelling marble


def arrival_times(t0: float, t_end: float, n: int = N) -> np.ndarray:
    n0 = len(FIRST)
    first = t0 + FIRST
    ts = float(first[-1])
    L = math.log(n / n0)
    a = 0.6
    u = np.linspace(0, 1, 400_001)
    g = a * (2 * u - u * u) + (1 - a) * (3 * u * u - 2 * u ** 3)
    nt = n0 * np.exp(L * g)
    rest = ts + (t_end - ts) * np.interp(np.arange(n0 + 1, n + 1), nt, u)
    return np.concatenate([first, rest])


def dot_size(n: float) -> float:
    return max(S_MIN, S_BIG * max(1.0, n) ** -S_EXP)


# --------------------------------------------------------------------------- #
# Dots: antialiased glossy splats into one density layer per corner colour
# --------------------------------------------------------------------------- #
def splat(layers: np.ndarray, xs, ys, cid, s, wt=None) -> None:
    """layers: (3, BH, BW). Adds glossy round dots (radius s) for each point."""
    if len(xs) == 0:
        return
    s = np.broadcast_to(np.asarray(s, np.float64), xs.shape)
    k = int(math.ceil(s.max() + 1.5))
    offs = np.arange(-k, k + 1)
    lx, ly = xs - BOX[0], ys - BOX[1]
    gx = np.floor(lx).astype(np.int64)[:, None] + offs
    gy = np.floor(ly).astype(np.int64)[:, None] + offs
    dx = (gx + 0.5 - lx[:, None])[:, None, :]
    dy = (gy + 0.5 - ly[:, None])[:, :, None]
    ss = s[:, None, None]
    d2 = dx * dx + dy * dy
    cover = np.clip(ss + 0.5 - np.sqrt(d2), 0, 1)
    shade = 0.75 + 0.25 * np.clip(1 - d2 / (ss * ss), 0, 1)
    gloss = 0.9 * np.exp(-((dx + 0.35 * ss) ** 2 + (dy + 0.4 * ss) ** 2) / (0.32 * ss) ** 2)
    sparkle = (0.72 + 0.28 * ((xs * 7.31 + ys * 3.17) % 1.0))[:, None, None]
    w = cover * (shade + gloss) * sparkle
    if wt is not None:
        w = w * np.asarray(wt)[:, None, None]
    ok = (gx >= 0)[:, None, :] & (gx < BW)[:, None, :] & (gy >= 0)[:, :, None] & (gy < BH)[:, :, None]
    idx = np.clip(gy, 0, BH - 1)[:, :, None] * BW + np.clip(gx, 0, BW - 1)[:, None, :]
    w = np.where(ok, w, 0)
    for c in range(3):
        sel = cid == c
        if sel.any():
            layers[c].ravel()[:] += np.bincount(idx[sel].ravel(), w[sel].ravel(),
                                                minlength=BW * BH).astype(np.float32)


_KN = [0.0, 0.2, 0.45, 0.7, 1.0]
RAMPS = [np.array(r, np.float32) for r in (
    [(0, 0, 0), (110, 42, 8), (232, 140, 40), GOLD, (255, 218, 120)],
    [(0, 0, 0), (96, 14, 44), (214, 56, 110), PINK, (255, 168, 196)],
    [(0, 0, 0), (8, 34, 84), (28, 112, 196), CYAN, (150, 226, 255)],
)]


def _ramp(v, r):
    return np.stack([np.interp(v, _KN, r[:, c]) for c in range(3)], axis=-1)


def _fill(e):
    small = e.reshape(BH // 4, 4, BW // 4, 4).mean(axis=(1, 3))
    im = Image.fromarray(np.clip(small * 60, 0, 255).astype(np.uint8))
    up = im.filter(ImageFilter.GaussianBlur(2.0)).resize((BW, BH), Image.BILINEAR)
    return np.asarray(up, np.float32) / 60


def to_rgb(layers: np.ndarray, gain: float = 1.0, fade: float = 1.0) -> np.ndarray:
    out = np.zeros((BH, BW, 3), np.float32)
    for c in range(3):
        e = layers[c] * gain
        if not e.any():
            continue
        v = 1 - np.exp(-1.6 * e)
        f = 1 - np.exp(-0.55 * _fill(e))
        out += _ramp(1 - (1 - v) * (1 - 0.6 * f), RAMPS[c])
    return out * fade


def knee(reg, knee=178.0):
    m = reg.max(axis=-1, keepdims=True)
    top = 255 - knee
    f = np.where(m > knee, (knee + top * (1 - np.exp(-(m - knee) / top))) / np.maximum(m, 1e-3), 1.0)
    return np.clip(reg * f, 0, 255)


# --------------------------------------------------------------------------- #
# Self-similar zoom into corner B
# --------------------------------------------------------------------------- #
class Zoom:
    """Dots for a zoom of z = 2^(L + w) into corner B (L = 0 or 1, w in [0, 1)).

    Level L shows f_B^L(halfway from an earlier position to each corner): at
    w = 0 only the real dots (density as at the end of the run), more of the
    other two halfway points as w grows, so density stays steady. Colours fade
    from the corner of this level's jump to the corner one jump earlier, so the
    picture looks the same at every doubling."""

    def __init__(self, sim: dict, seed: int = 9):
        p, h = sim["p"], sim["h"]
        self.idx = np.arange(2, len(p))
        rng = np.random.default_rng(seed)
        self.levels = []
        for L in (0, 1):
            base = sim["prev"][self.idx] if L == 0 else sim["prev"][self.idx - 1]
            real = h[self.idx] if L == 0 else h[self.idx - 1]
            inner = h[self.idx - 1] if L == 0 else h[self.idx - 2]
            pts, coarse, fine, isreal, order = [], [], [], [], []
            for x in range(3):
                q = (base + CORNERS[x]) / 2
                for _ in range(L):
                    q = (q + CORNERS[B]) / 2
                pts.append(q)
                coarse.append(np.full(len(q), x))
                fine.append(inner)
                isreal.append(real == x)
                order.append(self.idx)
            self.levels.append(dict(p=np.vstack(pts), coarse=np.concatenate(coarse),
                                    fine=np.concatenate(fine), real=np.concatenate(isreal),
                                    order=np.concatenate(order), u=rng.random(3 * len(self.idx))))

    def draw(self, layers: np.ndarray, z: float, n_vis: int | None = None, fade: float = 1.0) -> None:
        lz = math.log2(max(1.0, z))
        L = min(1, int(lz))
        w = min(1.0, lz - L)
        lv = self.levels[L]
        keep = lv["real"] | (lv["u"] < (3 ** w - 1) / 2)
        if n_vis is not None:
            keep &= lv["order"] < n_vis
        q = lv["p"][keep]
        sx = CORNERS[B][0] + (q[:, 0] - CORNERS[B][0]) * z
        sy = CORNERS[B][1] + (q[:, 1] - CORNERS[B][1]) * z
        inside = (sx > BOX[0] - 3) & (sx < BOX[2] + 3) & (sy > BOX[1] - 3) & (sy < BOX[3] + 3)
        sx, sy = sx[inside], sy[inside]
        co, fi = lv["coarse"][keep][inside], lv["fine"][keep][inside]
        if w < 0.02:
            splat(layers, sx, sy, co, S_MIN, np.full(len(sx), fade))
        elif w > 0.98:
            splat(layers, sx, sy, fi, S_MIN, np.full(len(sx), fade))
        else:
            both_x, both_y = np.concatenate([sx, sx]), np.concatenate([sy, sy])
            wt = np.concatenate([np.full(len(sx), 1 - w), np.full(len(sx), w)]) * fade
            splat(layers, both_x, both_y, np.concatenate([co, fi]), S_MIN, wt)


def tri_mask() -> np.ndarray:
    """The big triangle as a soft mask over BOX (zoomed dots stay inside it)."""
    ss = 3
    im = Image.new("L", (BW * ss, BH * ss), 0)
    pts = [((x - BOX[0]) * ss, (y - BOX[1]) * ss) for x, y in CORNERS]
    ImageDraw.Draw(im).polygon(pts, fill=255)
    m = im.resize((BW, BH), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
    return np.asarray(m, np.float32)[..., None] / 255


# --------------------------------------------------------------------------- #
# Line-work: outline, the halfway guide, the 'why' overlay
# --------------------------------------------------------------------------- #
def _lines(draw_fn) -> np.ndarray:
    ss = 3
    big = Image.new("RGB", (BW * ss, BH * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)

    def P(x, y):
        return ((x - BOX[0]) * ss, (y - BOX[1]) * ss)
    draw_fn(d, P, ss)
    sharp = np.asarray(big.resize((BW, BH), Image.LANCZOS), np.float32)
    return kit.glow_of(sharp, 5, 0.7)


def _dashed(d, a, b, col, w, dash=12, gap=10):
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return
    ux, uy = (bx - ax) / L, (by - ay) / L
    s = 0.0
    while s < L:
        e = min(L, s + dash)
        d.line([(ax + ux * s, ay + uy * s), (ax + ux * e, ay + uy * e)], fill=col, width=w)
        s += dash + gap


def outline(prog: float, alpha: float) -> np.ndarray:
    def f(d, P, ss):
        pts = [CORNERS[0], CORNERS[1], CORNERS[2], CORNERS[0]]
        left = prog * 3
        for a, b in zip(pts, pts[1:]):
            if left <= 0:
                break
            g = min(1.0, left)
            e = a + (b - a) * g
            d.line([P(*a), P(*e)], fill=scale(mix(MUTED, WHITE, 0.2), alpha), width=2 * ss)
            left -= 1
    return _lines(f)


def why_overlay(p_half: float, p_mid: float, p_deep: float) -> np.ndarray:
    """The three half-size triangles in their colours, then the empty middle
    (dashed white), then the same middles one size down."""
    A, Bc, C = CORNERS
    mids = [(A + Bc) / 2, (Bc + C) / 2, (C + A) / 2]       # AB, BC, CA

    def tri(d, P, pts, col, w, dashed=False):
        q = [P(*p) for p in pts] + [P(*pts[0])]
        for a, b in zip(q, q[1:]):
            if dashed:
                _dashed(d, a, b, col, w, dash=14 * 3, gap=10 * 3)
            else:
                d.line([a, b], fill=col, width=w)

    def f(d, P, ss):
        if p_half > 0:
            subs = [(A, mids[0], mids[2]), (mids[0], Bc, mids[1]), (mids[2], mids[1], C)]
            for c, s in enumerate(subs):
                tri(d, P, s, scale(COLS[c], p_half), 3 * ss)
        if p_mid > 0:
            tri(d, P, mids, scale(WHITE, p_mid), 4 * ss, dashed=True)
        if p_deep > 0:
            for c, (a, b, cc) in enumerate([(A, mids[0], mids[2]), (mids[0], Bc, mids[1]), (mids[2], mids[1], C)]):
                tri(d, P, [(a + b) / 2, (b + cc) / 2, (cc + a) / 2], scale(WHITE, p_deep * 0.8), 2 * ss, dashed=True)
    return _lines(f)


def mid_shade(alpha: float) -> np.ndarray:
    """A faint white wash over the empty middle triangle while it's named."""
    A, Bc, C = CORNERS
    mids = [(A + Bc) / 2, (Bc + C) / 2, (C + A) / 2]
    im = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(im).polygon([(x - BOX[0], y - BOX[1]) for x, y in mids], fill=255)
    m = np.asarray(im.filter(ImageFilter.GaussianBlur(3)), np.float32)[..., None] / 255
    return m * np.array([255, 255, 255], np.float32) * 0.035 * alpha


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
class Plan:
    def __init__(self, L: dict[str, voice.Line]):
        self.hook_at = 0.3
        self.rew = max(3.9, self.hook_at + L["hook"].secs + 0.35)
        self.rew_end = self.rew + 0.7
        self.setup = self.rew_end + 0.05            # corners pop in, outline draws
        self.t0 = self.setup + 0.45                 # first jump time base
        self.rule_at = self.t0 + 0.15
        self.mess_at = max(self.t0 + FIRST[-1] + 0.9, self.rule_at + L["rule"].secs + 0.35)
        self.why_at = self.mess_at + L["mess"].secs + 0.35
        w = L["why"]
        self.half_at = self.why_at + _word(w, "Halfway", 0.1)
        self.mid_at = self.why_at + _word(w, "middle", 0.65)
        self.deep_at = self.why_at + _word(w, "every", 0.85)
        self.t_end = self.why_at + w.secs + 0.2     # all dots in
        self.pay = self.t_end + 0.35
        self.end_at = self.pay + 0.1
        self.zoom0 = self.end_at + _word(L["end"], "Zoom", 0.45) - 0.1
        self.zoom1 = self.zoom0 + 4.2
        self.total = max(self.zoom1 + 1.4, self.end_at + L["end"].secs + 1.6)


def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


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


def _soundtrack(plan: Plan, sim, times, total, path, clips):
    mixer = snd.Mixer(total)
    rng = np.random.default_rng(77)
    mixer.add(0.0, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 12)], dur=plan.rew + 0.6), 0.5)
    for j, n in enumerate([10, 12, 14, 17]):
        mixer.add(0.12 + j * 0.17, snd.pluck(snd.scale_freq(n), dur=1.2, bright=0.6), 0.32)
    mixer.add(plan.rew, whoosh(0.8, 1600, 220), 0.5)
    for c in range(3):
        mixer.add(plan.setup + 0.12 * c, snd.pluck(snd.scale_freq((12, 9, 7)[c]), dur=0.9), 0.5,
                  float((CORNERS[c][0] - CX) / SIDE))
    corner_note = {0: 12, 1: 9, 2: 7}
    gap = np.gradient(times)
    rate = 1 / np.maximum(gap, 1e-5)
    keep = rng.random(len(times)) < np.minimum(1.0, 45.0 / rate)
    keep[: len(FIRST)] = True
    idx = np.where(keep)[0]
    gains = snd.density_gains(times[idx], base=0.5, window=0.1, calm=1.5)
    h, p = sim["h"], sim["p"]
    notes = {(c, o): snd.pluck(snd.scale_freq(corner_note[c] + o), dur=0.5, bright=0.8)
             for c in range(3) for o in (0, 5)}
    for i, g in zip(idx, gains):
        c = int(h[i])
        o = 5 if (i % 7 == 3) else 0               # a little melody in the stream
        gg = 0.6 if i < len(FIRST) else float(g)
        mixer.add(float(times[i]), notes[(c, o)], gg, float((p[i][0] - CX) / SIDE * 1.2))
    for at, n in ((plan.half_at, 14), (plan.mid_at, 17), (plan.deep_at, 19)):
        mixer.add(at, snd.pluck(snd.scale_freq(n), dur=1.0, bright=0.5), 0.35)
    for j, n in enumerate([5, 7, 9, 10, 12, 14]):
        mixer.add(plan.pay + j * 0.14, snd.pluck(snd.scale_freq(n), dur=1.4), 0.75)
    mixer.add(plan.pay + 0.8, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 10)], dur=total - plan.pay), 1.1)
    mixer.add(plan.zoom0, whoosh(plan.zoom1 - plan.zoom0, 180, 900, seed=3), 0.28)
    voice.voice_over(mixer, list(clips), bed=0.6)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 5):
    sim = simulate(seed)
    lines = kit.spoken(SCRIPT, ffmpeg)
    plan = Plan(lines)
    times = arrival_times(plan.t0, plan.t_end)
    total = plan.total
    clips = [(plan.hook_at, lines["hook"]), (plan.rule_at, lines["rule"]), (plan.mess_at, lines["mess"]),
             (plan.why_at, lines["why"]), (plan.end_at, lines["end"])]
    caps = []
    for (at, line), key in zip(clips[1:], ["rule", "mess", "why", "end"]):
        caps += kit.captions(at, line, SCRIPT[key][1])

    zoom = Zoom(sim)
    mask = tri_mask()
    bg = kit.backdrop(CX, APEX_Y + HGT * 0.6)
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)
    with_hook = bg.copy()
    kit.hook(with_hook, HOOK, 99.0)
    corner_spr = cv.Sprites(COLS, 15)
    jumper = cv.Sprites([WHITE], 11)
    halos = {c: kit.ring(30, COLS[c], 1.0, 3.0) for c in range(3)}
    full_outline = outline(1.0, 1.0)
    p, h = sim["p"], sim["h"]
    persist = {"layers": np.zeros((3, BH, BW), np.float32), "baked": 0}
    lab_f, num_f = kit.sans(27, "bold"), kit.sans(84, "black")
    jumps_lab = " ".join("JUMPS")

    def put_dots(img, layers, gain=1.0, fade=1.0, clip=True):
        rgb = to_rgb(layers, gain, fade)
        if clip:
            rgb = rgb * mask
        reg = np.asarray(img.crop(BOX), np.float32) + rgb
        img.paste(Image.fromarray(knee(reg).astype(np.uint8)), BOX[:2])

    def cold_zoom(t):
        return 1 + 1.15 * cv.ease(t / plan.rew) if t < plan.rew else 2.15

    def frame(t: float) -> Image.Image:
        img = with_hook.copy() if t > hook_end + 0.05 else bg.copy()
        if t <= hook_end + 0.05:
            kit.hook(img, HOOK, t, t0=HOOK_T0)

        if t < plan.rew_end:
            # ---- cold open: the finished triangle, slowly zooming into a corner ----
            layers = np.zeros((3, BH, BW), np.float32)
            if t < plan.rew:
                zoom.draw(layers, cold_zoom(t))
            else:
                u = cv.ease((t - plan.rew) / 0.65)
                z = 2.15 + (1 - 2.15) * cv.ease((t - plan.rew) / 0.4)
                zoom.draw(layers, z, n_vis=int(N * (1 - u) ** 2), fade=1 - 0.4 * u)
            put_dots(img, layers)
        else:
            # ---- corners and outline ----
            a_set = cv.ease((t - plan.setup) / 0.4)
            kit.add(img, BOX, outline(min(1.0, (t - plan.setup) / 0.5), 0.9) if t < plan.setup + 0.5
                    else full_outline * 0.9)
            n = int(np.searchsorted(times, t, side="right"))
            # ---- dots ----
            if n < N_FINE:
                layers = np.zeros((3, BH, BW), np.float32)
                if n:
                    age = (t - times[:n]) / POP
                    pop = np.where(age < 1, 1 + 0.9 * (1 - np.clip(age, 0, 1)) ** 3, 1.0)
                    splat(layers, p[:n, 0], p[:n, 1], h[:n], dot_size(n) * pop)
            elif t < plan.zoom0:
                layers = persist["layers"]
                if persist["baked"] == 0 or persist["baked"] > n:
                    layers[:] = 0
                    persist["baked"] = 0
                b0 = persist["baked"]
                splat(layers, p[b0:n, 0], p[b0:n, 1], h[b0:n], S_MIN)
                persist["baked"] = n
            else:
                layers = np.zeros((3, BH, BW), np.float32)
                zt = (t - plan.zoom0) / (plan.zoom1 - plan.zoom0)
                zoom.draw(layers, 2 ** (2 * cv.ease(zt)) * 0.99999 + 1e-5)
            pulse = kit.flash(t, plan.pay + 0.7, 0.5) + 0.15 * cv.ease((t - plan.pay) / 1.5)
            put_dots(img, layers, gain=1 + 0.3 * pulse, clip=t >= plan.zoom0)

            # ---- the travelling marble for the first jumps ----
            if n <= len(FIRST) + 1:
                k = min(n, len(FIRST) - 1)                 # jump in progress (or just landed)
                if k < N_SOLO + 4:
                    t_land = times[k]
                    glide = min(0.34, 0.75 * (FIRST[k] - (FIRST[k - 1] if k else 0)))
                    u = cv.ease((t - (t_land - glide)) / glide)
                    a = p[k - 1] if k else sim["start"]
                    if t < t_land - glide and k:
                        a = p[k - 1]
                        u = 0.0
                    c = int(h[k])
                    fade_m = 1 - cv.ease((t - times[N_SOLO + 3]) / 0.4)
                    if fade_m > 0:
                        guide = _lines(lambda d, P, ss: _dashed(d, P(*a), P(*CORNERS[c]),
                                                                scale(COLS[c], 0.75 * fade_m), 2 * ss,
                                                                dash=10 * ss, gap=9 * ss))
                        kit.add(img, BOX, guide)
                        pos = a + (p[k] - a) * u if t < t_land else p[k]
                        if t < t_land:
                            jumper.paste(img, WHITE, float(pos[0]), float(pos[1]))
                        kit.text_parts(img, (a[0] + CORNERS[c][0]) / 2 + 22, (a[1] + CORNERS[c][1]) / 2 - 22,
                                       [("½", scale(WHITE, 0.9 * fade_m))], kit.sans(34, "bold"), glow=0.3)
            for c in range(3):
                if a_set <= 0:
                    break
                x, y = CORNERS[c]
                corner_spr.paste(img, COLS[c], float(x), float(y))
                # a ring flashes on the chosen corner during the solo jumps
                k = min(n, len(FIRST) - 1)
                if n <= N_SOLO + 4 and t < times[N_SOLO + 3] + 0.3 and int(h[k]) == c:
                    t_land = times[k]
                    fl = kit.flash(t, t_land - 0.3, 0.22)
                    if fl > 0.05:
                        cv.add_rgba(img, halos[c] if fl > 0.5 else kit.ring(30 + 10 * (1 - fl), COLS[c], fl, 3.0),
                                    float(x), float(y))

            # ---- the 'why' overlay ----
            if plan.half_at - 0.1 < t < plan.pay + 0.6:
                end = 1 - cv.ease((t - plan.pay) / 0.5)
                ph = cv.ease((t - plan.half_at) / 0.5) * end
                pm = cv.ease((t - plan.mid_at) / 0.5) * end
                pd = cv.ease((t - plan.deep_at) / 0.6) * end
                kit.add(img, BOX, why_overlay(ph, pm, pd) + mid_shade(pm))

            # ---- read-outs ----
            a_c = cv.ease((t - plan.t0) / 0.4) * (1 - cv.ease((t - plan.pay) / 0.4))
            if a_c > 0:
                kit.text_parts(img, W / 2, LAB_Y, [(jumps_lab, scale(mix(MUTED, WHITE, 0.3), a_c))], lab_f)
                kit.text_parts(img, W / 2, NUM_Y, [(f"{n:,}", scale(WHITE, a_c))], num_f, glow=0.3 * a_c)
            a_p = cv.ease((t - plan.pay) / 0.5)
            if a_p > 0:
                kit.text_parts(img, W / 2, LAB_Y + 14, [("Sierpinski triangle", scale(GOLD, a_p))],
                               kit.serif(64), glow=0.35 * a_p)
                if t > plan.zoom0:
                    zt = (t - plan.zoom0) / (plan.zoom1 - plan.zoom0)
                    z = 2 ** (2 * cv.ease(zt))
                    az = cv.ease((t - plan.zoom0) / 0.4)
                    kit.text_parts(img, W / 2, NUM_Y + 26, [("zoom ", scale(MUTED, az)),
                                                            (f"×{z:.1f}", scale(WHITE, az))],
                                   kit.sans(40, "bold"))
                else:
                    kit.text_parts(img, W / 2, NUM_Y + 26, [(f"{N:,}", scale(WHITE, a_p)),
                                                            (" random jumps", scale(MUTED, a_p))],
                                   kit.sans(40, "bold"))
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, sim, times, total, path, clips)

    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 5, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
