"""The hidden curve in your coffee: light bouncing inside a cup draws a nephroid,
and a light on the rim draws a heart (a cardioid).

Math in Motion. A real-looking scene rendered in Blender (Cycles, RTX 4090):
a white glazed mug of milky coffee on a walnut table in low morning sun.

- hook: the mug from above at an angle, the bright curve on the coffee, the
  question spoken over it;
- the sun goes behind a cloud while the camera rises to look straight down;
  one ray of sunlight comes in, bounces off the inside wall; then more rays,
  then hundreds, and where the bounced rays crowd together the bright curve
  appears; the cloud passes and the real curve lies exactly under them;
- its name: a nephroid (its exact shape drawn over it);
- evening: the sun goes, a small clip-on LED drops onto the near rim and
  switches on; its rays fan out and bounce, and the curve becomes a heart:
  a cardioid;
- back to the angled view: the heart in the coffee.

Honest light: the reflected light on the coffee is traced photon by photon for
this exact cup, sun direction and lamp (graph_bot/sims/caustic_model.py), with
the glaze's real reflectance; Blender renders everything else. The drawn rays
are true paths seen from above; the outlines are the exact caustics (the
nephroid for sunlight, and for the LED, which sits just inside the rim, the
envelope of its reflected rays, within 3% of a perfect cardioid).
"""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import cairo
import numpy as np
from PIL import Image

from . import blend as B
from . import caustic_model as C
from . import kit
from . import sound as snd
from . import voice
from .canvas import GOLD, WHITE

FPS = 60
VOICE, RATE = kit.VOICE, kit.RATE
MUTED = (200, 194, 182)

SUN_EL, SUN_AZ = 16.0, 150.0              # low morning sun from the back left
LAMP_ANGLE = -90.0                        # the clip sits on the near rim (towards the camera)
LAMP_R, LAMP_Z = 0.935, C.HW - 0.05
LAMP_CONE = 80.0
LAMP_AIMZ = -0.2
LIQUID = (0.52, 0.35, 0.21)               # milky coffee (linear albedo)
SUN_S = 4.0                               # W/m2 at normal incidence (Blender sun strength)
LAMP_I = 4.0                              # W/sr

HERO = ((0.0, -2.35, 3.75), (0.05, 0.12, -0.25), 35.0, 0.35)
HERO_B = ((0.24, -2.3, 3.68), (0.07, 0.1, -0.25), 35.0, 0.35)
TOP = ((0.0, -0.06, 5.4), (0.0, 0.0, 0.0), 35.0, 2.0)

HOOK = [[("A", WHITE), ("perfect", GOLD), ("curve", GOLD)],
        [("hides", WHITE), ("in", WHITE), ("your", WHITE), ("coffee.", WHITE)]]
HOOK_YS = (190, 272)
CAP_Y = 372

SCRIPT = {
    "hook": ("On a sunny morning, a perfect curve hides in your coffee.", None),
    "light": ("Sunlight comes in low, and bounces off the inside of the cup.",
              [("Sunlight comes in low,", 4), ("and bounces off", 3), ("the inside of the cup.", 5)]),
    "crowd": ("Every ray bounces a little differently, and where the bounced rays crowd together, the light piles up.",
              [("Every ray bounces", 3), ("a little differently,", 3), ("and where the bounced rays", 5),
               ("crowd together,", 2), ("the light *piles up*.", 4)]),
    "name": ("That bright curve is called a nephroid.", [("That bright curve", 3), ("is called a *nephroid*.", 4)]),
    "twist": ("Now clip a tiny light onto the rim.", [("Now clip a tiny light", 5), ("onto the rim.", 3)]),
    "heart": ("The curve turns into a heart: a cardioid.", [("The curve turns", 3), ("into a heart:", 3), ("a *cardioid*.", 2)]),
    "close": ("Same cup. Same coffee. Just geometry.", [("Same cup.", 2), ("Same coffee.", 2), ("Just *geometry*.", 2)]),
}


def lamp_pos():
    a = math.radians(LAMP_ANGLE)
    return (LAMP_R * math.cos(a), LAMP_R * math.sin(a), LAMP_Z)


def lamp_aim():
    a = math.radians(LAMP_ANGLE)
    return (-math.cos(a), -math.sin(a), LAMP_AIMZ)


# --------------------------------------------------------------------------- #
# The two light maps (traced once, cached by their parameters)
# --------------------------------------------------------------------------- #
MAP_RES, MAP_N = 1024, 60_000_000


