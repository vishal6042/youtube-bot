"""All the water on Earth, gathered into one ball.

Science in Motion, episode 2. A real Earth (NASA imagery and ocean depths),
seen in 3D:

- hook: the finished picture. The oceans are gone, the seabed is bare, and all
  of Earth's water sits in one ball beside India, with two smaller balls next
  to it. The claim is spoken over it;
- rewind: the water runs back, the ball shrinks to nothing, clouds return: the
  blue planet as it looks from space;
- drain: sea level falls (continental shelves first, the trenches last) while
  the water gathers into a ball that grows by exactly the volume drained;
- the liquid fresh water buds off into a second ball, and the lakes and rivers
  into a third;
- payoff: back out to the whole planet, three drops against it.

Honest numbers (USGS Water Science School, "How Much Water is There on Earth?",
H. Perlman, USGS; data: I. Shiklomanov 1993). Sphere diameters: all water on,
in and above Earth 1,385 km (1.386 billion km3: oceans, ice, groundwater,
lakes, rivers, the air); liquid fresh water 272.8 km (10.6 million km3, about
99% of it groundwater); fresh water in lakes and rivers 56.2 km (93,113 km3),
the source of most of the water people and other life use every day. The balls
are drawn to scale with the Earth (12,742 km). The land is left as it is: the
ice caps are counted in the big ball but not melted in the picture.

The picture is ray-traced on the GPU when CuPy can reach one (see ocean_depth):
Earth is a textured, lit sphere with an atmosphere and clouds; each ball
refracts the ground behind it, reflects the sun and throws a shadow with a
bright caustic in its middle. Everything is drawn at OUT_W x OUT_H
(1440 x 2560 by default; EARTH_WATER_SIZE=2160x3840 for 4K), text included.

Imagery: NASA Earth Observatory, Blue Marble Next Generation (July) with ocean
depths and land heights from GEBCO (assets/earth/, see CREDITS.md there).
Clouds: Solar System Scope (CC BY 4.0).
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

import cairo
import numpy as np
from PIL import Image

from . import kit
from . import sound as snd
from . import voice
from .canvas import GOLD, MUTED, WHITE
from .ocean_depth import GPU, GPU_WORKERS, _noise, _release, mapc, rumble, smooth, smoother, text_sprite, to_np, whoosh, xp

FPS = 60
VOICE, RATE = "en-US-AndrewNeural", "+8%"

OUT_W, OUT_H = (int(v) for v in os.environ.get("EARTH_WATER_SIZE", "1440x2560").split("x"))
K = OUT_W / 1080.0                    # every pixel size below is given for a 1080-wide frame and scaled by this
SS = float(os.environ.get("EARTH_WATER_SS", "1.5"))     # supersampling of the 3D layer

R_KM = 6371.0
EARTH_DIR = Path(__file__).resolve().parents[2] / "assets" / "earth"
CACHE = EARTH_DIR / "cache"
SRC = dict(rgb="world.topo.bathy.200407.3x21600x10800.jpg", bath="gebco_08_rev_bath_21600x10800.jpg",
           elev="gebco_08_rev_elev_21600x10800.jpg")
CLOUDS = Path(__file__).resolve().parents[2] / "assets" / "space" / "2k_earth_clouds.jpg"
PATCH = (30.0, 110.0, -25.0, 45.0)    # lon0, lon1, lat0, lat1 kept at the source's full 2 km per pixel
MAX_DEPTH = 8.0                       # km: the depth image's range
FLAT = 150.0                          # the baked relief shade of flat ground

# the three balls: (key, diameter km, latitude, longitude, label title, label value)
BALLS = [
    ("all", 1385.0, 16.0, 63.0, "ALL THE WATER ON EARTH", "1,385 km wide"),
    ("fresh", 272.8, 8.2, 70.2, "LIQUID FRESH WATER", "273 km"),
    ("lakes", 56.2, 5.2, 73.6, "LAKES AND RIVERS", "56 km"),
]

HOOK = [[("All", WHITE), ("the", WHITE), ("water", WHITE), ("on", WHITE), ("Earth", WHITE)],
        [("fits", WHITE), ("in", WHITE), ("this", GOLD), ("one", GOLD), ("ball.", GOLD)]]
HOOK_YS = (190, 272)
HOOK_T0 = -0.45
CAP_Y = 372

SCRIPT = {
    "hook": ("All the water on Earth fits inside this one ball.", None),
    "world": ("From space, Earth looks like a water world.", [("From space, Earth looks", 4), ("like a water world.", 4)]),
    "drain": ("But drain every ocean, and gather it all up:", [("But drain every ocean,", 4), ("and gather it all up:", 5)]),
    "all": ("one ball, 1,385 kilometres wide.", [("one ball,", 2), ("*1,385 kilometres* wide", 3)]),
    "fresh": ("All the liquid fresh water, most of it underground: 273.",
              [("All the liquid fresh water,", 5), ("most of it underground:", 4), ("*273 km*", 1)]),
    "lakes": ("And every lake and river: just 56.", [("And every lake and river:", 5), ("just *56 km*", 2)]),
    "payoff": ("Most of the water we use every day comes from that last tiny drop.",
               [("Most of the water", 4), ("we use every day", 4), ("comes from that", 3), ("*last tiny drop*", 3)]),
}


# --------------------------------------------------------------------------- #
# Textures: a pyramid of the whole Earth and a full-resolution patch round India
# --------------------------------------------------------------------------- #
def prepare() -> None:
    """Build the texture cache from the three NASA images (once; about a minute)."""
    if all((CACHE / f).exists() for f in ("g0.npy", "g1.npy", "g2.npy", "g3.npy", "patch.npy", "hypso.npy")):
        return
    Image.MAX_IMAGE_PIXELS = None
    CACHE.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(EARTH_DIR / SRC["rgb"]).convert("RGB"))
    dep = np.asarray(Image.open(EARTH_DIR / SRC["bath"]).convert("L"))          # 255 = surface, 0 = 8 km down
    elv = np.asarray(Image.open(EARTH_DIR / SRC["elev"]).convert("L"))          # 0 = sea level, 255 = 6.4 km up
    h, w = dep.shape
    # relief shade, baked for a sun in the north-west: n . l with slopes exaggerated
    lx, ly, lz = np.array([-0.55, 0.45, 0.70]) / np.linalg.norm([-0.55, 0.45, 0.70])
    shd = np.empty((h, w), np.uint8)
    dy_km = 20037.5 / h
    for y0 in range(0, h, 900):
        y1 = min(h, y0 + 900)
        a, b = max(0, y0 - 1), min(h, y1 + 1)
        hk = elv[a:b].astype(np.float32) * (6.4 / 255) - (255 - dep[a:b].astype(np.float32)) * (MAX_DEPTH / 255)
        gy = np.gradient(hk, axis=0)[y0 - a:y1 - a] / -dy_km                     # northward slope
        hk = hk[y0 - a:y1 - a]
        lat = 90 - (np.arange(y0, y1) + 0.5) / h * 180
        dx_km = (40075.0 / w) * np.maximum(0.06, np.cos(np.radians(lat)))[:, None]
        gx = (np.roll(hk, -1, 1) - np.roll(hk, 1, 1)) / (2 * dx_km)              # eastward slope
        ex = np.where(hk < 0, 9.0, 3.5)                                          # the seabed is gentler than the land
        nx, ny = -gx * ex, -gy * ex
        s = (nx * lx + ny * ly + lz) / np.sqrt(nx * nx + ny * ny + 1) / lz
        shd[y0:y1] = np.clip(s * FLAT, 0, 255).astype(np.uint8)

    def pack(c, d, s_):
        out = np.empty((5, c.shape[0], c.shape[1] + 1), np.uint8)               # one extra column: longitude wraps
        out[0:3, :, :-1] = np.moveaxis(c, 2, 0)
        out[3, :, :-1], out[4, :, :-1] = d, s_
        out[:, :, -1] = out[:, :, 0]
        return out
    lon0, lon1, lat0, lat1 = PATCH
    x0, x1 = int((lon0 + 180) / 360 * w), int((lon1 + 180) / 360 * w)
    y0, y1 = int((90 - lat1) / 180 * h), int((90 - lat0) / 180 * h)
    np.save(CACHE / "patch.npy", pack(rgb[y0:y1, x0:x1], dep[y0:y1, x0:x1], shd[y0:y1, x0:x1])[:, :, :-1])
    ims = [Image.fromarray(rgb), Image.fromarray(dep), Image.fromarray(shd)]
    for lvl in range(4):
        ims = [im.reduce(2) for im in ims]
        np.save(CACHE / f"g{lvl}.npy", pack(*(np.asarray(im) for im in ims)))
    # how much of the ocean's volume has drained when sea level has fallen by d km
    d3 = (255 - np.asarray(ims[1], np.float32)) * (MAX_DEPTH / 255)
    wgt = np.cos(np.radians(90 - (np.arange(d3.shape[0]) + 0.5) / d3.shape[0] * 180))[:, None]
    lv = np.linspace(0, MAX_DEPTH, 161)
    vol = np.array([(np.minimum(d3, x) * wgt).sum() for x in lv])
    np.save(CACHE / "hypso.npy", np.stack([lv, vol / vol[-1]]))


@lru_cache(maxsize=1)
def textures():
    prepare()
    lv = [xp.asarray(np.load(CACHE / f"g{i}.npy")) for i in range(4)]
    cl = np.asarray(Image.open(CLOUDS).convert("L"))
    cl = np.concatenate([cl, cl[:, :1]], 1)
    return dict(levels=lv, patch=xp.asarray(np.load(CACHE / "patch.npy")), clouds=xp.asarray(cl),
                hypso=np.load(CACHE / "hypso.npy"))


def drained(level_km: float) -> float:
    """Fraction of the ocean's volume gone when the sea has fallen by level_km."""
    hy = textures()["hypso"]
    return float(np.interp(level_km, hy[0], hy[1]))


