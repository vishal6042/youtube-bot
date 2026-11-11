"""15 pendulums, one release: a pendulum wave, seen from above.

Pendulum k swings exactly 16 + k times in 24 seconds (16, 17, … 30), so after
release they drift apart into travelling snakes, rows and apparent chaos, then
all finish a whole number of swings at 24 s and line up again.

Honest physics: lengths are solved from the exact (large-angle) pendulum period
for the release amplitude, and each swing is integrated from the full equation
θ'' = -(g/L)·sin θ, not the small-angle shortcut. The counter beside each bob
counts its real completed swings.

Hook: the first frame is the wave mid-dance, with the question; then it rewinds
at speed to the release, held by a bar, and lets go.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.special import ellipk

from . import canvas as cv
from . import kit
from . import sound as snd
from . import voice
from .canvas import CYAN, GOLD, MUTED, PINK, WHITE, W, mix, scale

FPS = 60
NP = 15
N0 = 16
GAMMA = 24.0                     # seconds until they line up again
G = 9.81
AMP = 0.08                       # metres pulled aside at release
CX = 520                         # pivot bar (screen x)
PX_PER_M = 330 / AMP             # release amplitude -> 330 px
ROW0, ROW1 = 486, 1312           # first and last pendulum rows (screen y)
BOB_R = 22
TILT = 0.035                     # a hint of 3D: bobs dip as they swing out
COUNT_X = 84
TIME_Y = 1420
HOOK_T0 = -0.3
COLD = (6.2, 9.9)                # sim time shown in the cold open

HOOK = [[("15", GOLD), ("pendulums.", WHITE), ("One", WHITE), ("release.", WHITE)],
        [("What", WHITE), ("happens", WHITE), ("next?", WHITE)]]

SCRIPT = {
    "hook": ("Fifteen pendulums, let go at the same moment. Watch what happens.", None),
    "rule": ("Each one is a little shorter than the last, so it swings a little faster.",
             [("Each one is a little shorter", 6), ("than the last", 3), ("so it swings", 3),
              ("a little *faster*", 3)]),
    "count": ("In 24 seconds, the longest swings 16 times. The next, 17. Right up to 30.",
              [("In 24 seconds", 3), ("the longest swings 16 times", 5), ("The next, 17", 3),
               ("Right up to 30", 4)]),
    "end": ("So at 24 seconds, every one finishes together. Back in line.",
            [("So at 24 seconds", 4), ("every one finishes *together*", 4), ("*Back in line*", 3)]),
}


# --------------------------------------------------------------------------- #
# Physics
# --------------------------------------------------------------------------- #
def exact_period(L: float, theta0: float) -> float:
    return 4 * math.sqrt(L / G) * ellipk(math.sin(theta0 / 2) ** 2)


def solve_length(T: float) -> float:
    """Length whose large-angle period is T when released AMP metres to the side."""
    L = G * (T / (2 * math.pi)) ** 2
    for _ in range(60):
        th = math.asin(min(0.99, AMP / L))
        L = L * (T / exact_period(L, th)) ** 2
    return L


def simulate(dt: float = 1 / 2400, t_max: float = GAMMA + 6.0) -> dict:
    """θ_k(t) on a fine grid (RK4 on the full equation), plus swing-completion times.
    Cached on disk: every frame worker needs it and it takes ~15 s."""
    import pickle

    from ..config import PROJECT_ROOT
    key = f"pw_{NP}_{N0}_{GAMMA}_{AMP}_{dt:.8f}_{t_max}.pkl"
    cache = PROJECT_ROOT / "data" / "cache" / "sims" / key
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    out = _simulate(dt, t_max)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(f".{__import__('os').getpid()}.tmp")
    tmp.write_bytes(pickle.dumps(out))
    tmp.replace(cache)
    return out


def _simulate(dt: float, t_max: float) -> dict:
    T = GAMMA / (N0 + np.arange(NP))
    L = np.array([solve_length(t) for t in T])
    th0 = np.arcsin(AMP / L)
    n = int(t_max / dt) + 1
    th = np.empty((n, NP))
    om = np.zeros(NP)
    x = th0.copy()
    k = G / L

    def acc(a):
        return -k * np.sin(a)
    for i in range(n):
        th[i] = x
        k1v, k1x = acc(x), om
        k2v, k2x = acc(x + 0.5 * dt * k1x), om + 0.5 * dt * k1v
        k3v, k3x = acc(x + 0.5 * dt * k2x), om + 0.5 * dt * k2v
        k4v, k4x = acc(x + dt * k3x), om + dt * k3v
        x = x + dt / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
        om = om + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
    ts = np.arange(n) * dt
    # A swing is complete each time the bob is back at the release side (max θ).
    done = []
    for j in range(NP):
        a = th[:, j]
        peaks = np.where((a[1:-1] > a[:-2]) & (a[1:-1] >= a[2:]) & (a[1:-1] > 0.5 * th0[j]))[0] + 1
        done.append(ts[peaks])
    # Centre crossings going right (for the notes).
    cross = []
    for j in range(NP):
        a = th[:, j]
        idx = np.where((a[:-1] < 0) & (a[1:] >= 0))[0]
        cross.append(ts[idx])
    return dict(th=th, dt=dt, L=L, th0=th0, T=T, done=done, cross=cross)


def state(sim: dict, ts: float) -> tuple[np.ndarray, np.ndarray]:
    """(x offset px, y dip px) of each bob at sim time ts (linear between samples)."""
    th, dt = sim["th"], sim["dt"]
    ts = max(0.0, min(ts, (len(th) - 2) * dt))
    i = int(ts / dt)
    f = ts / dt - i
    a = th[i] * (1 - f) + th[i + 1] * f
    L = sim["L"]
    return L * np.sin(a) * PX_PER_M, L * (1 - np.cos(a)) * PX_PER_M * TILT * 8


def swings_done(sim: dict, ts: float) -> list[int]:
    return [int(np.searchsorted(d, ts + 0.03, side="right")) for d in sim["done"]]


ROWS = np.linspace(ROW0, ROW1, NP)


def bob_colors() -> list[tuple[int, int, int]]:
    stops = [GOLD, (255, 150, 90), PINK, (190, 130, 230), CYAN]
    out = []
    for k in range(NP):
        f = k / (NP - 1) * (len(stops) - 1)
        i = min(len(stops) - 2, int(f))
        out.append(mix(stops[i], stops[i + 1], f - i))
    return out


COLORS = bob_colors()


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
SLOW_FROM, SLOW_EASE, SLOW_RATE = GAMMA - 0.7, 1.0, 0.12  # slow motion into the line-up


class Plan:
    def __init__(self, L: dict[str, voice.Line]):
        self.hook_at = 0.3
        self.rew = max(3.9, self.hook_at + L["hook"].secs + 0.3)
        self.rew_end = self.rew + 0.85        # reversed at speed back to the release
        self.release = self.rew_end + 0.55    # the bar lets go
        self.rule_at = self.release + 0.35
        self.count_at = self.release + 10.6
        # Playback after release: real time, then easing into slow motion so the
        # moment they line up lasts long enough to see.
        tau = np.arange(0, 60, 1 / 1200)
        u = np.clip((tau - SLOW_FROM) / SLOW_EASE, 0, 1)
        rate = 1 - (1 - SLOW_RATE) * u * u * (3 - 2 * u)
        self.tau = tau
        self.ts_of_tau = np.concatenate([[0], np.cumsum(rate[:-1]) / 1200])
        self.rate_of_tau = rate
        tau_sync = float(np.interp(GAMMA, self.ts_of_tau, tau))
        self.sync = self.release + tau_sync
        self.slow_at = self.release + SLOW_FROM + 0.4
        e = L["end"]
        together = _word(e, "together", 0.55)
        self.end_at = max(self.sync - together - 0.1, self.count_at + L["count"].secs + 0.3)
        self.total = max(self.sync + 2.4, self.end_at + e.secs + 1.2)

    def ts(self, tau: float) -> float:
        return float(np.interp(tau, self.tau, self.ts_of_tau))

    def video_t(self, ts: float) -> float:
        return self.release + float(np.interp(ts, self.ts_of_tau, self.tau))

    def rate(self, t: float) -> float:
        return float(np.interp(t - self.release, self.tau, self.rate_of_tau))


def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


def sim_time(plan: Plan, t: float) -> float:
    """Which moment of the swing to show at video time t."""
    if t < plan.rew:
        return COLD[0] + (COLD[1] - COLD[0]) * t / plan.rew
    if t < plan.rew_end:
        u = (t - plan.rew) / (plan.rew_end - plan.rew)
        return COLD[1] * (1 - cv.ease(u))
    return plan.ts(max(0.0, t - plan.release))


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def _linework(xs, dips, trail_xs, held: float, bar_x: float, snake: float) -> tuple[np.ndarray, tuple]:
    """Pivot bar, strings, motion trails, the snake curve and the release bar."""
    ss = 3
    box = (40, ROW0 - 70, 1000, ROW1 + 70)
    bw, bh = box[2] - box[0], box[3] - box[1]
    big = Image.new("RGB", (bw * ss, bh * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)

    def P(x, y):
        return ((x - box[0]) * ss, (y - box[1]) * ss)
    # pivot bar
    d.line([P(CX, ROW0 - 46), P(CX, ROW1 + 46)], fill=(120, 124, 138), width=5 * ss)
    d.line([P(CX - 1.5, ROW0 - 46), P(CX - 1.5, ROW1 + 46)], fill=(200, 204, 214), width=1 * ss)
    for k in range(NP):
        y = ROWS[k]
        bx, by = CX + xs[k], y + dips[k]
        d.line([P(CX, y - 6), P(bx, by)], fill=(150, 150, 160), width=int(1.6 * ss))
        # trail: a fading streak along the recent path
        tr = trail_xs[:, k]
        col = COLORS[k]
        for i in range(len(tr) - 1):
            f = (i + 1) / len(tr)
            d.line([P(CX + tr[i], y), P(CX + tr[i + 1], y)], fill=scale(col, 0.42 * f * f),
                   width=int((6 + 14 * f) * ss))
    if snake > 0:
        pts = _spline([(CX + xs[k], ROWS[k] + dips[k]) for k in range(NP)])
        d.line([P(x, y) for x, y in pts], fill=scale((255, 236, 200), 0.55 * snake), width=int(2.4 * ss),
               joint="curve")
    if held > 0:
        x = bar_x
        d.rounded_rectangle([*P(x - 7, ROW0 - 40), *P(x + 7, ROW1 + 40)], radius=7 * ss,
                            fill=scale((235, 196, 120), held))
    sharp = np.asarray(big.resize((bw, bh), Image.LANCZOS), np.float32)
    return kit.glow_of(sharp, 6, 0.75), box


def _spline(pts, steps: int = 8):
    """Catmull-Rom through the points (a smooth curve through the bobs)."""
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = (np.array(v, float) for v in (p[i - 1], p[i], p[i + 1], p[i + 2]))
        for s in range(steps):
            u = s / steps
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)))
    out.append(pts[-1])
    return out


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


def _soundtrack(plan: Plan, sim: dict, total: float, path: Path, clips) -> None:
    mixer = snd.Mixer(total)
    notes = [snd.pluck(snd.scale_freq(6 + k), dur=0.9, bright=0.7) for k in range(NP)]
    # Cold open: the bobs' notes as they really sound at that moment of the wave.
    for k in range(NP):
        for c in sim["cross"][k]:
            if COLD[0] <= c <= COLD[1]:
                t = (c - COLD[0]) / (COLD[1] - COLD[0]) * plan.rew
                mixer.add(t, notes[k], 0.22, float(np.clip((k - 7) / 9, -0.6, 0.6)))
    mixer.add(plan.rew, whoosh(0.9, 1400, 160), 0.5)
    mixer.add(plan.release - 0.04, snd.thud(110, 0.25), 0.6)
    times, gains = [], []
    for k in range(NP):
        for c in sim["cross"][k]:
            t = plan.video_t(c)
            if t < total - 0.3 and c < GAMMA + 1:
                times.append((t, k))
    ts = np.array([a for a, _ in times])
    g = snd.density_gains(ts, base=0.42, window=0.06, calm=2.0)
    for (t, k), gg in zip(times, g):
        mixer.add(t, notes[k], float(gg), float(np.clip((k - 7) / 9, -0.6, 0.6)))
    # The line-up: every bob's note at once, then the chord.
    for k in range(NP):
        mixer.add(plan.sync, notes[k], 0.16, float(np.clip((k - 7) / 9, -0.6, 0.6)))
    mixer.add(plan.sync + 0.25, snd.chord([snd.scale_freq(i) for i in (6, 8, 10, 13)], dur=total - plan.sync), 0.9)
    voice.voice_over(mixer, list(clips), bed=0.7)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    sim = simulate()
    lines = kit.spoken(SCRIPT, ffmpeg)
    plan = Plan(lines)
    total = plan.total
    clips = [(plan.hook_at, lines["hook"]), (plan.rule_at, lines["rule"]), (plan.count_at, lines["count"]),
             (plan.end_at, lines["end"])]
    caps = []
    for (at, line), key in zip(clips[1:], ["rule", "count", "end"]):
        caps += kit.captions(at, line, SCRIPT[key][1])

    bg = kit.backdrop(CX, (ROW0 + ROW1) / 2, warm=(58, 44, 30), rad=900)
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)
    with_hook = bg.copy()
    kit.hook(with_hook, HOOK, 99.0)
    bobs = cv.Sprites(COLORS, BOB_R)
    cnt_f, time_f, lab_f = kit.sans(30, "black"), kit.sans(72, "black"), kit.sans(27, "bold")
    trail_n = 9

    def frame(t: float) -> Image.Image:
        img = with_hook.copy() if t > hook_end + 0.05 else bg.copy()
        if t <= hook_end + 0.05:
            kit.hook(img, HOOK, t, t0=HOOK_T0)
        ts = sim_time(plan, t)
        xs, dips = state(sim, ts)
        # Trail = where each bob was over the last ~0.15 s of *shown* time.
        back = []
        for i in range(trail_n, 0, -1):
            tb = sim_time(plan, t - i * 0.016)
            tb = min(ts + 0.12, max(ts - 0.12, tb))      # fast rewind: keep streaks short
            back.append(state(sim, tb)[0])
        trail = np.array(back + [xs])
        held = 0.0
        bar_x = CX + 330 + BOB_R + 10
        if plan.rew_end - 0.3 <= t < plan.release + 0.5:
            held = cv.ease((t - plan.rew_end + 0.3) / 0.3)
            if t > plan.release:
                u = (t - plan.release) / 0.5
                bar_x += 160 * cv.ease(u)
                held *= 1 - cv.ease(u)
        snake = 1.0
        lw, box = _linework(xs, dips, trail, held, bar_x, snake)
        kit.add(img, box, lw)
        for k in range(NP):
            bobs.paste(img, COLORS[k], CX + xs[k], ROWS[k] + dips[k])

        # ---- counters and the clock (from release) ----
        a = cv.ease((t - plan.release + 0.2) / 0.5)
        if a > 0:
            done = swings_done(sim, ts) if t >= plan.release else [0] * NP
            fin = t >= plan.sync - 0.02
            for k in range(NP):
                col = GOLD if fin else mix(MUTED, WHITE, 0.5)
                pulse = 0.0
                d_k = sim["done"][k]
                j = int(np.searchsorted(d_k, ts, side="right")) - 1
                if j >= 0 and t >= plan.release:
                    pulse = math.exp(-((ts - d_k[j]) / 0.18) ** 2)
                kit.text_parts(img, COUNT_X, ROWS[k], [(f"{done[k]}", scale(mix(col, WHITE, pulse * 0.6), a))],
                               cnt_f, glow=0.25 * a * (1 + pulse))
            kit.text_parts(img, COUNT_X, ROW0 - 52, [("SWINGS", scale(MUTED, a))], kit.sans(22, "bold"))
            sec = ts if t >= plan.release else 0.0
            tc = GOLD if fin else WHITE
            kit.text_parts(img, CX, TIME_Y, [(f"{sec:4.1f}", scale(tc, a)), (" s", scale(MUTED, a))], time_f,
                           glow=0.3 * a)
            # progress line towards 24 s
            frac = min(1.0, sec / GAMMA)
            bar = _progress(frac, a, fin)
            kit.add(img, (CX - 260, TIME_Y + 46, CX + 260, TIME_Y + 66), bar)
            sm = cv.ease((t - plan.slow_at) / 0.4)
            if sm > 0:
                kit.text_parts(img, CX, TIME_Y + 92, [("SLOW MOTION", scale(MUTED, sm))], kit.sans(22, "bold"))
        if t >= plan.sync - 0.05:
            f = kit.flash(t, plan.sync + 0.25, 0.35)
            if f > 0.02:
                glow = np.zeros((ROW1 - ROW0 + 140, 1000 - 40, 3), np.float32)
                yy = np.arange(glow.shape[0])[:, None]
                xx = np.arange(glow.shape[1])[None, :]
                xline = CX + 330 - 40
                g = np.exp(-((xx - xline) / 26.0) ** 2) * f * 70
                glow += g[..., None] * np.array([1.0, 0.85, 0.55])[None, None, :]
                kit.add(img, (40, ROW0 - 70, 1000, ROW1 + 70), glow * np.ones_like(yy[..., None]))
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, sim, total, path, clips)

    return total, frame, sound


def _progress(frac: float, a: float, fin: bool) -> np.ndarray:
    ss = 3
    w, h = 520, 20
    big = Image.new("RGB", (w * ss, h * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    y = h * ss / 2
    d.line([(6 * ss, y), ((w - 6) * ss, y)], fill=scale(MUTED, 0.35 * a), width=3 * ss)
    if frac > 0:
        d.line([(6 * ss, y), ((6 + (w - 12) * frac) * ss, y)], fill=scale(GOLD if fin else WHITE, 0.9 * a),
               width=3 * ss)
    sharp = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32)
    return kit.glow_of(sharp, 4, 0.6)


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