def maps() -> dict:
    from scipy.ndimage import gaussian_filter

    key = json.dumps(dict(el=SUN_EL, az=SUN_AZ, lp=lamp_pos(), la=lamp_aim(), cone=LAMP_CONE, hw=C.HW,
                          n=C.GLAZE_N, res=MAP_RES, N=MAP_N, v=2), sort_keys=True)
    h = hashlib.sha1(key.encode()).hexdigest()[:12]
    folder = B.CACHE / "coffee_maps"
    folder.mkdir(parents=True, exist_ok=True)
    out = {"sun": folder / f"sun_{h}.npy", "lamp": folder / f"lamp_{h}.npy"}
    if not out["sun"].exists():
        m = C.sun_map(SUN_EL, SUN_AZ, n=MAP_N, res=MAP_RES, seed=1)
        np.save(out["sun"], gaussian_filter(m, 0.9).astype(np.float32))       # the glaze is not a perfect mirror
    if not out["lamp"].exists():
        m = C.lamp_map(lamp_pos(), lamp_aim(), LAMP_CONE, n=MAP_N, res=MAP_RES, seed=2)
        np.save(out["lamp"], gaussian_filter(m, 0.9).astype(np.float32))
    return {k: str(v) for k, v in out.items()}


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
def _mix(a, b, u):
    return tuple(np.array(x, float) * (1 - u) + np.array(y, float) * u if not isinstance(x, float)
                 else x + (y - x) * u for x, y in zip(a, b))


class Plan:
    def __init__(self, lines):
        sec = {k: v.secs for k, v in lines.items()}
        at = {"hook": 0.15}
        self.r0 = max(3.2, at["hook"] + sec["hook"] + 0.3)        # leave the hook: cloud and camera move
        self.top_at = self.r0 + 1.7                                # straight down
        at["light"] = self.r0 + 1.2
        self.ray1 = at["light"] + 0.9                              # the first ray travels
        at["crowd"] = at["light"] + sec["light"] + 0.35
        self.many0 = at["crowd"] - 0.4                             # more rays, then hundreds
        self.many1 = at["crowd"] + sec["crowd"] * 0.75
        self.sun_back = at["crowd"] + sec["crowd"] - 1.1           # the cloud passes at "piles up"
        self.rays_out = self.sun_back + 1.6
        at["name"] = at["crowd"] + sec["crowd"] + 0.45
        self.neph_on = at["name"] + 0.4
        at["twist"] = at["name"] + sec["name"] + 0.9
        self.dusk0, self.dusk1 = at["twist"] - 0.6, at["twist"] + 1.0
        self.clip0, self.clip1 = at["twist"] + 0.5, at["twist"] + 1.35
        self.led_on = self.clip1 + 0.35
        self.fan0 = self.led_on + 0.25
        at["heart"] = max(at["twist"] + sec["twist"] + 0.5, self.led_on + 0.9)
        self.card_on = at["heart"] + 0.5
        self.back0 = at["heart"] + sec["heart"] + 0.5
        self.back1 = self.back0 + 1.8
        at["close"] = self.back1 - 0.2
        self.total = at["close"] + sec["close"] + 1.6
        self.at = at

    def cam(self, t: float):
        if t < self.r0:
            return _mix(HERO, HERO_B, B.smoother(t / self.r0) * 0.6)
        if t < self.top_at:
            u = B.smoother((t - self.r0) / (self.top_at - self.r0))
            return _mix(_mix(HERO, HERO_B, 0.6), TOP, u)
        if t < self.back0:
            return TOP
        u = B.smoother((t - self.back0) / (self.back1 - self.back0))
        end = _mix(HERO, HERO_B, 0.25 * B.smooth((t - self.back1) / 4.0))
        return _mix(TOP, end, u)

    def sun(self, t: float) -> float:
        """The cloud: full sun, dim while the rays are drawn, back at "piles up", gone at dusk."""
        dim = 0.10
        if t < self.r0:
            return 1.0
        if t < self.sun_back:
            return 1 - (1 - dim) * B.smooth((t - self.r0) / 0.9)
        if t < self.dusk0:
            return dim + (1 - dim) * B.smooth((t - self.sun_back) / 1.1)
        return 1 - B.smooth((t - self.dusk0) / (self.dusk1 - self.dusk0))

    def lamp(self, t: float) -> float:
        return B.smooth((t - self.led_on) / 0.3)

    def clip(self, t: float):
        """(outward, up) offset of the clip from its place on the rim; None before it comes in.
        It swings in from beyond the near edge of the picture and settles onto the rim."""
        if t < self.clip0:
            return None
        u = min(1.0, (t - self.clip0) / (self.clip1 - self.clip0))
        e = 1 - B.smoother(u)
        return 1.9 * e, 0.75 * e ** 0.6 + 0.0

    def state(self, t: float) -> dict:
        pos, tgt, lens, fstop = self.cam(t)
        r = lambda v: [round(float(x), 5) for x in v]
        return dict(pos=r(pos), tgt=r(tgt), lens=round(float(lens), 4), fstop=round(float(fstop), 4),
                    sun=round(self.sun(t), 4), lamp=round(self.lamp(t), 4),
                    clip=None if self.clip(t) is None else [round(v, 5) for v in self.clip(t)])

    def frames(self):
        """Each video frame's state, the frames whose state is new (rendered), and frame -> rendered frame."""
        n = int(self.total * FPS)
        rep, seen, unique, states = [], {}, [], {}
        for fi in range(n):
            st = self.state(fi / FPS)
            k = json.dumps(st, sort_keys=True)
            if k not in seen:
                seen[k] = fi
                unique.append(fi)
                states[str(fi)] = st
            rep.append(seen[k])
        return states, unique, rep

    def job(self, states, samples: int = 64) -> dict:
        return dict(width=B.OUT_W, height=B.OUT_H, samples=samples, hw=C.HW, liquid_rgb=list(LIQUID),
                    table_z=-2.12, emit_k=1 / math.pi, sun_el=SUN_EL, sun_az=SUN_AZ, sun_strength=SUN_S,
                    lamp_angle=LAMP_ANGLE, lamp_z=LAMP_Z, lamp_pos=list(lamp_pos()), lamp_aim=list(lamp_aim()),
                    lamp_cone=LAMP_CONE, lamp_intensity=LAMP_I, world=1.6, exposure=0.0,
                    maps=maps(), frames=states)