def _lookup(tex, x, y):
    """Bilinear lookup of a (C, H, W) uint8 texture at float pixel positions -> (n, C) float32."""
    co = xp.stack([y, x])
    return xp.stack([mapc(tex[c], co, order=1, mode="nearest", output=xp.float32) for c in range(tex.shape[0])], -1)


def sample_earth(lon, lat, lod: float, wp: float):
    """Colour, depth and relief shade at (lon, lat) degrees: (n, 5) float32.
    lod: 0..3, which level of the pyramid (blended); wp: 0..1, how much the
    full-resolution patch round India takes over where it reaches."""
    T = textures()
    l0 = int(math.floor(lod))
    l1 = min(3, l0 + 1)
    f = lod - l0

    def level(i):
        tex = T["levels"][i]
        hh, ww = tex.shape[1], tex.shape[2] - 1
        return _lookup(tex, ((lon + 180.0) / 360.0 * ww - 0.5) % ww, xp.clip((90.0 - lat) / 180.0 * hh - 0.5, 0, hh - 1))
    out = level(l0)
    if f > 1e-3 and l1 != l0:
        out = out * (1 - f) + level(l1) * f
    if wp > 1e-3:
        lon0, lon1, lat0, lat1 = PATCH
        inside = xp.clip(xp.minimum(xp.minimum(lon - lon0, lon1 - lon), xp.minimum(lat - lat0, lat1 - lat)) / 3.0, 0, 1) * wp
        m = inside > 1e-3
        if bool(m.any()):
            tex = T["patch"]
            hh, ww = tex.shape[1], tex.shape[2]
            px = _lookup(tex, xp.clip((lon[m] - lon0) / (lon1 - lon0) * ww - 0.5, 0, ww - 1),
                         xp.clip((lat1 - lat[m]) / (lat1 - lat0) * hh - 0.5, 0, hh - 1))
            a = inside[m][:, None]
            out[m] = out[m] * (1 - a) + px * a
    return out


