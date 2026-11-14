"""Buffon's needle: drop needles on a wooden floor, count them, and get pi.

Math in Motion. A real-looking scene rendered in Blender (Cycles, RTX 4090):
a varnished oak floor whose boards are exactly as wide as a needle is long,
and 5,000 steel needles dropped on it at random. A needle that lands across a
crack between two boards turns brass.

- hook: the finished floor, 10,000 needles, and pi on screen, spoken over it;
- rewind: the needles fly back up, the camera drops to the floor;
- needle one falls in slow motion and lands across a crack; needle two misses;
- the rain: needles fall faster and faster as the camera rises; the counter
  runs: 2 x dropped / crossed;
- payoff: 5,000 needles, pi to three decimal places, and why: a needle of
  length 1 on boards of width 1 crosses a crack with probability 2 / pi.

Honest numbers: each needle's centre and angle are uniform random draws
(numpy, seeded); whether it crosses is decided by its two ends landing on
different boards, and the counter counts exactly those. The seed was picked
(from a search, see `pick_seed`) so that the first needle crosses, the second
misses and the 5,000 land near pi; the needles themselves are not placed.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from . import blend as B
from . import buffon_model as M
from . import kit
from . import sound as snd
from . import voice
from .canvas import GOLD, WHITE

FPS = 60
N = 5_000
VOICE, RATE = kit.VOICE, kit.RATE              # British Sonia, +10%
MUTED = (196, 190, 178)

# floor and where needles may land (whole boards across)
FLOOR_X = (-14, 15)
FLOOR_Y = (-40.0, 60.0)
REGION = (-13.0, 14.0, -7.0, 35.0)
FIRST_BOX = (-1.0, 2.0, -0.35, 0.75)
N_FIRST = 10

HOOK = [[("Drop", WHITE), ("needles", WHITE), ("on", WHITE), ("a", WHITE), ("floor.", WHITE)],
        [("Count", WHITE), ("them.", WHITE), ("Get", GOLD), ("π.", GOLD)]]
HOOK_YS = (190, 272)
CAP_Y = 372
NUM_Y, SUB_Y = 505, 590

SCRIPT = {
    "hook": ("Drop needles on a wooden floor, count them, and out comes pi.", None),
    "rule": ("Each needle is exactly as long as a floorboard is wide.",
             [("Each needle is exactly as long", 6), ("as a floorboard is wide.", 5)]),
    "count": ("Drop them at random, and count the ones that land across a crack.",
              [("Drop them at random,", 4), ("and count the ones", 4), ("that land *across a crack*.", 5)]),
    "formula": ("Now double the number dropped, and divide by the number that crossed.",
                [("Now double the number dropped,", 5), ("and divide by", 3), ("the number that crossed.", 4)]),
    "result": ("Five thousand needles later: pi, to three decimal places.",
               [("*5,000* needles later:", 4), ("*π*, to *3* decimal places.", 5)]),
    "why": ("Why? A needle like this crosses a crack with a chance of exactly two over pi.",
            [("Why?", 1), ("A needle like this crosses a crack", 7), ("with a chance of exactly", 5), ("*2 over π*", 3)]),
}


def pick_seed(start: int = 1, stop: int = 20000) -> int:
    """The first seed whose first needle crosses, second misses and 5,000 give 2N/c = 3.1417."""
    target = int(round(2 * N / math.pi))                 # 3,183 crossings
    for s in range(start, stop):
        d = M.make_drops(N, s, REGION, FIRST_BOX, N_FIRST)
        if not (d["hit"][0] and not d["hit"][1] and int(d["hit"].sum()) == target):
            continue
        # and both are clear on screen: one crack well inside needle one, needle two well clear of both
        h = 0.5 * np.abs(np.cos(d["phi"][:2]))
        x = d["x"][:2]
        crack = np.round(x[0])
        if abs(x[0] - crack) > 0.6 * h[0] or h[0] < 0.3:
            continue
        lo, hi = x[1] - h[1], x[1] + h[1]
        if min(lo - np.floor(lo), np.ceil(hi) - hi) < 0.12:
            continue
        u = np.linspace(-0.5, 0.5, 41)[:, None]
        p0 = np.stack([x[0] + u[:, 0] * np.cos(d["phi"][0]), d["y"][0] + u[:, 0] * np.sin(d["phi"][0])], 1)
        p1 = np.stack([x[1] + u[:, 0] * np.cos(d["phi"][1]), d["y"][1] + u[:, 0] * np.sin(d["phi"][1])], 1)
        if np.min(np.linalg.norm(p0[:, None] - p1[None], axis=2)) < 0.15:     # the two never touch
            continue
        return s
    raise RuntimeError("no seed found")


SEED = 8122                 # pick_seed(): kept as a constant so every render draws the same needles


class Plan:
    def __init__(self, lines):
        self.lines = lines
        sec = {k: v.secs for k, v in lines.items()}
        at = {"hook": 0.15}
        self.r0 = max(3.0, at["hook"] + sec["hook"] + 0.35)       # hook ends: the rewind starts
        self.r1 = self.r0 + 1.35                                  # back at the start, camera on the floor
        at["rule"] = self.r1 + 0.15
        T1 = self.r1 + 2.15                                       # needle one lands (slow motion)
        T2 = max(T1 + 1.9, at["rule"] + sec["rule"] + 0.9)        # needle two
        at["count"] = T1 + 0.75
        T2 = max(T2, at["count"] + 1.0)
        firsts = [T1, T2] + list(np.linspace(T2 + 0.95, T2 + 3.1, N_FIRST - 2))
        self.rain0 = firsts[-1] + 0.35
        at["formula"] = max(at["count"] + sec["count"] + 0.45, self.rain0 + 0.4)
        self.rain1 = max(self.rain0 + 9.5, at["formula"] + sec["formula"] + 4.5)
        at["result"] = self.rain1 + 0.55
        at["why"] = at["result"] + sec["result"] + 0.45
        self.total = at["why"] + sec["why"] + 1.6
        self.at = at
        self.T = M.schedule(N, firsts, self.rain0, self.rain1, power=2.4)
        D = np.full(N, 0.55)
        D[:N_FIRST] = [1.75, 1.15, 0.95, 0.85, 0.78, 0.72, 0.68, 0.64, 0.61, 0.58]
        self.D = D
        self.s_end = self.rain1 + 1.5                             # story time when everything lies still
        # video time -> story time: the hook holds the end, the rewind runs it back
        tv = [0.0, self.r0]
        sv = [self.s_end, self.s_end]
        for u in np.linspace(0, 1, 61)[1:]:
            tv.append(self.r0 + (self.r1 - self.r0) * u)
            sv.append(self.s_end + (self.r1 - 0.25 - self.s_end) * B.smoother(u) ** 0.85)
        tv += [self.r1 + 0.0001, self.total + 5]
        sv += [self.r1, self.total + 5]
        self.tmap = [tv, sv]
        self.T1, self.T2 = T1, T2
        self.cam = self._camera()

    def _camera(self):
        WIDE = ((0.5, -7.5, 17.0), (0.5, 5.0, 0.0), 30.0, 9.0)
        WIDE2 = ((-0.2, -7.2, 16.4), (0.3, 5.3, 0.0), 30.5, 9.0)
        CLOSE = ((2.25, -1.65, 1.45), (1.84, 0.62, 0.03), 46.0, 1.0)
        CLOSE_B = ((2.15, -1.75, 1.5), (1.8, 0.6, 0.03), 46.0, 1.0)
        CLOSE2 = ((-0.15, -1.8, 1.5), (-0.5, 0.42, 0.03), 46.0, 1.1)
        CLOSE2_B = ((0.1, -2.1, 1.75), (-0.3, 0.45, 0.03), 46.0, 1.2)
        MID = ((0.5, -4.6, 5.6), (0.4, 1.6, 0.0), 34.0, 3.0)
        r0, r1 = self.r0, self.r1
        k = [(0.0, *WIDE), (r0, *WIDE2), (r1 + 0.2, *CLOSE), (self.T1 + 0.9, *CLOSE_B),
             (self.T2 - 0.15, *CLOSE2), (self.T2 + 1.2, *CLOSE2_B),
             (self.rain0 + 2.4, *MID), (self.rain1 - 0.5, *WIDE)]
        # the end: down to one brass needle lying across a crack ("a needle like this")
        hx, hy = hero_xy()
        END = ((hx + 0.5, hy - 2.6, 2.0), (hx, hy + 0.05, 0.03), 46.0, 1.4)
        END_B = ((hx + 0.95, hy - 2.5, 1.85), (hx + 0.03, hy + 0.05, 0.03), 46.0, 1.4)
        why = self.at["why"]
        k += [(why - 0.6, *_mixk(WIDE, WIDE2, 0.35)), (why + 2.1, *END), (self.total + 1.0, *END_B)]
        return [(t, list(p), list(q), lens, fs) for t, p, q, lens, fs in k]

    def job(self, drops, samples: int = 64) -> dict:
        return dict(width=B.OUT_W, height=B.OUT_H, fps=FPS, samples=samples, model_path=str(Path(M.__file__)),
                    floor_x=list(FLOOR_X), floor_y=list(FLOOR_Y), gap=0.016,
                    drops={k: np.round(np.asarray(v, float), 6).tolist() for k, v in drops.items()},
                    T=np.round(self.T, 6).tolist(), D=np.round(self.D, 6).tolist(),
                    tmap=[np.round(self.tmap[0], 6).tolist(), np.round(self.tmap[1], 6).tolist()],
                    cam=self.cam, sun=3.2, sun_el=30, sun_az=140, window=3500, world=1.8, exposure=0.0)


def _mixk(a, b, u):
    return (tuple(np.add(np.multiply(a[0], 1 - u), np.multiply(b[0], u))),
            tuple(np.add(np.multiply(a[1], 1 - u), np.multiply(b[1], u))), a[2] + (b[2] - a[2]) * u, a[3])


@lru_cache(maxsize=1)
def hero():
    """The needle the camera ends on: crosses a crack near its middle, well clear of
    other needles, near the middle of the wide view."""
    d = M.make_drops(N, SEED, REGION, FIRST_BOX, N_FIRST)
    x, y, phi = d["x"], d["y"], d["phi"]
    h = 0.5 * np.abs(np.cos(phi))
    mid = np.abs(x - np.round(x)) < 0.35 * h
    ok = d["hit"] & mid & (h > 0.25) & (np.abs(x - 0.5) < 6) & (y > -3) & (y < 14)
    u = np.linspace(-0.5 * M.L, 0.5 * M.L, 41)

    def seg(j):
        return np.stack([x[j] + u * np.cos(phi[j]), y[j] + u * np.sin(phi[j])], 1)

    best, room = -1, -1.0
    for i in np.where(ok)[0]:                      # the loneliest one (the floor is crowded)
        p = seg(i)
        js = np.where((np.hypot(x - x[i], y - y[i]) < 1.2) & (np.arange(len(x)) != i))[0]
        gap = min((np.linalg.norm(p[:, None] - seg(j)[None], axis=2).min() for j in js), default=9.0)
        if gap > room:
            best, room = int(i), float(gap)
    return best


def hero_xy():
    d = M.make_drops(N, SEED, REGION, FIRST_BOX, N_FIRST)
    i = hero()
    return float(d["x"][i]), float(d["y"][i])


@lru_cache(maxsize=1)
def drops():
    return M.make_drops(N, SEED, REGION, FIRST_BOX, N_FIRST)


def counts(plan: Plan, s: float):
    """(dropped, crossed) at story time s: a needle counts once it has settled."""
    d = drops()
    done = plan.T + 0.25 <= s
    return int(done.sum()), int((done & d["hit"]).sum())


def fmt(n: int) -> str:
    return f"{n:,}"


def build(ffmpeg: str, seed: int = 7, samples: int = 64):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    d = drops()
    job = plan.job(d, samples)
    folder = B.job_dir("buffon_scene", job, [M.__file__])
    keys = ["rule", "count", "formula", "result", "why"]
    clips = [(plan.at[k], lines[k]) for k in ["hook"] + keys]
    caps = []
    for k in keys:
        caps += kit.captions(plan.at[k], lines[k], SCRIPT[k][1])
    f_cap = kit.sans(B.px(48), "bold")
    captions = B.Captions(caps, f_cap, CAP_Y)
    hook = B.Hook(HOOK, kit.serif(B.px(70)), HOOK_YS)
    f_big = kit.sans(B.px(104), "black")
    f_pi = kit.serif(B.px(104))
    f_sub = kit.sans(B.px(40), "semi")
    f_tag = kit.sans(B.px(30), "bold")
    tag_hit = B.row_sprite([("ACROSS A CRACK", GOLD)], f_tag)
    tag_miss = B.row_sprite([("MISSES", (235, 232, 226))], f_tag)
    sprite_cache: dict = {}

    def sprite(key, parts, font):
        if key not in sprite_cache:
            if len(sprite_cache) > 400:
                sprite_cache.clear()
            sprite_cache[key] = B.row_sprite(parts, font)
        return sprite_cache[key]

    formula_on = plan.at["formula"] + 0.2

    def counter(img: Image.Image, t: float) -> None:
        s = M.story_time(plan.tmap, t)
        n, c = counts(plan, s)
        hook_phase = t < plan.r0 + 0.25
        a = 1.0 if t < plan.r0 else max(0.0, 1 - B.smooth((t - plan.r0) / 0.25))
        if not hook_phase:
            a = B.smooth((t - plan.T1 - 0.3) / 0.4)
        if a <= 0:
            return
        show_pi = hook_phase or t >= formula_on
        if show_pi:
            fa = 1.0 if hook_phase else B.smooth((t - formula_on) / 0.5)
            val = f"{2 * n / c:.4f}" if c else "—"
            spr = sprite(("pi", val), [("π ≈ ", GOLD, f_pi), (val, WHITE, f_big)], f_big)
            B.blit_center(img, spr, B.OUT_W / 2, NUM_Y * K_, a * fa)
            sub = sprite(("sub", n, c), [("2 × ", MUTED), (fmt(n), WHITE), (" dropped  ÷  ", MUTED),
                                         (fmt(c), GOLD), (" crossed", MUTED)], f_sub)
            B.blit_center(img, sub, B.OUT_W / 2, SUB_Y * K_, a * fa)
        if not hook_phase and t < formula_on:                  # the plain count leaves before pi arrives
            fa = a * (1 - B.smooth((t - formula_on + 0.3) / 0.3))
            sub = sprite(("cnt", n, c), [(fmt(n), WHITE), (" dropped  ·  ", MUTED), (fmt(c), GOLD),
                                         (" crossed", MUTED)], f_sub)
            B.blit_center(img, sub, B.OUT_W / 2, NUM_Y * K_, fa)

    def tags(img: Image.Image, t: float) -> None:
        """Labels on the first two needles while the camera is close."""
        if t < plan.r1 or t > plan.rain0 + 1.2:
            return
        pos, tgt, lens, _ = M.camera(plan.cam, t)
        for i, spr in ((0, tag_hit), (1, tag_miss)):
            a = B.smooth((t - plan.T[i] - 0.35) / 0.35) * (1 - B.smooth((t - plan.rain0 - 0.4) / 0.6))
            if a <= 0:
                continue
            x, y, z = B.project(pos, tgt, lens, [[d["x"][i], d["y"][i], 0.02]])
            if z[0] <= 0:
                continue
            B.blit_center(img, spr, x[0], y[0] - B.px(105), a)

    hi = hero()

    def hero_tag(img: Image.Image, t: float) -> None:
        a = B.smooth((t - plan.at["why"] - 2.0) / 0.4)
        if a <= 0:
            return
        pos, tgt, lens, _ = M.camera(plan.cam, t)
        x, y, z = B.project(pos, tgt, lens, [[d["x"][hi], d["y"][hi], 0.02]])
        if z[0] > 0:
            B.blit_center(img, tag_hit, x[0], y[0] - B.px(105), a)

    def frame(t: float) -> Image.Image:
        fi = min(int(round(t * FPS)), int(total * FPS) - 1)
        arr = B.load_frame(folder, fi)
        arr = B.shade_top(B.grade(arr), 520 * K_, 820 * K_, 0.55)
        img = B.to_image(arr)
        tags(img, t)
        hero_tag(img, t)
        counter(img, t)
        if t < plan.r0 + 0.4:
            ha = 1.0 if t < plan.r0 else 1 - B.smooth((t - plan.r0) / 0.4)
            hook.draw(img, t, ha)
        captions.draw(img, t)
        return img

    def sound(path: Path) -> None:
        m = snd.Mixer(total)
        m.add(0.0, B.pad(total, 55.0), 0.20)
        m.add(0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7)], dur=3.2), 0.45)
        m.add(plan.r0 - 0.05, B.whoosh(plan.r1 - plan.r0 + 0.2, 900, 220, seed=4), 0.30)
        T = plan.T
        g = snd.density_gains(T, 0.55, window=0.06, calm=1.5)
        rng = np.random.default_rng(5)
        tinks = [tink(f) for f in (1650, 1900, 2200, 2500, 2850, 3200)]
        x0, x1 = REGION[0], REGION[1]
        for i in range(N):
            gi = float(g[i]) * (1.6 if i < N_FIRST else 1.0)
            pan = float(np.clip(((d["x"][i] - x0) / (x1 - x0)) * 2 - 1, -1, 1)) * 0.6
            m.add(float(T[i]), tinks[rng.integers(len(tinks))], gi, pan)
            if i < N_FIRST and d["hit"][i]:
                m.add(float(T[i]) + 0.25, snd.pluck(snd.scale_freq(10 + i % 3), dur=1.0, bright=0.5), 0.30)
        m.add(plan.at["result"] - 0.1, snd.chord([snd.scale_freq(i) for i in (5, 7, 10, 12, 15)],
                                                 dur=total - plan.at["result"] + 0.4), 0.55)
        voice.voice_over(m, clips, bed=0.75)
        m.write(path, total)

    build.plan, build.job, build.folder = plan, job, folder
    return total, frame, sound


K_ = B.K


def tink(freq: float) -> np.ndarray:
    """A steel needle striking varnished wood: a bright inharmonic ping and a tiny knock."""
    dur = 0.35
    t = np.arange(int(snd.SR * dur)) / snd.SR
    ping = (np.sin(2 * np.pi * freq * t) * np.exp(-t * 32) + 0.6 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 48)
            + 0.3 * np.sin(2 * np.pi * freq * 5.40 * t) * np.exp(-t * 70))
    knock = np.sin(2 * np.pi * 420 * t) * np.exp(-t * 90)
    return ((0.55 * ping + 0.6 * knock) * (1 - np.exp(-t * 4000))).astype(np.float32)


def frames_needed(total: float) -> list[int]:
    return list(range(int(total * FPS)))


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    p3d, penc = B.split_progress(progress, 0.9)
    B.render_frames("buffon_scene", build.job, frames_needed(total), [M.__file__], progress=p3d)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, penc, module=__name__,
                      build_kw={"seed": seed}, size=(B.OUT_W, B.OUT_H), max_workers=12)