# --------------------------------------------------------------------------- #
# Drawing over the picture
# --------------------------------------------------------------------------- #
def _ctx():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, B.OUT_W, B.OUT_H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    return surf, ctx


def _add(img: Image.Image, surf, glow: float = 0.0) -> None:
    """Add a premultiplied cairo layer as light (plus an optional soft bloom)."""
    from scipy.ndimage import gaussian_filter

    surf.flush()
    buf = np.ndarray((B.OUT_H, B.OUT_W, 4), np.uint8, surf.get_data())
    a = buf[..., 2::-1].astype(np.float32)
    if not a.any():
        return
    if glow:
        a = a + gaussian_filter(a, (5 * B.K, 5 * B.K, 0)) * glow
    base = np.asarray(img, np.float32)
    img.paste(Image.fromarray(np.clip(base + a, 0, 255).astype(np.uint8)))


def _over(img: Image.Image, surf) -> None:
    surf.flush()
    buf = np.ndarray((B.OUT_H, B.OUT_W, 4), np.uint8, surf.get_data())
    al = buf[..., 3:4].astype(np.float32) / 255
    if al.max() <= 0:
        return
    base = np.asarray(img, np.float32)
    img.paste(Image.fromarray(np.clip(base * (1 - al) + buf[..., 2::-1], 0, 255).astype(np.uint8)))


def _path(ctx, pts):
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)


@lru_cache(maxsize=1)
def sun_rays():
    reach = C.HW / math.tan(math.radians(SUN_EL))
    one = C.ray_paths(SUN_AZ, "sun", 1)
    few = C.ray_paths(SUN_AZ, "sun", 9)
    many = C.ray_paths(SUN_AZ, "sun", 260)
    clip = lambda rays: [(p, q, q + (e - q) * min(1.0, reach / max(1e-9, np.linalg.norm(e - q)))) for p, q, e in rays]
    return clip(one), clip(few), clip(many)


@lru_cache(maxsize=1)
def lamp_rays():
    src = np.array(lamp_pos()[:2])
    base = math.degrees(math.atan2(-src[1], -src[0]))
    return (C.ray_paths(src, "lamp", 9, spread=(base - 70, base + 70)),
            C.ray_paths(src, "lamp", 240, spread=(base - 84, base + 84)))