# --------------------------------------------------------------------------- #
# The world: unit sphere, x towards (0 N, 0 E), y towards 90 E, z north
# --------------------------------------------------------------------------- #
def unit(lat_deg: float, lon_deg: float) -> np.ndarray:
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


SUN = unit(24.0, 22.0)                               # afternoon over India: light from the west-north-west
SUN_X = xp.asarray(SUN, xp.float32)
BALL_UP = [unit(la, lo) for _, _, la, lo, _, _ in BALLS]
BALL_R = [d / 2 / R_KM for _, d, *_ in BALLS]


class Cam:
    """Looks at a point on the ground from `dist` Earth radii away, `el` degrees
    above its horizon, facing compass heading `az`."""

    def __init__(self, lat, lon, dist, el, az, fov, shift=0.0):
        s = unit(lat, lon)
        north = np.array([0.0, 0.0, 1.0]) - s * s[2]
        north /= np.linalg.norm(north)
        east = np.cross(north, s)
        a, e = math.radians(az), math.radians(el)
        head = math.cos(a) * north + math.sin(a) * east
        self.pos = s + dist * (math.sin(e) * s - math.cos(e) * head)
        self.f = s - self.pos
        self.dist = float(np.linalg.norm(self.f))
        self.f /= self.dist
        up = head - self.f * (head @ self.f)
        self.u = up / np.linalg.norm(up)
        self.r = np.cross(self.f, self.u)
        self.t = math.tan(math.radians(fov) / 2)
        self.shift = shift                           # picture moved down by this fraction of its height

    def rays(self, w: int, h: int, y0: int, y1: int):
        f, r, u = (xp.asarray(v, xp.float32) for v in (self.f, self.r, self.u))
        sx = ((xp.arange(w, dtype=xp.float32) + 0.5) / w * 2 - 1) * (self.t * w / h)
        sy = (1 - (xp.arange(y0, y1, dtype=xp.float32) + 0.5) / h * 2 + 2 * self.shift) * self.t
        X, Y = xp.meshgrid(sx, sy)
        d = (f[None, None] + X[..., None] * r[None, None] + Y[..., None] * u[None, None]).reshape(-1, 3)
        return d / xp.linalg.norm(d, axis=1, keepdims=True)

    def project(self, P):
        """World points -> x, y in output pixels, and depth along the view."""
        P = np.atleast_2d(np.asarray(P, np.float64)) - self.pos
        z = P @ self.f
        zs = np.where(z > 1e-6, z, 1e-6)
        x = (P @ self.r) / (zs * self.t * OUT_W / OUT_H)
        y = (P @ self.u) / (zs * self.t) - 2 * self.shift
        return (x + 1) / 2 * OUT_W, (1 - y) / 2 * OUT_H, z


def _sky(o, d):
    """Rays that miss the planet: black space, and the thin blue line of air on the limb."""
    tca = -(d @ o)
    b = xp.sqrt(xp.maximum((o * o).sum() - tca * tca, 0.0))
    hgt = xp.maximum(b - 1.0, 0.0)
    p = o + d * tca[:, None]
    day = xp.clip((p @ SUN_X) / xp.maximum(b, 1e-6) * 2.2 + 0.35, 0, 1)
    glow = (xp.exp(-hgt / 0.0085) * 0.95 + xp.exp(-hgt / 0.035) * 0.16) * day * (tca > 0)
    return glow[:, None] * xp.asarray([96.0, 158.0, 255.0], xp.float32)


def earth_colour(P, d, st):
    """Colour of the ground at points P on the unit sphere, seen along d."""
    lat = xp.degrees(xp.arcsin(xp.clip(P[:, 2], -1, 1)))
    lon = xp.degrees(xp.arctan2(P[:, 1], P[:, 0]))
    tx = sample_earth(lon, lat, st["lod"], st["wp"])
    rgb, depth, shade = tx[:, :3], (255.0 - tx[:, 3]) * (MAX_DEPTH / 255.0), tx[:, 4] / FLAT
    lvl = st["level"]
    blue = xp.clip((rgb[:, 2] - 1.15 * rgb[:, 0]) / 22.0, 0, 1) * xp.clip((rgb[:, 2] - 0.92 * rgb[:, 1]) / 18.0, 0, 1)
    depth = xp.maximum(depth, 0.035 * blue)
    sea = xp.clip((depth - 0.006) / 0.02, 0, 1)                      # where there is (or was) water
    wd = depth - lvl                                                 # water still standing above this spot
    wet = xp.clip(wd / 0.02, 0, 1) * sea
    # the bare seabed: pale shelves, brown slopes, grey abyssal plains, dark trenches, with its real relief
    c = xp.asarray([[186, 158, 118], [134, 112, 88], [98, 86, 76], [58, 52, 50]], xp.float32)
    t1 = xp.clip(depth / 0.35, 0, 1)[:, None]
    t2 = xp.clip((depth - 0.35) / 3.4, 0, 1)[:, None]
    t3 = xp.clip((depth - 4.6) / 3.0, 0, 1)[:, None]
    rock = ((c[0] * (1 - t1) + c[1] * t1) * (1 - t2) + c[2] * t2) * (1 - t3) + c[3] * t3
    rock = rock * (shade ** 1.25)[:, None]
    # the water: NASA's own ocean colour at full sea level, then turquoise shallows and dark deeps as it falls
    k = xp.exp(-xp.clip(wd, 0, None) / 0.85)[:, None]
    water = xp.asarray([64, 176, 188], xp.float32) * k + xp.asarray([7, 30, 80], xp.float32) * (1 - k)
    own = math.exp(-lvl / 0.12)
    water = rgb * own + water * (1 - own)
    land = rgb * (shade ** 0.55)[:, None]
    seaf = sea[:, None]
    alb = (water * wet[:, None] + rock * (1 - wet[:, None])) * seaf + land * (1 - seaf)

    nd = P @ SUN_X
    lit = xp.clip(nd, 0, 1) ** 0.85
    # the balls' shadows, each with the bright caustic a ball of water focuses in its middle
    shadow = xp.ones_like(nd)
    caustic = xp.zeros_like(nd)
    for C, r in st["balls"]:
        if r < 1e-5:
            continue
        v = xp.asarray(C, xp.float32) - P
        along = v @ SUN_X
        perp = xp.sqrt(xp.maximum((v * v).sum(1) - along * along, 0.0))
        q = perp / r
        infront = along > 0
        shadow = shadow * (1 - 0.62 * xp.clip((1.03 - q) / 0.10, 0, 1) * infront)
        caustic = caustic + xp.exp(-(q / 0.30) ** 2) * 1.5 * infront
    col = alb * ((0.030 + 1.16 * lit * shadow)[:, None]) + alb * (caustic * lit)[:, None] * xp.asarray([0.75, 0.95, 1.1], xp.float32)
    # the sun's glint on open water
    refl = d - 2 * (d * P).sum(1)[:, None] * P
    col = col + (xp.clip(refl @ SUN_X, 0, 1) ** 70 * 150.0 * wet * shadow)[:, None] * xp.asarray([1.0, 0.94, 0.82], xp.float32)
    # clouds and their shadows, while there is still water to make them
    if st["cloud"] > 1e-3:
        cl = textures()["clouds"]
        hh, ww = cl.shape[0], cl.shape[1] - 1

        def cover(lo, la):
            x = ((lo + 180.0 + st["drift"]) / 360.0 * ww - 0.5) % ww
            y = xp.clip((90.0 - la) / 180.0 * hh - 0.5, 0, hh - 1)
            return (mapc(cl, xp.stack([y, x]), order=1, mode="nearest", output=xp.float32) / 255.0) ** 1.25
        a = xp.clip(cover(lon, lat) * 1.15 * st["cloud"], 0, 1)[:, None]
        sh = xp.clip(cover(lon - 0.55, lat + 0.35) * st["cloud"], 0, 1)[:, None]
        col = col * (1 - 0.42 * sh * (1 - a))
        col = col * (1 - a) + xp.asarray([250, 252, 255], xp.float32) * ((0.05 + 1.08 * lit * shadow)[:, None]) * a
    # air: the ground hazes towards the limb, and the night side falls away
    graze = (1 - xp.clip(-(d * P).sum(1), 0, 1)) ** 2.8
    haze = (graze * (0.25 + 0.75 * xp.clip(nd * 2.0 + 0.3, 0, 1)))[:, None]
    return col * (1 - 0.72 * haze) + xp.asarray([104, 164, 255], xp.float32) * haze * 0.95