def draw_rays(ctx, cam, rays, alpha: float, width: float, grow: float = 1.0, col=(1.0, 0.92, 0.74),
              incoming: float = 0.45):
    """Each ray: the incoming leg, then the bounced leg; `grow` 0..1 reveals them along their length."""
    pos, tgt, lens, _ = cam
    for p, q, e in rays:
        pts3 = np.array([[p[0], p[1], 0.0], [q[0], q[1], 0.0], [e[0], e[1], 0.0]])
        x, y, _ = B.project(pos, tgt, lens, pts3)
        l1 = math.hypot(x[1] - x[0], y[1] - y[0])
        l2 = math.hypot(x[2] - x[1], y[2] - y[1])
        L = (l1 + l2) * grow
        ctx.set_line_width(width)
        ctx.set_source_rgba(*col, alpha * incoming)
        ctx.move_to(x[0], y[0])
        f = min(1.0, L / max(l1, 1e-6))
        ctx.line_to(x[0] + (x[1] - x[0]) * f, y[0] + (y[1] - y[0]) * f)
        ctx.stroke()
        if L <= l1:
            continue
        ctx.set_source_rgba(*col, alpha)
        ctx.move_to(x[1], y[1])
        f = (L - l1) / max(l2, 1e-6)
        ctx.line_to(x[1] + (x[2] - x[1]) * f, y[1] + (y[2] - y[1]) * f)
        ctx.stroke()


def draw_curve(ctx, cam, pts2, frac: float, alpha: float, width: float, dash: float):
    pos, tgt, lens, _ = cam
    P = np.c_[pts2, np.zeros(len(pts2))]
    x, y, _ = B.project(pos, tgt, lens, P)
    k = max(2, int(len(x) * frac))
    ctx.set_dash([dash, dash * 0.8])
    ctx.set_line_width(width)
    ctx.set_source_rgba(1.0, 0.80, 0.36, alpha)
    _path(ctx, list(zip(x[:k], y[:k])))
    ctx.stroke()
    ctx.set_dash([])