def shade(o, d, st):
    """Colour along each ray: space, the planet, and the balls of water."""
    n = len(d)
    b = d @ o
    disc = b * b - ((o * o).sum() - 1.0)
    te = xp.where(disc > 0, -b - xp.sqrt(xp.maximum(disc, 0)), xp.inf)
    te = xp.where(te > 0, te, xp.inf)
    tb = xp.full(n, xp.inf, xp.float32)
    ib = xp.full(n, -1, xp.int32)
    for i, (C, r) in enumerate(st["balls"]):
        if r < 1e-5:
            continue
        oc = o - xp.asarray(C, xp.float32)
        b2 = d @ oc
        d2 = b2 * b2 - ((oc * oc).sum() - r * r)
        t = xp.where(d2 > 0, -b2 - xp.sqrt(xp.maximum(d2, 0)), xp.inf)
        nearer = (t > 0) & (t < tb) & (t < te)
        tb = xp.where(nearer, t, tb)
        ib = xp.where(nearer, i, ib)
    col = _sky(o, d)
    ground = xp.isfinite(te) & (ib < 0)
    if bool(ground.any()):
        col[ground] = earth_colour(o + d[ground] * te[ground][:, None], d[ground], st)
    for i, (C, r) in enumerate(st["balls"]):
        m = ib == i
        if not bool(m.any()):
            continue
        Cx = xp.asarray(C, xp.float32)
        dm = d[m]
        p1 = o + dm * tb[m][:, None]
        n1 = (p1 - Cx) / r
        ci = xp.clip(-(dm * n1).sum(1), 0, 1)
        eta = 1.0 / 1.333
        kk = xp.sqrt(xp.maximum(1 - eta * eta * (1 - ci * ci), 0.0))               # cos of the angle inside
        t1 = eta * dm + (eta * ci - kk)[:, None] * n1                               # the ray inside the water
        chord = 2 * r * kk
        p2 = p1 + t1 * chord[:, None]
        n2 = (p2 - Cx) / r
        c2 = xp.clip((t1 * n2).sum(1), 0, 1)
        d2 = 1.333 * t1 - (1.333 * c2 - ci)[:, None] * n2                            # and out the far side
        d2 = d2 / xp.linalg.norm(d2, axis=1, keepdims=True)
        # what lies behind, seen through the ball
        bb = (d2 * p2).sum(1)
        ds = bb * bb - ((p2 * p2).sum(1) - 1.0)
        t2 = xp.where(ds > 0, -bb - xp.sqrt(xp.maximum(ds, 0)), xp.inf)
        hit = xp.isfinite(t2) & (t2 > 0)
        behind = xp.zeros((len(dm), 3), xp.float32)
        if bool(hit.any()):
            behind[hit] = earth_colour(p2[hit] + d2[hit] * t2[hit][:, None], d2[hit], st)
        if bool((~hit).any()):
            behind[~hit] = _sky_from(p2[~hit], d2[~hit])
        # water takes the red out first: clear at the rim, deep blue through the middle
        path = (chord / (2 * r))[:, None]
        tr = xp.exp(-path * xp.asarray([2.1, 0.62, 0.22], xp.float32))
        sunward = (0.30 + 0.70 * xp.clip(n1 @ SUN_X * 0.5 + 0.5, 0, 1))[:, None]
        body = behind * tr * 1.15 + xp.asarray([16, 98, 178], xp.float32) * (1 - tr.mean(1, keepdims=True)) * sunward * 0.82
        # the surface: it mirrors more towards its edge, and catches the sun
        fres = (0.02 + 0.98 * (1 - ci) ** 5)[:, None]
        rf = dm + 2 * ci[:, None] * n1
        up = xp.asarray(C / np.linalg.norm(C), xp.float32)
        env = xp.asarray([70, 122, 205], xp.float32) * xp.clip(0.55 - 0.75 * (rf @ up), 0, 1)[:, None] \
            + xp.asarray([14, 30, 64], xp.float32) * xp.clip(rf @ up, 0, 1)[:, None]
        rs = xp.clip(rf @ SUN_X, 0, 1)
        spec = (rs ** 900 * 2400.0 + rs ** 60 * 34.0)[:, None] * xp.asarray([1.0, 0.97, 0.90], xp.float32)
        col[m] = body * (1 - fres) + env * fres + spec
    return col


def _sky_from(p, d):
    """_sky for rays that start at different points (those leaving a ball)."""
    tca = -(d * p).sum(1)
    b = xp.sqrt(xp.maximum((p * p).sum(1) - tca * tca, 0.0))
    hgt = xp.maximum(b - 1.0, 0.0)
    q = p + d * tca[:, None]
    day = xp.clip((q @ SUN_X) / xp.maximum(b, 1e-6) * 2.2 + 0.35, 0, 1)
    glow = (xp.exp(-hgt / 0.0085) * 0.95 + xp.exp(-hgt / 0.035) * 0.16) * day * (tca > 0)
    return glow[:, None] * xp.asarray([96.0, 158.0, 255.0], xp.float32)


def picture(cam: Cam, st: dict, ss: float = SS) -> np.ndarray:
    """The 3D picture as float32 (OUT_H, OUT_W, 3), 0..255."""
    w, h = int(round(OUT_W * ss)), int(round(OUT_H * ss))
    km_px = cam.dist * R_KM * 2 * cam.t / h                           # ground covered by one rendered pixel
    st = {**st, "lod": float(np.clip(math.log2(max(km_px, 1e-3) / 3.71), 0, 3)),
          "wp": float(np.clip((7.0 - km_px) / 3.0, 0, 1))}
    o = xp.asarray(cam.pos, xp.float32)
    out = xp.empty((h, w, 3), xp.uint8)
    rows = max(32, int(1.4e6 // w))
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        out[y0:y1] = xp.clip(shade(o, cam.rays(w, h, y0, y1), st), 0, 255).astype(xp.uint8).reshape(y1 - y0, w, 3)
    im = Image.fromarray(to_np(out))
    _release()
    if (w, h) != (OUT_W, OUT_H):
        im = im.resize((OUT_W, OUT_H), Image.LANCZOS)
    return np.asarray(im, np.float32)


# --------------------------------------------------------------------------- #
# Text and compositing at the output size
# --------------------------------------------------------------------------- #
_DITHER = (np.random.default_rng(99).random((OUT_H, OUT_W, 1), np.float32) - 0.5) * 1.6


def grade(arr: np.ndarray, sharp: float = 0.5) -> np.ndarray:
    """An unsharp mask for crisp detail, then a little more contrast with deeper blacks."""
    from scipy.ndimage import gaussian_filter

    out = arr + sharp * (arr - gaussian_filter(arr, (1.3 * K, 1.3 * K, 0)))
    return np.clip(52.0 + (out - 52.0) * 1.10, 0, 255)


def to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr + _DITHER, 0, 255).astype(np.uint8))


def blit(img: Image.Image, rgba: Image.Image, x: float, y: float, alpha: float = 1.0) -> None:
    """Paste an RGBA sprite with its top-left at float (x, y): text never snaps to whole pixels."""
    if alpha <= 0.004:
        return
    tw, th = rgba.size[0] + 2, rgba.size[1] + 2
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    x0, y0 = max(0, ix), max(0, iy)
    x1, y1 = min(img.size[0], ix + tw), min(img.size[1], iy + th)
    if x1 <= x0 or y1 <= y0:
        return
    t = rgba.transform((tw, th), Image.AFFINE, (1, 0, -fx, 0, 1, -fy), resample=Image.BICUBIC)
    a = np.asarray(t, np.float32)[y0 - iy:y1 - iy, x0 - ix:x1 - ix]
    m = a[..., 3:4] / 255 * alpha
    reg = np.asarray(img.crop((x0, y0, x1, y1)), np.float32)
    img.paste(Image.fromarray(np.clip(reg * (1 - m) + a[..., :3] * m, 0, 255).astype(np.uint8)), (x0, y0))


def px(v: float) -> int:
    return int(round(v * K))


def row_sprite(parts, font) -> Image.Image:
    """One line of text in several colours, with a soft shadow. parts: [(text, colour)]."""
    from PIL import ImageDraw, ImageFilter

    pad = px(22)
    widths = [font.getlength(t) for t, _ in parts]
    wd, hd = int(sum(widths)) + pad * 2, int(font.size * 1.3) + pad * 2
    mask = Image.new("L", (wd, hd), 0)
    colr = Image.new("RGB", (wd, hd), (0, 0, 0))
    dm, dc = ImageDraw.Draw(mask), ImageDraw.Draw(colr)
    x = float(pad)
    for (t, c), w_ in zip(parts, widths):
        dm.text((x, hd / 2), t, font=font, fill=255, anchor="lm")
        dc.rectangle((x - 1, 0, x + w_ + 1, hd), fill=tuple(int(v) for v in c))
        x += w_
    m = np.asarray(mask, np.float32) / 255
    sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(px(6))), np.float32) / 255
    sh = np.clip(np.roll(sh, px(3), axis=0) * 1.6, 0, 1) * 0.85
    a = m + sh * (1 - m)
    rgb = np.asarray(colr, np.float32) * (m / np.maximum(a, 1e-4))[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8), "RGBA")


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
#        look at (lat, lon)  distance  elevation  heading  field of view
HERO = (13.4, 70.2, 2.08, 50.0, 6.0, 34.0)        # the big ball beside India, the horizon above them
CLOSE = (7.2, 72.4, 0.86, 42.0, 6.0, 34.0)        # down among the two small ones, off India's tip
WIDE = (16.0, 72.0, 5.5, 90.0, 0.0, 34.0)         # the whole planet, India in the middle
SHIFT = (-0.075, 0.035, 0.05)                       # how far each view sits below the frame's centre (room for text)


def _mix(a, b, u):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