def build(ffmpeg: str, seed: int = 7, samples: int = 64):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    states, unique, rep = plan.frames()
    job = plan.job(states, samples)
    folder = B.job_dir("coffee_scene", job, [B.SCRIPTS / "bkit.py", Path(C.__file__)])
    keys = ["light", "crowd", "name", "twist", "heart", "close"]
    clips = [(plan.at[k], lines[k]) for k in ["hook"] + keys]
    caps = []
    for k in keys:
        caps += kit.captions(plan.at[k], lines[k], SCRIPT[k][1])
    captions = B.Captions(caps, kit.sans(B.px(48), "bold"), CAP_Y)
    hook = B.Hook(HOOK, kit.serif(B.px(72)), HOOK_YS)
    f_name = kit.serif(B.px(76))
    f_tag = kit.sans(B.px(32), "semi")
    neph_lbl = (B.row_sprite([("Nephroid", GOLD)], f_name), B.row_sprite([("THE CURVE SUNLIGHT MAKES", MUTED)], f_tag))
    card_lbl = (B.row_sprite([("Cardioid", GOLD)], f_name), B.row_sprite([("THE CURVE OF A LIGHT ON THE RIM", MUTED)], f_tag))
    neph = C.nephroid(SUN_AZ)
    src = np.array(lamp_pos()[:2])
    base = math.degrees(math.atan2(-src[1], -src[0]))
    card = C.lamp_envelope(src, base - 88, base + 88, 900)
    one, few, many = sun_rays()
    lfew, lmany = lamp_rays()
    label_y = 482

    def overlay(img: Image.Image, t: float) -> None:
        cam = plan.cam(t)
        on_top = plan.top_at - 0.2 <= t < plan.back0 + 0.3
        if not on_top:
            return
        fade_all = 1 - B.smooth((t - plan.back0) / 0.35)
        surf, ctx = _ctx()
        # sunlight: one ray, a few, then hundreds; gone once the real curve is back
        out = 1 - B.smooth((t - plan.sun_back - 0.4) / (plan.rays_out - plan.sun_back - 0.4))
        if t >= plan.ray1 and out > 0:
            g = B.smoother((t - plan.ray1) / 1.3)
            a1 = 0.95 * out * (1 - 0.6 * B.smooth((t - plan.many1) / 1.0))
            draw_rays(ctx, cam, one, a1, 3.2 * B.K, g, incoming=0.8)
            if t >= plan.many0:
                g2 = B.smoother((t - plan.many0) / 1.0)
                draw_rays(ctx, cam, few, 0.65 * out, 1.8 * B.K, g2)
                n_many = int(len(many) * B.smooth((t - plan.many0 - 0.8) / (plan.many1 - plan.many0 - 0.8)))
                if n_many:
                    order = np.random.default_rng(3).permutation(len(many))[:n_many]
                    draw_rays(ctx, cam, [many[i] for i in sorted(order)], 0.20 * out, 1.1 * B.K, 1.0)
        # the LED's rays fan out once it is on
        if t >= plan.fan0:
            g = B.smoother((t - plan.fan0) / 1.0)
            lout = 1 - B.smooth((t - plan.card_on - 0.6) / 1.0)
            if lout > 0:
                draw_rays(ctx, cam, lfew, 0.7 * lout, 1.8 * B.K, g, col=(1.0, 0.95, 0.86))
                n_many = int(len(lmany) * B.smooth((t - plan.fan0 - 0.5) / 1.6))
                if n_many:
                    order = np.random.default_rng(4).permutation(len(lmany))[:n_many]
                    draw_rays(ctx, cam, [lmany[i] for i in sorted(order)], 0.20 * lout, 1.1 * B.K, 1.0,
                              col=(1.0, 0.95, 0.86))
        _add(img, surf, glow=0.6)
        # the exact curves, dashed, and their names
        surf2, ctx2 = _ctx()
        na = B.smooth((t - plan.neph_on) / 0.4) * (1 - B.smooth((t - plan.dusk0) / 0.6))
        if na > 0:
            draw_curve(ctx2, cam, neph, B.smoother((t - plan.neph_on) / 1.0), 0.95 * na * fade_all, 2.6 * B.K, 9 * B.K)
        ca = B.smooth((t - plan.card_on) / 0.4)
        if ca > 0:
            draw_curve(ctx2, cam, card, B.smoother((t - plan.card_on) / 1.2), 0.95 * ca * fade_all, 2.6 * B.K, 9 * B.K)
        _over(img, surf2)
        for a, (big, small) in ((na * fade_all, neph_lbl), (ca * fade_all, card_lbl)):
            if a > 0:
                B.blit_center(img, big, B.OUT_W / 2, label_y * B.K, a)
                B.blit_center(img, small, B.OUT_W / 2, (label_y + 62) * B.K, a)

    def frame(t: float) -> Image.Image:
        fi = min(int(round(t * FPS)), len(rep) - 1)
        arr = B.load_frame(folder, rep[fi])
        arr = B.shade_top(B.grade(arr), 470 * B.K, 760 * B.K, 0.45)
        img = B.to_image(arr)
        overlay(img, t)
        if t < plan.r0 + 0.4:
            ha = 1.0 if t < plan.r0 else 1 - B.smooth((t - plan.r0) / 0.4)
            hook.draw(img, t, ha)
        captions.draw(img, t)
        return img

    def sound(path: Path) -> None:
        m = snd.Mixer(total)
        m.add(0.0, B.pad(total, 55.0), 0.22)
        m.add(0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7)], dur=3.2), 0.45)
        m.add(plan.r0 - 0.05, B.whoosh(plan.top_at - plan.r0 + 0.2, 260, 700, seed=8), 0.22)
        m.add(plan.ray1 + 0.55, snd.pluck(snd.scale_freq(12), dur=1.4, bright=0.5), 0.40)   # the first ray strikes the wall
        for i in range(9):                                                                 # the few
            m.add(plan.many0 + 0.45 + i * 0.09, snd.pluck(snd.scale_freq(9 + i % 5), dur=1.0, bright=0.4), 0.16)
        shimmer = B.noise(plan.many1 - plan.many0, 21, 6500, high=True)
        env = np.sin(np.pi * np.linspace(0, 1, len(shimmer))) ** 1.5
        m.add(plan.many0 + 0.4, (shimmer * env).astype(np.float32), 0.05)
        m.add(plan.sun_back, snd.chord([snd.scale_freq(i) for i in (5, 7, 10, 12)], dur=3.0), 0.42)   # the curve appears
        m.add(plan.clip1 - 0.03, snd.thud(140, 0.15), 0.6)                                            # the clip snaps on
        m.add(plan.led_on, snd.pluck(snd.scale_freq(15), dur=0.5, bright=1.0), 0.25)                   # click on
        m.add(plan.card_on, snd.chord([snd.scale_freq(i) for i in (3, 7, 10, 14)], dur=total - plan.card_on + 0.4), 0.5)
        voice.voice_over(m, clips, bed=0.75)
        m.write(path, total)

    build.plan, build.job, build.folder, build.unique = plan, job, folder, unique
    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    p3d, penc = B.split_progress(progress, 0.85)
    B.render_frames("coffee_scene", build.job, build.unique, [B.SCRIPTS / "bkit.py", Path(C.__file__)], progress=p3d)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, penc, module=__name__,
                      build_kw={"seed": seed}, size=(B.OUT_W, B.OUT_H), max_workers=12)