class Plan:
    def __init__(self, L: dict):
        self.L = L
        g = 0.22
        self.at = {"hook": 0.15}
        self.rew = self.at["hook"] + L["hook"].secs + 0.25           # the finished picture is let go
        self.at["world"] = self.rew + 1.05
        self.at["drain"] = self.at["world"] + L["world"].secs + g
        self.at["all"] = self.at["drain"] + L["drain"].secs + 0.12
        self.at["fresh"] = self.at["all"] + L["all"].secs + g + 0.25
        self.at["lakes"] = self.at["fresh"] + L["fresh"].secs + g
        self.at["payoff"] = self.at["lakes"] + L["lakes"].secs + g + 0.2
        self.total = self.at["payoff"] + L["payoff"].secs + 1.45
        # the drain runs through its own line and ends as the size is spoken
        self.d0 = self.at["drain"] + 0.15
        self.d1 = self.at["all"] + self._num(L["all"]) + 0.1
        self.fresh_on = self.at["fresh"] + self._num(L["fresh"]) - 0.55
        self.lakes_on = self.at["lakes"] + self._num(L["lakes"]) - 0.55
        self.out0 = self.at["payoff"] + 0.1                          # the pull back to the whole planet
        self.out1 = self.out0 + 2.6

    @staticmethod
    def _num(line) -> float:
        for c in line.words:
            if any(ch.isdigit() for ch in c["text"]):
                return float(c["start"])
        return line.secs * 0.6

    def level(self, t: float) -> float:
        """How far the sea has fallen, km."""
        if t < self.rew:
            return MAX_DEPTH
        if t < self.rew + 1.25:
            return MAX_DEPTH * (1 - smoother((t - self.rew) / 1.25))
        if t < self.d0:
            return 0.0
        return MAX_DEPTH * smooth((t - self.d0) / (self.d1 - self.d0)) ** 1.15

    def clouds(self, t: float) -> float:
        if t < self.rew + 0.5:
            return 0.0
        if t < self.d0:
            return smooth((t - self.rew - 0.5) / 0.9)
        return 1 - smooth((t - self.d0) / ((self.d1 - self.d0) * 0.55))

    def grown(self, t: float) -> tuple[float, float, float]:
        """Each ball's size, 0..1 of its final radius."""
        big = drained(self.level(t)) ** (1 / 3)
        if t < self.rew + 1.25:                                       # the rewind: the small ones go first
            u = 1 - smoother((t - self.rew) / 0.5) if t > self.rew else 1.0
            return big, u, u
        return big, smooth((t - self.fresh_on) / 0.7), smooth((t - self.lakes_on) / 0.7)

    def cam(self, t: float) -> Cam:
        if t < self.rew:
            k, s = _mix(HERO, _mix(HERO, CLOSE, 0.10), t / self.rew), SHIFT[0]
        elif t < self.d0:
            u = smoother((t - self.rew) / 1.5)
            k, s = _mix(_mix(HERO, CLOSE, 0.10), WIDE, u), SHIFT[0] + (SHIFT[2] - SHIFT[0]) * u
            k = (k[0], k[1] - 5.0 * smooth((t - self.rew - 1.2) / (self.d0 - self.rew - 1.2)), *k[2:])   # the planet turns a little
        elif t < self.at["lakes"]:
            u = smoother((t - self.d0) / (self.d1 - self.d0 + 0.5))
            w = (WIDE[0], WIDE[1] - 5.0, *WIDE[2:])
            push = 0.06 * smooth((t - self.d1) / (self.at["lakes"] - self.d1))
            k, s = _mix(_mix(w, HERO, u), CLOSE, push), SHIFT[2] + (SHIFT[0] - SHIFT[2]) * u
        elif t < self.out0:
            u = smoother((t - self.at["lakes"]) / 1.6)
            k, s = _mix(_mix(HERO, CLOSE, 0.06), CLOSE, u), SHIFT[0] + (SHIFT[1] - SHIFT[0]) * u
        else:
            u = smoother((t - self.out0) / (self.out1 - self.out0))
            end = (WIDE[0], WIDE[1] + 2.5 * smooth((t - self.out1) / 4.0), *WIDE[2:])
            k, s = _mix(CLOSE, end, u), SHIFT[1] + (SHIFT[2] - SHIFT[1]) * u
        return Cam(*k, shift=s)

    def balls(self, t: float):
        """(centre, radius) of each ball now. The small ones bud off the side of the next one up."""
        g = self.grown(t)
        out = []
        for i, (up, r) in enumerate(zip(BALL_UP, BALL_R)):
            rr = r * g[i]
            home = up * (1.0 + rr)
            if i > 0 and 0 < g[i] < 1:                                # sliding out from its parent to its own place
                par = BALL_UP[i - 1] * (1.0 + BALL_R[i - 1])
                toward = home - par
                start = par + toward / np.linalg.norm(toward) * BALL_R[i - 1] * 0.92
                start = start / np.linalg.norm(start) * (1.0 + rr)
                u = smoother(g[i])
                c = start * (1 - u) + home * u
                home = c / np.linalg.norm(c) * (1.0 + rr)
            out.append((home, rr))
        return out


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    textures()
    keys = ["world", "drain", "all", "fresh", "lakes", "payoff"]
    clips = [(plan.at[k], lines[k]) for k in ["hook"] + keys]
    caps = []
    for k in keys:
        caps += kit.captions(plan.at[k], lines[k], SCRIPT[k][1])
    f_cap, f_tag, f_num = kit.sans(px(48), "bold"), kit.sans(px(28), "bold"), kit.sans(px(46), "black")
    f_hook = kit.serif(px(68))
    cap_sprites = {txt: row_sprite(kit.caption_parts(txt, 1.0), f_cap) for _, _, txt, _ in caps}
    tags = {key: text_sprite([(title, WHITE, f_tag), (val, GOLD, f_num)], align="left") for key, _, _, _, title, val in BALLS}
    hook_words = []
    kk = 0
    for line, y in zip(HOOK, HOOK_YS):
        words = [(w + (" " if i < len(line) - 1 else ""), c) for i, (w, c) in enumerate(line)]
        widths = [f_hook.getlength(w) for w, _ in words]
        x = OUT_W / 2 - sum(widths) / 2
        for (w, c), wd in zip(words, widths):
            spr = row_sprite([(w, c)], f_hook)
            hook_words.append((spr, x - px(22), y * K - spr.size[1] / 2, kk))
            x += wd
            kk += 1
    hook_gone = plan.rew + 0.4
    rng = np.random.default_rng(seed)
    star_dir = rng.normal(0, 1, (900, 3))
    star_dir /= np.linalg.norm(star_dir, axis=1, keepdims=True)
    star_mag = rng.random(900) ** 3

    def stars(arr: np.ndarray, cam: Cam) -> None:
        """A few faint stars behind the planet (splatted at sub-pixel positions: no twinkle)."""
        x, y, z = cam.project(cam.pos + star_dir * 50.0)
        tca = -(star_dir @ cam.pos)
        clear = ((cam.pos @ cam.pos) - tca * tca > 1.06 ** 2) | (tca < 0)
        ok = (z > 0) & clear & (x > 2) & (x < OUT_W - 3) & (y > 2) & (y < OUT_H - 3)
        for xi, yi, m in zip(x[ok], y[ok], star_mag[ok]):
            ix, iy = int(xi), int(yi)
            fx, fy = xi - ix, yi - iy
            v = (60 + 190 * m) * K
            for dy, wy in ((0, 1 - fy), (1, fy)):
                for dx, wx in ((0, 1 - fx), (1, fx)):
                    arr[iy + dy, ix + dx] += v * wy * wx

    def labels(img: Image.Image, cam: Cam, t: float, balls) -> None:
        shown = {"all": smooth((t - plan.d1 + 0.25) / 0.5) if t >= plan.d0 else (1 - smooth((t - plan.rew) / 0.3)),
                 "fresh": smooth((t - plan.fresh_on - 0.45) / 0.5) if t >= plan.d0 else 0.0,
                 "lakes": smooth((t - plan.lakes_on - 0.45) / 0.5) if t >= plan.d0 else 0.0}
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, OUT_W, OUT_H)
        ctx = cairo.Context(surf)
        ctx.set_antialias(cairo.ANTIALIAS_BEST)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        todo = []
        g = [c / 255 for c in GOLD]
        for (key, *_), (C, r) in zip(BALLS, balls):
            a = shown[key]
            if a <= 0.01 or r <= 1e-5:
                continue
            x, y, z = cam.project([C])
            if z[0] <= 0:
                continue
            rp = r / (z[0] * cam.t) * OUT_H / 2                           # the ball's radius on screen
            tag = tags[key]
            # the label sits up and to the right of its ball, joined to it by a thin leader
            ax, ay = x[0] + rp * 0.72, y[0] - rp * 0.72
            a *= smooth((ax - px(12)) / px(70)) * smooth((OUT_W - px(12) - ax) / px(70))      # its ball has left the frame
            a *= smooth((x[0] + rp * 0.2) / px(90)) * smooth((y[0] + rp * 0.2) / px(90))
            if a <= 0.01:
                continue
            lx = min(OUT_W - px(34) - tag.size[0], ax + px(54) + rp * 0.10)
            ly = max(px(CAP_Y + 70), ay - px(86) - rp * 0.10)
            todo.append([tag, lx, ly, a, ax, ay])
        todo.sort(key=lambda q: q[2])
        for prev, cur in zip(todo, todo[1:]):                                 # push down any that would overlap
            cur[2] = max(cur[2], prev[2] + prev[0].size[1] - px(26))
        for tag, lx, ly, a, ax, ay in todo:
            ctx.set_source_rgba(0.97, 0.96, 0.93, 0.75 * a)
            ctx.set_line_width(px(2))
            ctx.move_to(ax, ay)
            ctx.line_to(lx + px(16), ly + tag.size[1] * 0.60)
            ctx.stroke()
            ctx.set_source_rgba(*g, a)
            ctx.arc(ax, ay, px(5), 0, 2 * math.pi)
            ctx.fill()
        surf.flush()
        buf = np.ndarray((OUT_H, OUT_W, 4), np.uint8, surf.get_data())
        al = buf[..., 3:4].astype(np.float32) / 255
        if al.max() > 0:
            base = np.asarray(img, np.float32)
            img.paste(Image.fromarray(np.clip(base * (1 - al) + buf[..., 2::-1], 0, 255).astype(np.uint8)))
        for tag, lx, ly, a, _, _ in todo:
            blit(img, tag, lx, ly, a)

    def frame(t: float) -> Image.Image:
        cam = plan.cam(t)
        balls = plan.balls(t)
        st = dict(level=plan.level(t), cloud=plan.clouds(t), drift=0.35 * t, balls=balls)
        arr = picture(cam, st)
        stars(arr, cam)
        img = to_image(grade(arr))
        labels(img, cam, t, balls)
        if t < hook_gone:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            for spr, x, y, k in hook_words:
                u = min(1.0, max(0.0, (t - HOOK_T0 - k * 0.075) / 0.42))
                u = 1 - (1 - u) ** 3
                if u > 0:
                    blit(img, spr, x, y + px(26) * (1 - u), u * ha)
        for c0, c1, txt, last in caps:
            if c0 <= t < c1 + (0.2 if last else 0):
                f = smooth((t - c0) / 0.1)
                if last:
                    f = min(f, smooth((c1 + 0.2 - t) / 0.2))
                spr = cap_sprites[txt]
                blit(img, spr, OUT_W / 2 - spr.size[0] / 2, CAP_Y * K - spr.size[1] / 2, f)
                break
        return img

    def sound(path: Path) -> None:
        m = snd.Mixer(total)
        t_ = np.arange(int(snd.SR * total)) / snd.SR
        pad = (np.sin(2 * np.pi * 55.0 * t_) + 0.5 * np.sin(2 * np.pi * 82.5 * t_ + 0.4) + 0.3 * np.sin(2 * np.pi * 110.3 * t_ + 1.1))
        pad = pad * np.clip(t_ / 2.0, 0, 1) * np.clip((total - t_) / 1.5, 0, 1) / 1.8
        m.add(0.0, pad.astype(np.float32), 0.24)
        m.add(0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7)], dur=3.4), 0.5)
        m.add(plan.rew - 0.05, whoosh(1.4, 180, 620, seed=3), 0.30)                       # the water runs back
        wash = _noise(plan.d1 - plan.d0 + 0.6, 17, 900)
        env = np.sin(np.pi * np.clip(np.arange(len(wash)) / len(wash), 0, 1)) ** 1.3
        m.add(plan.d0 - 0.1, (wash * env).astype(np.float32), 0.34)                        # the sea draining
        m.add(plan.d0, rumble(plan.d1 - plan.d0), 0.40)
        for when, note, gain in ((plan.d1, 0, 0.5), (plan.fresh_on + 0.5, 7, 0.4), (plan.lakes_on + 0.5, 12, 0.36)):
            m.add(when - 0.02, snd.pluck(snd.scale_freq(note), dur=1.8, bright=0.6), gain)  # each ball, a smaller note
        m.add(plan.d1 - 0.02, snd.thud(58, 0.6), 0.5)
        m.add(plan.out0, whoosh(plan.out1 - plan.out0, 130, 480, seed=41), 0.24)
        m.add(plan.out1 - 0.3, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7, 10)], dur=total - plan.out1 + 0.5), 0.6)
        voice.voice_over(m, clips, bed=0.7)
        m.write(path, total)

    build.plan = plan
    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress, module=__name__,
                      build_kw={"seed": seed}, max_workers=GPU_WORKERS if GPU else None, size=(OUT_W, OUT_H))
