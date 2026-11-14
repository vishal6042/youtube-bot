"""How deep is the ocean, really? A 3D dive to the bottom of the Mariana Trench.

Science in Motion, episode 1. One 3D world, one camera:

- hook: the open sea at dusk, cut open along one plane: the surface running to
  the horizon, the water column, the seabed in section, and Mount Everest
  standing in the trench with its peak still ~2 km under the surface; the
  question is spoken over it. No box: the sea runs on past the frame;
- rewind: Everest sinks away, the camera swoops down over the water and
  plunges through the surface;
- dive: a first-person descent (3D marine snow with parallax and motion blur,
  sunlight shafts that fade out, a lamp that takes over in the dark) past the
  deepest scuba dive, a beaked whale's record dive, the Titanic's depth and the
  deepest fish ever filmed, down the trench wall to its floor. The diver, the
  whale, the wreck and the fish are real 3D models, animated and rendered in
  Blender (scripts/make_ocean_models.py), played back as loops;
- payoff: the camera pulls back out to the cut and Everest rises from the
  trench floor, with about 2 km of water above its peak.

Honest numbers. Depths (m): sunlight zone ends at 200 (NOAA); deepest scuba
dive 332.35 (Ahmed Gabr, 2014, Guinness); deepest recorded mammal dive 2,992
(Cuvier's beaked whale, Schorr et al. 2014); Titanic wreck ~3,800 (3,810);
deepest fish filmed 8,336 (snailfish, Izu-Ogasawara Trench, 2022, announced
2023); Challenger Deep 10,935 (NOAA; surveys range 10,925-10,994). Everest
8,849 m (2020 China-Nepal survey), so its peak would sit 2,086 m under the
surface (2,145 m with the deepest survey): "about 2 km" either way.

Depth is to scale; horizontal distances, the trench's shape and the animals'
sizes are illustrative (the markers sit in one column at their real depths).
"""
from __future__ import annotations

import math
import os
import warnings
from functools import lru_cache
from pathlib import Path

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import map_coordinates

from . import kit
from . import sound as snd
from . import voice
from .canvas import GOLD, MUTED, WHITE, H, W

# --------------------------------------------------------------------------- #
# Where the 3D is computed: on the graphics card if CuPy can reach one, else in
# NumPy on the CPU. The renderer below is written against `xp`, so both run the
# same code (OCEAN_GPU=0 forces the CPU). Text, sprites and particles stay on
# the CPU either way.
# --------------------------------------------------------------------------- #
GPU = False
GPU_WORKERS = int(os.environ.get("OCEAN_GPU_WORKERS", "8"))
xp = np
mapc = map_coordinates
if os.environ.get("OCEAN_GPU", "1") != "0":
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import cupy as _cp
            from cupyx.scipy.ndimage import map_coordinates as _cp_map
        if _cp.cuda.runtime.getDeviceCount() > 0:
            float(_cp.arange(4, dtype=_cp.float32).sum())      # touch the card and the compiler now, not mid-render
            xp, mapc, GPU = _cp, _cp_map, True
    except Exception:
        pass


def to_np(a) -> np.ndarray:
    """An array back on the CPU (a no-op without a GPU)."""
    return _cp.asnumpy(a) if GPU else np.asarray(a)


def _release() -> None:
    """Hand the frame's GPU memory back, so several workers can share one card."""
    if GPU:
        _cp.get_default_memory_pool().free_all_blocks()

FPS = 60
VOICE, RATE = "en-US-AndrewNeural", "+8%"     # English-only, as Space in Motion

# --------------------------------------------------------------------------- #
# The world (units: km; y = 0 is the sea surface, negative is down)
# --------------------------------------------------------------------------- #
# The sea is cut open along one plane (z = Z0) and looked at from in front; it
# runs on past the frame to both sides and back to the horizon, so there is no
# box to see. The detailed seabed covers GX x GZ; a coarse one carries on
# beyond it, into the haze.
GX, GZ = (-4.2, 4.2), (-3.6, 3.6)
Z0 = -3.4                     # the cut
X0, X1, Z1 = -4000.0, 4000.0, 4000.0
Y_BOT = -30.0
FAR_X, FAR_Z, FAR_N = (-44.0, 44.0), (-6.0, 82.0), 881      # the coarse seabed (0.1 km cells)
DEEP = 10.935                 # Challenger Deep, km
EVEREST = 8.849
PLAIN = -5.7                  # abyssal plain either side of the trench
EV_C = (0.0, 0.55)            # Everest's centre (x, z)
EV_R = 4.3                    # its base radius (illustrative)
GRID_N = (900, 760)           # heightfield samples (x, z)

# depth markers: key, depth (km), title, depth label
MARKERS = [
    ("sun", 0.200, "SUNLIGHT ENDS", "200 m"),
    ("scuba", 0.332, "DEEPEST SCUBA DIVE", "332 m"),
    ("midnight", 1.000, "THE MIDNIGHT ZONE", "1,000 m"),
    ("whale", 2.992, "BEAKED WHALE'S RECORD DIVE", "2,992 m"),
    ("titanic", 3.800, "TITANIC WRECK", "3,800 m"),
    ("fish", 8.336, "DEEPEST FISH EVER FILMED", "8,336 m"),
    ("bottom", DEEP, "CHALLENGER DEEP", "10,935 m"),
]
MD = {k: d for k, d, *_ in MARKERS}

HOOK = [[("Drop", WHITE), ("Everest", WHITE), ("into", WHITE)],
        [("the", WHITE), ("deepest", WHITE), ("ocean.", WHITE)],
        [("Its", WHITE), ("peak:", WHITE), ("2 km", GOLD), ("underwater.", GOLD)]]
HOOK_YS = (178, 256, 334)
HOOK_T0 = -0.45

SCRIPT = {
    "hook": ("Drop Everest into the deepest ocean, and its peak would still be 2 kilometres underwater.", None),
    "scuba": ("Deepest scuba dive: 332 metres.", [("Deepest scuba dive:", 3), ("*332 metres*", 2)]),
    "whale": ("A whale's deepest dive: almost 3,000.", [("A whale's deepest dive:", 4), ("almost *3,000*", 2)]),
    "titanic": ("The Titanic: 3,800.", [("The Titanic:", 2), ("*3,800*", 1)]),
    "fish": ("Deepest fish ever filmed: 8,336.", [("Deepest fish", 2), ("ever filmed:", 2), ("*8,336*", 1)]),
    "bottom": ("The bottom: almost 11 kilometres.", [("The bottom:", 2), ("almost *11 kilometres*", 3)]),
    "payoff": ("Everest fits, with 2 kilometres to spare.", [("Everest fits,", 2), ("with *2 kilometres*", 3),
                                                          ("to spare", 2)]),
}


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def smoother(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


# --------------------------------------------------------------------------- #
# Heightfields: the trench (T) and Everest's shape (S, 0..1), with gradients
# --------------------------------------------------------------------------- #
def _sines(x, z, terms):
    out = np.zeros_like(x)
    for a, fx, fz, ph in terms:
        out += a * np.sin(fx * x + fz * z + ph)
    return out


def _ridged(x, z, seed: int, octaves: int = 5, f0: float = 0.9):
    """Smooth ridged noise from rotated sine sums (deterministic, no grid)."""
    rng = np.random.default_rng(seed)
    out = np.zeros_like(x)
    amp, f = 1.0, f0
    for _ in range(octaves):
        th = rng.uniform(0, math.pi)
        u = x * math.cos(th) + z * math.sin(th)
        v = -x * math.sin(th) + z * math.cos(th)
        n = (np.sin(f * u + rng.uniform(0, 6.3)) * np.cos(f * 0.73 * v + rng.uniform(0, 6.3))
             + 0.5 * np.sin(f * 1.7 * v + 0.6 * np.sin(f * u)))
        out += amp * (1 - np.abs(n) / 1.5)
        amp *= 0.5
        f *= 2.03
    return out


def _ground(x, z):
    """Seabed height before smoothing: the abyssal plain with the trench cut into it."""
    plain = PLAIN + 0.22 * _sines(x, z, [(0.6, 0.9, 0.4, 0.3), (0.4, -0.5, 1.3, 1.1), (0.25, 2.1, 1.7, 2.2)]) \
        + 0.10 * _ridged(x, z, 3, 6, 1.8)
    # the trench runs front to back; its axis wanders a little, and it shallows away from its deepest point
    axis = 0.35 * np.sin(0.45 * z + 0.4)
    xr = x - axis
    floor = -DEEP + 0.16 * ((z - 0.0) / 3.4) ** 2 + 0.05 * (1 + _sines(x, z, [(1, 0.0, 2.3, 0.5)]))
    g = np.exp(-(np.abs(xr) / 1.55) ** 2.2)
    walls = 0.30 * _ridged(x * 1.4, z * 0.8, 5, 6, 1.4) * (1 - g) * g * 4
    return np.minimum(plain + (np.minimum(floor, plain) - plain) * g + walls, plain + 0.05)


@lru_cache(maxsize=1)
def fields():
    nx, nz = GRID_N
    xs = np.linspace(*GX, nx)
    zs = np.linspace(*GZ, nz)
    x, z = np.meshgrid(xs, zs, indexing="ij")
    T = _ground(x, z)
    # Everest: three main ridges (a pyramid), spurs between them, eroded detail
    dx, dz = x - EV_C[0], z - EV_C[1]
    r = np.hypot(dx, dz)
    th = np.arctan2(dz, dx)
    re = r * (1 + 0.22 * np.cos(3 * th + 0.5) + 0.07 * np.cos(7 * th + 1.7)) / EV_R
    base = np.clip(1 - re, 0, 1)
    rid = _ridged(x * 1.1, z * 1.1, 9, 5, 1.3)
    rid = (rid - rid.min()) / (rid.max() - rid.min())
    S = base ** 1.25 * (0.82 + 0.22 * rid) + 0.04 * rid * np.clip(base * 3, 0, 1)
    S = np.where(base > 0, S, 0.0)
    # no detail finer than a few grid cells: it would shimmer as the camera moves
    from scipy.ndimage import gaussian_filter
    S = gaussian_filter(S, 1.6)
    T = gaussian_filter(T, 1.0)
    S = S / S.max()
    # albedo variation: sediment patches, darker rock streaks
    A = 0.5 * _ridged(x * 2.2, z * 2.2, 13, 5, 1.0) + 0.5 * _sines(x, z, [(0.5, 3.3, 1.2, 0.2), (0.5, -1.7, 4.1, 1.0)])
    A = (A - A.mean()) / (A.std() + 1e-6)
    hx = xs[1] - xs[0]
    hz = zs[1] - zs[0]
    Tgx, Tgz = np.gradient(T, hx, hz)
    Sgx, Sgz = np.gradient(S, hx, hz)
    # the coarse seabed beyond the detailed one
    cx = np.linspace(*FAR_X, FAR_N)
    czs = np.linspace(*FAR_Z, FAR_N)
    Tc = gaussian_filter(_ground(*np.meshgrid(cx, czs, indexing="ij")), 0.7)
    chx, chz = cx[1] - cx[0], czs[1] - czs[0]
    Tcx, Tcz = np.gradient(Tc, chx, chz)
    out = dict(xs=xs, zs=zs, T=T.astype(np.float32), S=S.astype(np.float32), A=A.astype(np.float32),
               Tg=(Tgx.astype(np.float32), Tgz.astype(np.float32)),
               Sg=(Sgx.astype(np.float32), Sgz.astype(np.float32)), hx=hx, hz=hz,
               far0=(cx[0], czs[0]), farh=(chx, chz))
    # which coarse field stands in for each detailed one outside its area (none: zero)
    out["far"] = {id(out["T"]): Tc.astype(np.float32), id(out["Tg"][0]): Tcx.astype(np.float32),
                  id(out["Tg"][1]): Tcz.astype(np.float32)}
    return out


TILE_N, TILE_PER = 1024, 1.7       # detail tile: samples, and its size in km


@lru_cache(maxsize=1)
def detail_tile() -> np.ndarray:
    """Seamless rock relief: (N, N, 3) = height 0..1, d/du, d/dv (per km)."""
    rng = np.random.default_rng(41)
    n = TILE_N
    fx = np.fft.fftfreq(n)[:, None] * n
    fy = np.fft.fftfreq(n)[None, :] * n
    k = np.hypot(fx, fy)
    k[0, 0] = 1.0

    def fbm(power: float, lo: float, hi: float) -> np.ndarray:
        amp = k ** (-power) * (k >= lo) * (k <= hi)
        spec = amp * np.exp(2j * np.pi * rng.random((n, n)))
        f = np.real(np.fft.ifft2(spec))
        return f / (np.abs(f).max() + 1e-9)

    ridged = 1 - np.abs(fbm(1.7, 2, 90)) * 1.6               # sharp crests
    lumps = fbm(2.1, 2, 24) * 0.5 + 0.5
    grit = fbm(1.1, 30, 150) * 0.5 + 0.5
    d = np.clip(0.55 * ridged + 0.33 * lumps + 0.12 * grit, 0, 1)
    step = TILE_PER / n
    gu = (np.roll(d, -1, 0) - np.roll(d, 1, 0)) / (2 * step)
    gv = (np.roll(d, -1, 1) - np.roll(d, 1, 1)) / (2 * step)
    return np.stack([d, gu, gv], -1).astype(np.float32)


@lru_cache(maxsize=1)
def _tile_x():
    return xp.asarray(detail_tile())


def _tex(u, v):
    """Bilinear, wrapping lookup of the detail tile at world coordinates (km)."""
    tile = _tile_x()
    n = TILE_N
    a = u / TILE_PER * n
    b = v / TILE_PER * n
    a0 = xp.floor(a)
    b0 = xp.floor(b)
    fa = (a - a0).astype(xp.float32)[:, None]
    fb = (b - b0).astype(xp.float32)[:, None]
    i0 = a0.astype(xp.int64) % n
    j0 = b0.astype(xp.int64) % n
    i1 = (i0 + 1) % n
    j1 = (j0 + 1) % n
    return ((tile[i0, j0] * (1 - fa) + tile[i1, j0] * fa) * (1 - fb)
            + (tile[i0, j1] * (1 - fa) + tile[i1, j1] * fa) * fb)


def shade_dive(F, pe, dist, cam, lamp: float):
    """The seabed and trench walls seen from inside the water: rock relief from
    the detail tile (three projections, so steep walls are not smeared), a dim
    blue ambient, and the lamp, which sits up and to the left of the lens so the
    relief throws shading."""
    x, y, z = pe[:, 0], pe[:, 1], pe[:, 2]
    _, n, _ = surface_info(F, x, z, 0.0)
    n = n.astype(xp.float32)
    w = n * n                                                  # projection weights
    near = xp.clip(1.7 - dist * 0.28, 0, 1)                    # fine detail only near the lens
    fine = xp.exp(-dist * 1.1)
    bump = xp.zeros_like(n)
    hgt = xp.zeros(len(x), xp.float32)
    for wgt, (u, v), (au, av) in ((w[:, 1], (x, z), (0, 2)), (w[:, 0], (z, y), (2, 1)), (w[:, 2], (x, y), (0, 1))):
        t1 = _tex(u, v)
        t2 = _tex(u * 3.3 + 0.37 * v + 0.2, v * 3.3 - 0.37 * u + 0.7)
        hgt += wgt * (t1[:, 0] * 0.7 + t2[:, 0] * 0.3)
        gu = t1[:, 1] * near + 1.1 * (t2[:, 1] * 3.3 - t2[:, 2] * 0.37) * fine * 0.50
        gv = t1[:, 2] * near + 1.1 * (t2[:, 2] * 3.3 + t2[:, 1] * 0.37) * fine * 0.50
        bump[:, au] += wgt * gu
        bump[:, av] += wgt * gv
    slope = 1 - n[:, 1]
    rocky = xp.clip((slope - 0.10) / 0.22, 0, 1)
    strength = (0.060 + 0.21 * rocky)[:, None]                 # sediment is smooth, rock is rough
    nb = n - bump * strength
    nb /= xp.linalg.norm(nb, axis=1, keepdims=True)
    av_ = _sample(F["A"], F, x, z)
    strata = 0.5 + 0.5 * xp.sin(y * 46 + 5.0 * hgt + 1.3 * xp.sin(x * 2.1 + z * 1.7))
    alb = (xp.array([150, 142, 126], xp.float32) * (1 - rocky[:, None])
           + xp.array([104, 100, 98], xp.float32) * rocky[:, None])
    alb = alb * ((0.62 + 0.62 * hgt) * (1 + 0.15 * av_) * (1 - 0.16 * rocky * strata * near))[:, None]
    lp = xp.asarray(cam.pos - 0.50 * cam.r + 0.42 * cam.u, xp.float32)      # the lamp
    lv = lp[None] - pe
    ld = xp.linalg.norm(lv, axis=1)
    lv /= ld[:, None]
    lam = xp.clip((nb * lv).sum(1), 0, 1)
    aim = xp.clip(((-lv) @ xp.asarray(cam.f, xp.float32) - 0.60) / 0.34, 0, 1) ** 1.5
    beam = lamp * 3.6 * lam * aim * xp.exp(-0.60 * ld)
    amb = 0.10 + 0.22 * xp.clip(nb[:, 1], 0, 1) + 0.06 * hgt
    lit = alb * (amb[:, None] * xp.array([0.42, 0.70, 1.10], xp.float32)[None]
                 + beam[:, None] * xp.array([1.06, 1.0, 0.90], xp.float32)[None])
    return 236 * (1 - xp.exp(-lit / 150))


def _sample(arr, F, x, z):
    """A field at points: the detailed grid, and beyond it the coarse seabed (or zero)."""
    v = mapc(arr, xp.stack([(x - F["x0"]) / F["hx"], (z - F["z0"]) / F["hz"]]), order=1, mode="nearest")
    out = (x < GX[0]) | (x > GX[1]) | (z < GZ[0]) | (z > GZ[1])
    if bool(out.any()):
        far = F["far"].get(id(arr))
        if far is None:
            v = xp.where(out, 0.0, v)
        else:
            v = v.astype(xp.float32, copy=True)
            v[out] = mapc(far, xp.stack([(x[out] - F["far0"][0]) / F["farh"][0], (z[out] - F["far0"][1]) / F["farh"][1]]),
                          order=1, mode="nearest")
    return v


@lru_cache(maxsize=1)
def fields_x():
    """The fields on the renderer's device (the GPU if there is one)."""
    F = fields()
    G = dict(hx=float(F["hx"]), hz=float(F["hz"]), x0=float(F["xs"][0]), z0=float(F["zs"][0]),
             far0=(float(F["far0"][0]), float(F["far0"][1])), farh=(float(F["farh"][0]), float(F["farh"][1])))
    for k in ("T", "S", "A"):
        G[k] = xp.asarray(F[k])
    for k in ("Tg", "Sg"):
        G[k] = tuple(xp.asarray(v) for v in F[k])
    G["far"] = {id(G["T"]): xp.asarray(F["far"][id(F["T"])]),
                id(G["Tg"][0]): xp.asarray(F["far"][id(F["Tg"][0])]),
                id(G["Tg"][1]): xp.asarray(F["far"][id(F["Tg"][1])])}
    return G


def height_np(F, x, z, rise: float) -> np.ndarray:
    """height() for CPU callers (labels, overlays): NumPy in, NumPy out."""
    return to_np(height(F, xp.asarray(x, xp.float32), xp.asarray(z, xp.float32), rise))


def everest_y(S, rise: float):
    """Everest's surface height for its shape value S, rising with `rise` 0..1."""
    return -DEEP + EVEREST * S - (1 - rise) * (EVEREST + 0.8)


def height(F, x, z, rise: float):
    t = _sample(F["T"], F, x, z)
    if rise <= 0.0:
        return t
    return xp.maximum(t, everest_y(_sample(F["S"], F, x, z), rise))


def surface_info(F, x, z, rise: float):
    """Height, normal and material (0 seabed, 1 Everest rock) at points."""
    t = _sample(F["T"], F, x, z)
    tgx, tgz = _sample(F["Tg"][0], F, x, z), _sample(F["Tg"][1], F, x, z)
    if rise > 0:
        s = _sample(F["S"], F, x, z)
        e = everest_y(s, rise)
        ev = e > t
        sgx, sgz = _sample(F["Sg"][0], F, x, z), _sample(F["Sg"][1], F, x, z)
        h = xp.where(ev, e, t)
        gx = xp.where(ev, EVEREST * sgx, tgx)
        gz = xp.where(ev, EVEREST * sgz, tgz)
    else:
        h, gx, gz, ev = t, tgx, tgz, xp.zeros_like(t, bool)
    n = xp.stack([-gx, xp.ones_like(gx), -gz], -1)
    n /= xp.linalg.norm(n, axis=-1, keepdims=True)
    return h, n, ev


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
_FOG_D = xp.array([0.0, 0.2, 1.0, 3.0, 6.0, 11.5])
_FOG_C = xp.array([(46, 126, 166), (30, 94, 136), (17, 56, 98), (12, 36, 70), (10, 26, 54), (9, 19, 42)],
                  xp.float32)
# the dive's own water: darker, as it really gets (the lamp does the rest)
_DIVE_C = xp.array([(52, 132, 170), (24, 78, 118), (8, 30, 58), (5, 15, 33), (4, 11, 25), (3, 8, 19)],
                   xp.float32)


def fog_col(depth_km, table=None):
    """Water colour at a depth (number or array) -> (..., 3)."""
    table = _FOG_C if table is None else table
    d = xp.clip(xp.asarray(depth_km, xp.float32), 0, 11.5)
    flat = d.reshape(-1)
    out = xp.stack([xp.interp(flat, _FOG_D, table[:, k]) for k in range(3)], -1).astype(xp.float32)
    return out.reshape(d.shape + (3,))


SEABED = xp.array([104, 98, 90], xp.float32)
WALL = xp.array([84, 80, 78], xp.float32)
EV_ROCK = xp.array([138, 126, 116], xp.float32)
SNOW = xp.array([240, 244, 250], xp.float32)
ROCK_FACE = xp.array([70, 60, 52], xp.float32)
SED_FACE = xp.array([112, 100, 82], xp.float32)
KEY_L = xp.array([0.55, 0.72, -0.42])
KEY_L = KEY_L / xp.linalg.norm(KEY_L)
FILL_L = xp.array([-0.6, 0.35, -0.72])          # soft fill from the camera's side
FILL_L = FILL_L / xp.linalg.norm(FILL_L)


def shade_terrain(F, p, rise: float, cutaway: bool):
    """Colour of the terrain at world points p (N,3)."""
    h, n, ev = surface_info(F, p[:, 0], p[:, 2], rise)
    y = p[:, 1]
    slope = 1 - n[:, 1]
    av = _sample(F["A"], F, p[:, 0], p[:, 2])
    wall_f = xp.clip((slope - 0.12) / 0.25, 0, 1)[:, None]
    alb = SEABED * (1 - wall_f) + WALL * wall_f
    alb = alb * (1 + 0.10 * av)[:, None]
    if ev.any():
        line = -5.0 + 0.45 * xp.sin(p[:, 0] * 3.1 + p[:, 2] * 2.3) + 0.25 * av
        snow_f = xp.clip((y - line) / 0.45, 0, 1) * xp.clip((n[:, 1] - 0.10) / 0.25, 0, 1)
        rock = EV_ROCK * (0.82 + 0.14 * av)[:, None]
        evc = rock * (1 - snow_f[:, None]) + SNOW * snow_f[:, None]
        alb = xp.where(ev[:, None], evc, alb)
    lam = xp.clip(n @ KEY_L, 0, 1)
    fill = xp.clip(n @ FILL_L, 0, 1)
    sky = 0.5 + 0.5 * n[:, 1]
    if cutaway:
        light = 0.26 + 0.80 * lam + 0.32 * fill + 0.16 * sky
        depth_dim = 0.58 + 0.42 * xp.exp(y / 7.0)
    else:
        light = 0.25 + 0.75 * lam + 0.15 * sky
        depth_dim = 1.0
    return alb * (light * depth_dim)[:, None]


# --------------------------------------------------------------------------- #
# Camera and rays
# --------------------------------------------------------------------------- #
class Cam:
    def __init__(self, pos, target, vfov_deg: float, roll: float = 0.0):
        self.pos = np.asarray(pos, np.float64)
        f = np.asarray(target, np.float64) - self.pos
        self.f = f / np.linalg.norm(f)
        up = np.array([math.sin(roll), math.cos(roll), 0.0])
        r = np.cross(up, self.f)
        if np.linalg.norm(r) < 1e-6:
            r = np.array([1.0, 0, 0])
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.f, self.r)
        self.t = math.tan(math.radians(vfov_deg) / 2)

    @staticmethod
    def look(pos, yaw_deg: float, pitch_deg: float, vfov: float):
        yw, pt = math.radians(yaw_deg), math.radians(pitch_deg)
        d = np.array([math.sin(yw) * math.cos(pt), -math.sin(pt), math.cos(yw) * math.cos(pt)])
        return Cam(pos, np.asarray(pos) + d, vfov)

    def rays(self, w: int, h: int):
        """Unit ray directions for a w x h picture, (w*h, 3), on the renderer's device."""
        f, r, u = (xp.asarray(v, xp.float32) for v in (self.f, self.r, self.u))
        sx = (xp.arange(w, dtype=xp.float32) + 0.5) / w * 2 - 1
        sy = 1 - (xp.arange(h, dtype=xp.float32) + 0.5) / h * 2
        X, Y = xp.meshgrid(sx * (self.t * w / h), sy * self.t)
        d = (f[None, None] + X[..., None] * r[None, None] + Y[..., None] * u[None, None]).reshape(-1, 3)
        return (d / xp.linalg.norm(d, axis=1, keepdims=True)).astype(xp.float32)

    def project(self, P):
        """World points (N,3) -> screen x, y (final 1080x1920 pixels), depth."""
        P = np.atleast_2d(np.asarray(P, np.float64)) - self.pos
        zc = P @ self.f
        xc = P @ self.r
        yc = P @ self.u
        zc_safe = np.where(zc > 1e-4, zc, 1e-4)
        sx = xc / (zc_safe * self.t * (W / H))
        sy = yc / (zc_safe * self.t)
        return (sx + 1) / 2 * W, (1 - sy) / 2 * H, zc


def _box_hit(o, d):
    """Slab test against the block (and the space above the surface is open)."""
    inv = 1.0 / xp.where(xp.abs(d) < 1e-9, 1e-9, d)
    lo = xp.array([X0, Y_BOT, Z0], xp.float32)
    hi = xp.array([X1, 0.0, Z1], xp.float32)
    t0 = (lo - o) * inv
    t1 = (hi - o) * inv
    tmin = xp.minimum(t0, t1)
    tmax = xp.maximum(t0, t1)
    tn = tmin.max(axis=1)
    tf = tmax.min(axis=1)
    face = tmin.argmax(axis=1)      # 0 x-side, 1 top/bottom, 2 front/back
    return tn, tf, face


def march(F, o, d, t0, t1, rise: float):
    """First terrain hit along each ray between t0 and t1 (xp.inf if none)."""
    n = len(d)
    hit = xp.full(n, xp.inf, xp.float32)
    t = t0.astype(xp.float32).copy()
    act = xp.arange(n)
    LIP = 4.4 if rise > 0 else 3.2   # steepest slope in the fields (Everest is steeper), for safe steps
    dh = xp.hypot(d[:, 0], d[:, 2])
    last = xp.full(n, 0.02, xp.float32)          # the step that led to each sample (the bisection's window)
    for _ in range(260):
        if not len(act):
            break
        p = o[act] + d[act] * t[act, None] if o.ndim == 2 else o + d[act] * t[act, None]
        h = height(F, p[:, 0], p[:, 2], rise)
        gap = p[:, 1] - h
        under = gap < 0.004
        if under.any():
            hit[act[under]] = t[act[under]]
        # never finer than the picture needs: the floor on the step grows with distance,
        # so rays skimming the seabed far off do not crawl
        step = xp.clip(gap / (xp.abs(d[act, 1]) + LIP * dh[act] + 1e-3) * 0.9,
                       0.006 + 0.004 * (t[act] - t0[act]), 1.2)
        t[act] += step
        last[act] = step
        keep = (~under) & (t[act] < t1[act])
        act = act[keep]
    # refine: back off and bisect
    ok = xp.isfinite(hit)
    if ok.any():
        idx = xp.where(ok)[0]
        hi_t = hit[idx]
        lo_t = xp.maximum(t0[idx], hi_t - xp.maximum(last[idx], 0.02))
        for _ in range(9):
            mid = (lo_t + hi_t) / 2
            p = (o[idx] if o.ndim == 2 else o) + d[idx] * mid[:, None]
            below = p[:, 1] < height(F, p[:, 0], p[:, 2], rise)
            hi_t = xp.where(below, mid, hi_t)
            lo_t = xp.where(below, lo_t, mid)
        hit[idx] = hi_t
    return hit


# --------------------------------------------------------------------------- #
# Rendering: the cutaway (camera outside) and the dive (camera in the water)
# --------------------------------------------------------------------------- #
SUN = xp.array([0.3256, 0.045, 0.9455], xp.float32)        # low, just off the right of the opening shot
SUN = SUN / xp.linalg.norm(SUN)


def _sky(d):
    """Blue-hour sky: dark overhead, a paler band at the horizon, a warm glow where the sun has gone."""
    up = xp.clip(d[:, 1] / 0.13, 0, 1)
    up = (up * up * (3 - 2 * up))[:, None]
    col = xp.array([76, 94, 118], xp.float32) * (1 - up) + xp.array([14, 20, 36], xp.float32) * up
    g = xp.clip(d @ SUN, 0, 1)
    return col + xp.array([255, 190, 132], xp.float32) * (0.42 * g ** 300 + 0.13 * g ** 40 + 0.02 * g ** 6)[:, None]


def _waves(x, z, t, chop=1.0, swell=1.0):
    """Surface normals: short chop (faded out with distance, where it would
    shimmer) over a long slow swell."""
    gx = chop * (0.06 * xp.cos(3.1 * x + 1.7 * z + 1.3 * t) + 0.035 * xp.cos(-2.2 * x + 4.3 * z + 1.9 * t)
                 + 0.02 * xp.cos(7.1 * x - 3.3 * z + 2.6 * t)) + swell * 0.020 * xp.cos(0.33 * x + 0.52 * z + 0.6 * t)
    gz = chop * (0.05 * xp.cos(1.3 * x + 3.6 * z + 1.1 * t) + 0.03 * xp.cos(4.4 * x - 2.6 * z + 2.2 * t)
                 + 0.02 * xp.cos(-5.3 * x + 6.2 * z + 2.9 * t)) + swell * 0.026 * xp.cos(-0.21 * x + 0.61 * z + 0.5 * t)
    n = xp.stack([-gx, xp.ones_like(gx), -gz], -1)
    return n / xp.linalg.norm(n, axis=-1, keepdims=True)


def _rock_face(p, face_normal):
    y = p[:, 1]
    warp = 0.12 * xp.sin(p[:, 0] * 1.1 + p[:, 2] * 0.9) + 0.05 * xp.sin(p[:, 0] * 3.7 - p[:, 2] * 2.9)
    yy = y + warp
    band = 0.05 * xp.sin(yy * 6.0) + 0.035 * xp.sin(yy * 17.0 + 1.3) + 0.02 * xp.sin(yy * 41.0 + 0.4)
    deep = xp.clip(-y / 12.0, 0, 1)[:, None]
    c = ROCK_FACE * (1 + band)[:, None] * (1.08 - 0.25 * deep) + xp.array([10, 6, 2], xp.float32) * (1 - deep)
    lam = max(0.0, float(face_normal @ KEY_L))
    return c * (0.55 + 0.6 * lam)


def render_cutaway(F, cam: Cam, rise: float, t: float, ss: float = 1.5,
                   fog_k: float = 0.085, near: float = 0.0) -> np.ndarray:
    """The sea from outside: sky, the surface running to the horizon, and the
    cut face (water and rock). `near` (0..1): the lens is close above the sea,
    so the surface turns opaque and shows fine ripples."""
    w, h = int(round(W * ss)), int(round(H * ss))
    d = cam.rays(w, h)
    o = xp.asarray(cam.pos, xp.float32)
    out = _sky(d)
    tn, tf, face = _box_hit(o[None], d)
    inside = (tf > xp.maximum(tn, 0)) & (tn > 0)
    idx = xp.where(inside)[0]
    if len(idx):
        dd = d[idx]
        t_in, t_out, fc = tn[idx], tf[idx], face[idx]
        P = o + dd * t_in[:, None]
        col = xp.zeros((len(idx), 3), xp.float32)
        top = (fc == 1) & (P[:, 1] > -0.01)
        side = ~top
        # cut faces: rock where the face is under the terrain
        hface = height(F, P[:, 0], P[:, 2], rise)
        rock = side & (P[:, 1] < hface)
        if rock.any():
            fn = xp.where((fc[rock] == 0)[:, None], xp.array([[1.0, 0, 0]]) * xp.sign(P[rock, 0:1]),
                          xp.array([[0, 0, -1.0]]))
            # per-face light (two faces at most are visible)
            c = xp.zeros((int(rock.sum()), 3), xp.float32)
            for nv in (xp.array([1.0, 0, 0]), xp.array([-1.0, 0, 0]), xp.array([0, 0, -1.0])):
                m = xp.all(xp.isclose(fn, nv), axis=1)
                if m.any():
                    c[m] = _rock_face(P[rock][m], nv)
            # a lighter sediment skin just under the seabed line
            skin = xp.clip(1 - (hface[rock] - P[rock, 1]) / 0.18, 0, 1)[:, None]
            col[rock] = c * (1 - skin * 0.6) + SED_FACE * skin * 0.6 * (0.6 + 0.4 * c.mean() / 60)
        water = ~rock
        if water.any():
            wi = xp.where(water)[0]
            t_far = xp.minimum(t_out[wi], t_in[wi] + 34.0)            # past this the haze has taken everything
            glance = top[wi] & (dd[wi][:, 1] > -0.22)                 # the surface seen at a glancing angle is a mirror
            t_far = xp.where(glance, t_in[wi] + 0.02, t_far)
            th = march(F, o[None].repeat(len(wi), 0), dd[wi], t_in[wi] + 1e-4, t_far, rise)
            got = xp.isfinite(th)
            tend = xp.where(got, th, t_far)
            L = tend - t_in[wi]
            pe = o + dd[wi] * tend[:, None]
            c_end = fog_col(-pe[:, 1]) * 0.75
            if got.any():
                c_end[got] = shade_terrain(F, pe[got], rise, cutaway=True)
            depth_mid = -(P[wi, 1] + pe[:, 1]) / 2
            fogc = fog_col(depth_mid)
            T = xp.exp(-fog_k * L)[:, None]
            cw = c_end * T + fogc * (1 - T)
            # glass faces: a faint sheen; the top: a moving, reflective surface
            tw = top[wi]
            if tw.any():
                away = t_in[wi][tw]
                n = _waves(P[wi][tw, 0], P[wi][tw, 2], t, xp.clip(1.75 - away / 30.0, 0, 1),
                           xp.clip(1.5 - away / 220.0, 0, 1))
                cosi = xp.clip(-(dd[wi][tw] * n).sum(1), 0, 1)
                fres = (0.04 + 0.96 * (1 - cosi) ** 5)[:, None]
                refl = dd[wi][tw] - 2 * (dd[wi][tw] * n).sum(1)[:, None] * n
                spec = xp.clip((refl @ SUN), 0, 1) ** 90 * 0.9
                surf = cw[tw] * 0.72 + xp.array([22, 66, 96], xp.float32) * 0.28
                if near > 0:
                    px_, pz_ = P[wi][tw, 0], P[wi][tw, 2]
                    dl = t_in[wi][tw]
                    rip = xp.zeros_like(px_)
                    for f, amp, sp, ph in ((9, 0.5, 1.1, 0.3), (21, 0.42, 1.7, 1.9), (47, 0.34, 2.4, 4.0),
                                           (103, 0.26, 3.1, 2.2)):
                        keep = xp.clip(2.0 - f * dl * 0.012, 0, 1)          # no ripple finer than a few pixels
                        rip += amp * keep * xp.sin(f * (0.83 * px_ + 0.55 * pz_) + sp * t + ph
                                                   + 1.3 * xp.sin(f * 0.41 * (pz_ - 0.6 * px_) - 0.7 * sp * t))
                    sea = (xp.array([20, 84, 124], xp.float32) * (1 + 0.16 * rip)[:, None]
                           + xp.array([120, 176, 200], xp.float32) * (xp.clip(rip - 0.62, 0, 1) ** 2)[:, None])
                    surf = surf * (1 - 0.85 * near) + sea * (0.85 * near)
                refl[:, 1] = xp.abs(refl[:, 1])
                sea = surf * (1 - fres) + _sky(refl) * fres + spec[:, None] * xp.array([255, 214, 170], xp.float32)
                haze = (1 - xp.exp(-away / 300.0))[:, None]              # the far sea melts into the horizon
                cw[tw] = sea * (1 - haze) + xp.array([70, 88, 112], xp.float32) * haze
            sw = ~tw
            if sw.any():
                cw[sw] = cw[sw] * 0.95 + xp.array([140, 190, 215], xp.float32) * 0.04
            col[water] = cw
        out[idx] = col
    im = Image.fromarray(to_np(xp.clip(out.reshape(h, w, 3), 0, 255).astype(xp.uint8)))
    _release()
    if ss != 1:
        im = im.resize((W, H), Image.LANCZOS)
    return np.asarray(im, np.float32)


def render_dive(F, cam: Cam, rise: float, t: float, depth_km: float, lamp: float, ss: float = 1.0,
                reach: float = 7.0) -> np.ndarray:
    """The water around a camera inside the ocean: depth colour, and the seabed
    and trench walls when near: dimly visible far off, lit by the lamp up close."""
    w, h = int(round(W * ss)), int(round(H * ss))
    d = cam.rays(w, h)
    o = xp.asarray(cam.pos, xp.float32)
    base = fog_col(depth_km, _DIVE_C)
    up = d[:, 1]
    col = base[None] * (0.62 + 0.55 * xp.clip(up * 0.9 + 0.45, 0, 1.2))[:, None]
    render_dive.centre = None
    seen = smooth((-float(o[1]) - 1.9) / 0.8)            # the plain fades in from ~2 km above it
    if seen > 0.0:
        idx = xp.where(up < 0.35)[0]
        th = march(F, o[None].repeat(len(idx), 0), d[idx], xp.full(len(idx), 0.02, xp.float32),
                   xp.full(len(idx), reach, xp.float32), rise)
        got = xp.isfinite(th)
        if got.any():
            gi = idx[got]
            dist = th[got]
            pe = o + d[gi] * dist[:, None]
            lit = shade_dive(F, pe, dist, cam, lamp)
            mid = (d[gi] @ xp.asarray(cam.f, xp.float32)) > 0.96
            if mid.sum() > 200:
                render_dive.centre = float(xp.median(dist[mid]))
            T = (seen * xp.exp(-0.34 * dist) * xp.clip((reach - dist) / 1.2, 0, 1))[:, None]
            col[gi] = lit * T + col[gi] * (1 - T)
    img = to_np(col.reshape(h, w, 3))
    _release()
    if ss != 1:
        img = np.asarray(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W, H), Image.LANCZOS),
                         np.float32)
    return img


def lamp_beams() -> np.ndarray:
    """Two lamps below the lens, their beams crossing ahead: H x W, 0..~1."""
    hh, ww = H // 4, W // 4
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32) * 4 + 2
    out = np.zeros((hh, ww), np.float32)
    cx, cy = W / 2, 800.0
    for ax in (-170.0, W + 170.0):
        ay = H + 140.0
        ln = math.hypot(cx - ax, cy - ay)
        ux, uy = (cx - ax) / ln, (cy - ay) / ln
        sgm = ((xx - ax) * ux + (yy - ay) * uy) / ln
        r = np.abs(-(xx - ax) * uy + (yy - ay) * ux)
        wd = 90 + 360 * np.clip(sgm, 0, 2)
        out += np.exp(-(r / wd) ** 2) * np.clip(sgm / 0.1, 0, 1) * np.exp(-1.7 * np.clip(sgm, 0, 3))
    pool = np.exp(-(((xx - cx) / 470) ** 2 + ((yy - 980) / 700) ** 2))
    out = 0.40 * out + 0.75 * pool
    return np.asarray(Image.fromarray(out).resize((W, H), Image.BICUBIC), np.float32)


# --------------------------------------------------------------------------- #
# Sub-pixel compositing (labels and sprites never snap to whole pixels)
# --------------------------------------------------------------------------- #
_DITHER = (np.random.default_rng(99).random((H, W, 1), np.float32) - 0.5) * 1.6   # fixed: no banding, no flicker


def grade(arr: np.ndarray, sharp: float = 0.55) -> np.ndarray:
    """The final look: an unsharp mask so detail reads crisply, then a little
    more contrast with deeper blacks. Applied before any text is drawn."""
    from scipy.ndimage import gaussian_filter

    out = arr + sharp * (arr - gaussian_filter(arr, (1.3, 1.3, 0)))
    return np.clip(56.0 + (out - 56.0) * 1.12, 0, 255)


def to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr + _DITHER, 0, 255).astype(np.uint8))


def blit(img: Image.Image, rgba: Image.Image, x: float, y: float, alpha: float = 1.0,
         width: float | None = None) -> None:
    """Paste an RGBA sprite with its top-left at float (x, y), scaled to `width` px."""
    if alpha <= 0.004:
        return
    src = rgba
    s = (width / src.size[0]) if width else 1.0
    while s < 0.5 and src.size[0] > 32:              # pre-shrink, so bicubic never aliases
        src = src.reduce(2)
        s *= 2
    tw, th = int(math.ceil(src.size[0] * s)) + 3, int(math.ceil(src.size[1] * s)) + 3
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    x0, y0 = max(0, ix), max(0, iy)
    x1, y1 = min(W, ix + tw), min(H, iy + th)
    if x1 <= x0 or y1 <= y0:
        return
    inv = 1.0 / s
    t = src.transform((tw, th), Image.AFFINE, (inv, 0, -fx * inv, 0, inv, -fy * inv), resample=Image.BICUBIC)
    a = np.asarray(t, np.float32)[y0 - iy:y1 - iy, x0 - ix:x1 - ix]
    m = a[..., 3:4] / 255 * alpha
    reg = np.asarray(img.crop((x0, y0, x1, y1)), np.float32)
    reg = reg * (1 - m) + a[..., :3] * m
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), (x0, y0))


def text_sprite(rows, align: str = "left") -> Image.Image:
    """rows: [(text, colour, font)] stacked; returns RGBA with a soft shadow."""
    gap = 4
    ws = [f.getlength(t) for t, _, f in rows]
    hs = [f.size * 1.16 for _, _, f in rows]
    pad = 24
    wd, hd = int(max(ws)) + pad * 2, int(sum(hs) + gap * (len(rows) - 1)) + pad * 2
    mask = Image.new("L", (wd, hd), 0)
    colr = Image.new("RGB", (wd, hd), (0, 0, 0))
    dm, dc = ImageDraw.Draw(mask), ImageDraw.Draw(colr)
    y = pad
    for (t, c, f), w_, h_ in zip(rows, ws, hs):
        x = pad if align == "left" else (wd - pad - w_ if align == "right" else (wd - w_) / 2)
        dm.text((x, y + h_ / 2), t, font=f, fill=255, anchor="lm")
        dc.rectangle((0, y - gap / 2, wd, y + h_ + gap / 2), fill=tuple(int(v) for v in c))
        y += h_ + gap
    m = np.asarray(mask, np.float32) / 255
    sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(7)), np.float32) / 255
    sh = np.clip(np.roll(sh, 3, axis=0) * 1.5, 0, 1) * 0.8
    a = m + sh * (1 - m)
    rgb = np.asarray(colr, np.float32) * (m / np.maximum(a, 1e-4))[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8), "RGBA")


def _over(img: Image.Image, surf: cairo.ImageSurface) -> None:
    """Composite a premultiplied cairo ARGB surface over the frame."""
    surf.flush()
    buf = np.ndarray((H, W, 4), np.uint8, surf.get_data())
    a = buf[..., 3:4].astype(np.float32) / 255
    base = np.asarray(img, np.float32)
    img.paste(Image.fromarray(np.clip(base * (1 - a) + buf[..., 2::-1], 0, 255).astype(np.uint8)))


def _ctx():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    return surf, ctx


# --------------------------------------------------------------------------- #
# The creatures and the wreck (drawn once, large; scaled per frame)
# --------------------------------------------------------------------------- #
def _sprite(w: int, h: int, draw) -> Image.Image:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    draw(ctx)
    surf.flush()
    buf = np.ndarray((h, w, 4), np.uint8, surf.get_data()).copy()
    a = buf[..., 3:4].astype(np.float32)
    rgb = buf[..., 2::-1].astype(np.float32) * 255 / np.maximum(a, 1)     # un-premultiply
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8), "RGBA")


def _fill(ctx, y0, y1, top, bot, rim_a=0.35, rim_w=3.0, alpha=1.0):
    """Fill the current path top-lit (light from above), with a pale rim."""
    g = cairo.LinearGradient(0, y0, 0, y1)
    g.add_color_stop_rgba(0, *[c / 255 for c in top], alpha)
    g.add_color_stop_rgba(0.55, *[(a + 2 * b) / 3 / 255 for a, b in zip(top, bot)], alpha)
    g.add_color_stop_rgba(1, *[c / 255 for c in bot], alpha)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(0.92, 0.97, 1.0, rim_a)
    ctx.set_line_width(rim_w)
    ctx.stroke()


def make_diver() -> Image.Image:
    def d(ctx):
        top, bot = (196, 212, 224), (34, 52, 78)
        # legs, trailing, with long fins
        for dy, k in ((-10, 1.0), (20, 0.8)):
            ctx.new_path()
            ctx.move_to(430, 292 + dy * 0.3)
            ctx.curve_to(360, 290 + dy, 290, 292 + dy * 1.3, 232, 296 + dy * 1.5)
            ctx.curve_to(180, 292 + dy * 1.9, 120, 276 + dy * 2.2, 62, 262 + dy * 2.4)
            ctx.curve_to(56, 286 + dy * 2.4, 66, 306 + dy * 2.4, 84, 316 + dy * 2.4)
            ctx.curve_to(140, 322 + dy * 2.0, 190, 324 + dy * 1.7, 236, 322 + dy * 1.5)
            ctx.curve_to(300, 326 + dy * 1.2, 370, 328 + dy, 440, 326 + dy * 0.3)
            ctx.close_path()
            _fill(ctx, 240, 380, tuple(c * k for c in (250, 176, 70)), (120, 66, 20), rim_a=0.22)
        # tank on the back
        ctx.new_path()
        ctx.move_to(476, 236)
        ctx.line_to(676, 228)
        ctx.curve_to(704, 228, 704, 262, 678, 264)
        ctx.line_to(478, 272)
        ctx.curve_to(452, 272, 452, 238, 476, 236)
        _fill(ctx, 226, 272, (250, 214, 110), (132, 96, 30), rim_a=0.3)
        # torso
        ctx.new_path()
        ctx.move_to(424, 294)
        ctx.curve_to(452, 252, 640, 250, 724, 276)
        ctx.curve_to(764, 294, 746, 334, 694, 340)
        ctx.curve_to(600, 352, 468, 350, 424, 330)
        ctx.close_path()
        _fill(ctx, 250, 352, top, bot)
        # arm reaching forward, with a torch
        ctx.new_path()
        ctx.move_to(640, 316)
        ctx.curve_to(720, 336, 800, 350, 880, 348)
        ctx.curve_to(894, 350, 894, 370, 880, 370)
        ctx.curve_to(800, 376, 700, 362, 628, 344)
        ctx.close_path()
        _fill(ctx, 316, 376, top, bot, rim_a=0.22)
        # head, mask, regulator
        ctx.new_path()
        ctx.arc(780, 284, 44, 0, 2 * math.pi)
        _fill(ctx, 240, 328, top, bot)
        ctx.new_path()
        ctx.move_to(798, 266)
        ctx.curve_to(842, 262, 850, 300, 812, 306)
        ctx.curve_to(800, 296, 796, 280, 798, 266)
        ctx.close_path()
        ctx.set_source_rgba(0.72, 0.9, 0.98, 0.9)
        ctx.fill()
        # bubbles, rising
        for bx, by, r in ((826, 212, 11), (846, 164, 8), (830, 122, 6), (852, 86, 4.5), (838, 56, 3.2)):
            ctx.new_path()
            ctx.arc(bx, by, r, 0, 2 * math.pi)
            ctx.set_source_rgba(0.86, 0.96, 1.0, 0.8)
            ctx.set_line_width(2.6)
            ctx.stroke()
    return _sprite(960, 416, d)


def make_whale() -> Image.Image:
    def d(ctx):
        ctx.new_path()
        ctx.move_to(944, 212)                         # beak tip
        ctx.curve_to(908, 200, 880, 176, 800, 160)    # the melon
        ctx.curve_to(650, 128, 430, 138, 268, 178)
        ctx.curve_to(196, 196, 146, 208, 112, 212)    # tail stock
        ctx.curve_to(90, 196, 66, 174, 34, 152)       # upper fluke
        ctx.curve_to(52, 188, 62, 208, 70, 222)
        ctx.curve_to(62, 238, 52, 258, 34, 292)       # lower fluke
        ctx.curve_to(66, 270, 92, 248, 114, 234)
        ctx.curve_to(164, 240, 236, 264, 334, 280)
        ctx.curve_to(504, 304, 704, 294, 824, 262)
        ctx.curve_to(884, 246, 920, 230, 944, 212)
        ctx.close_path()
        _fill(ctx, 130, 302, (168, 176, 180), (30, 34, 40), rim_a=0.28)
        # paler belly
        ctx.new_path()
        ctx.move_to(360, 280)
        ctx.curve_to(520, 302, 700, 294, 824, 262)
        ctx.curve_to(700, 276, 520, 280, 360, 280)
        ctx.set_source_rgba(0.8, 0.82, 0.82, 0.22)
        ctx.fill()
        # dorsal fin, set far back, and a small flipper
        ctx.new_path()
        ctx.move_to(336, 166)
        ctx.curve_to(322, 132, 304, 116, 286, 110)
        ctx.curve_to(298, 140, 294, 162, 282, 176)
        ctx.close_path()
        _fill(ctx, 108, 178, (150, 158, 162), (50, 54, 60), rim_a=0.2)
        ctx.new_path()
        ctx.move_to(704, 268)
        ctx.curve_to(684, 300, 654, 318, 622, 326)
        ctx.curve_to(644, 300, 656, 286, 664, 270)
        ctx.close_path()
        _fill(ctx, 268, 328, (96, 104, 110), (30, 34, 40), rim_a=0.15)
        # eye and mouth line
        ctx.new_path()
        ctx.arc(846, 206, 6.5, 0, 2 * math.pi)
        ctx.set_source_rgba(0.04, 0.05, 0.07, 0.9)
        ctx.fill()
        ctx.new_path()
        ctx.move_to(940, 214)
        ctx.curve_to(908, 226, 884, 228, 862, 224)
        ctx.set_source_rgba(0.04, 0.05, 0.07, 0.55)
        ctx.set_line_width(3)
        ctx.stroke()
    return _sprite(976, 352, d)


def make_titanic() -> Image.Image:
    def d(ctx):
        # masts and rigging
        ctx.set_source_rgba(0.66, 0.62, 0.58, 0.8)
        ctx.set_line_width(4)
        for x in (150, 866):
            ctx.move_to(x, 216)
            ctx.line_to(x - 24, 36)
            ctx.stroke()
        # four funnels, raked back
        for x in (330, 448, 566, 684):
            ctx.new_path()
            ctx.move_to(x, 198)
            ctx.line_to(x - 28, 72)
            ctx.line_to(x + 22, 72)
            ctx.line_to(x + 50, 198)
            ctx.close_path()
            _fill(ctx, 72, 198, (196, 146, 86), (74, 48, 28), rim_a=0.22)
            ctx.new_path()
            ctx.move_to(x - 28, 72)
            ctx.line_to(x + 22, 72)
            ctx.line_to(x + 27, 94)
            ctx.line_to(x - 23, 94)
            ctx.close_path()
            ctx.set_source_rgba(0.07, 0.06, 0.06, 0.96)
            ctx.fill()
        # decks
        ctx.new_path()
        ctx.rectangle(236, 170, 540, 24)
        _fill(ctx, 170, 194, (206, 200, 188), (120, 114, 104), rim_a=0.18, rim_w=2)
        ctx.new_path()
        ctx.rectangle(196, 194, 632, 30)
        _fill(ctx, 194, 224, (190, 184, 172), (100, 94, 86), rim_a=0.18, rim_w=2)
        # hull: straight stem, counter stern, a lighter band at the top
        ctx.new_path()
        ctx.move_to(56, 228)
        ctx.line_to(936, 214)
        ctx.curve_to(926, 258, 908, 300, 878, 332)
        ctx.line_to(124, 336)
        ctx.curve_to(82, 320, 58, 282, 56, 228)
        ctx.close_path()
        _fill(ctx, 214, 336, (112, 104, 98), (24, 20, 20), rim_a=0.25)
        ctx.new_path()
        ctx.move_to(58, 250)
        ctx.line_to(928, 238)
        ctx.set_source_rgba(0.86, 0.8, 0.66, 0.35)
        ctx.set_line_width(3)
        ctx.stroke()
        # portholes
        ctx.set_source_rgba(0.95, 0.86, 0.6, 0.5)
        for i in range(44):
            for row in (0, 1):
                ctx.new_path()
                ctx.arc(110 + i * 18.4, 266 + row * 20 - i * 0.28, 2.4, 0, 2 * math.pi)
                ctx.fill()
    return _sprite(992, 352, d)


def make_snailfish() -> Image.Image:
    def d(ctx):
        # soft fin fringe first, so the body sits over it
        ctx.new_path()
        ctx.move_to(640, 150)
        ctx.curve_to(470, 132, 250, 200, 56, 264)
        ctx.curve_to(250, 312, 470, 372, 650, 352)
        ctx.close_path()
        g = cairo.LinearGradient(0, 130, 0, 372)
        g.add_color_stop_rgba(0, 1.0, 0.88, 0.92, 0.34)
        g.add_color_stop_rgba(0.5, 1.0, 0.8, 0.86, 0.16)
        g.add_color_stop_rgba(1, 1.0, 0.88, 0.92, 0.34)
        ctx.set_source(g)
        ctx.fill()
        # tadpole body: big soft head, tapering tail
        ctx.new_path()
        ctx.move_to(868, 250)
        ctx.curve_to(872, 168, 792, 148, 720, 158)
        ctx.curve_to(600, 172, 470, 204, 330, 234)
        ctx.curve_to(240, 252, 150, 262, 66, 266)
        ctx.curve_to(150, 280, 250, 290, 340, 300)
        ctx.curve_to(480, 316, 610, 338, 722, 342)
        ctx.curve_to(804, 344, 862, 318, 868, 250)
        ctx.close_path()
        g = cairo.LinearGradient(0, 150, 0, 345)
        g.add_color_stop_rgba(0, 1.0, 0.9, 0.92, 0.96)
        g.add_color_stop_rgba(1, 0.78, 0.52, 0.6, 0.9)
        ctx.set_source(g)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 0.96, 0.97, 0.55)
        ctx.set_line_width(2.5)
        ctx.stroke()
        # pectoral fin, eye
        ctx.new_path()
        ctx.move_to(690, 286)
        ctx.curve_to(650, 318, 600, 332, 560, 330)
        ctx.curve_to(600, 310, 630, 296, 652, 276)
        ctx.close_path()
        ctx.set_source_rgba(1, 0.86, 0.9, 0.5)
        ctx.fill()
        ctx.new_path()
        ctx.arc(806, 226, 13, 0, 2 * math.pi)
        ctx.set_source_rgba(0.1, 0.07, 0.1, 0.92)
        ctx.fill()
        ctx.new_path()
        ctx.arc(810, 222, 4, 0, 2 * math.pi)
        ctx.set_source_rgba(1, 1, 1, 0.7)
        ctx.fill()
    return _sprite(928, 400, d)


# key: (drawn fallback, world width, sideways offset, how far ahead of the camera)
CREATURES = {
    "scuba": (make_diver, 0.53, 0.02, 1.15),
    "whale": (make_whale, 0.67, -0.01, 1.35),
    "titanic": (make_titanic, 0.78, 0.0, 1.6),
    "fish": (make_snailfish, 0.47, 0.0, 1.1),
}

# The real models: built, animated and rendered in Blender by
# scripts/make_ocean_models.py (original work, nothing downloaded) into
# assets/ocean/<name>/NNN.png, one looping pose per file.
# key: (folder, video frames each pose is held, water tint, soft edges). The
# diver is lit by daylight that has lost its red; the rest by the lamp.
MODEL_DIR = Path(__file__).resolve().parents[2] / "assets" / "ocean"
MODELS = {
    "scuba": ("diver", 2, (0.72, 0.94, 1.05), False),       # 40 poses: a kick every 1.33 s
    "whale": ("whale", 3, (0.94, 0.99, 1.04), False),       # 48 poses: a tail beat every 2.4 s
    "titanic": ("titanic", 1, (0.90, 0.98, 1.05), True),    # the wreck: a still picture, edges melted away
    "fish": ("snailfish", 2, (0.96, 0.99, 1.03), False),    # 48 poses: a wiggle every 1.6 s
}


@lru_cache(maxsize=None)
def model_poses(name: str) -> int:
    return len(list((MODEL_DIR / name).glob("[0-9][0-9][0-9].png")))


@lru_cache(maxsize=6)
def model_pose(name: str, idx: int, tint: tuple, soft: bool = False):
    """One rendered pose as (RGBA image, float array). Colour is bled outwards
    under the transparent pixels, so scaling the sprite never drags a dark halo
    in from its edge."""
    from scipy.ndimage import gaussian_filter

    a = np.asarray(Image.open(MODEL_DIR / name / f"{idx:03d}.png").convert("RGBA"), np.float32) / 255
    al = a[..., 3:4]
    if soft:                       # a framed picture (the wreck): fade it out before its sides and bottom
        hh, ww = al.shape[:2]
        u = np.linspace(0, 1, ww, dtype=np.float32)[None, :, None]
        v = np.linspace(0, 1, hh, dtype=np.float32)[:, None, None]
        ramp = lambda q: np.clip(q, 0, 1) ** 2 * (3 - 2 * np.clip(q, 0, 1))
        al = al * ramp(u / 0.34) * ramp((1 - u) / 0.22) * ramp((1 - v) / 0.30)
    bleed = gaussian_filter(a[..., :3] * al, (4, 4, 0)) / np.maximum(gaussian_filter(al, (4, 4, 0)), 1e-4)
    rgb = np.where(al > 0.03, a[..., :3], bleed) * np.array(tint, np.float32)
    im = Image.fromarray((np.clip(np.dstack([rgb, al]), 0, 1) * 255).astype(np.uint8), "RGBA")
    if im.width > 1280:                      # rendered at twice this: shrink once, cleanly
        im = im.resize((1280, int(round(im.height * 1280 / im.width / 16)) * 16), Image.LANCZOS)
    return im, np.asarray(im, np.float32)


# --------------------------------------------------------------------------- #
# Sound helpers
# --------------------------------------------------------------------------- #
def _noise(dur: float, seed: int, cutoff: float) -> np.ndarray:
    from scipy.signal import butter, lfilter

    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, int(snd.SR * dur)).astype(np.float32)
    b, a = butter(2, cutoff / (snd.SR / 2))
    y = lfilter(b, a, x).astype(np.float32)
    return y / (np.abs(y).max() + 1e-6)


def splash(dur: float = 1.5) -> np.ndarray:
    t = np.arange(int(snd.SR * dur)) / snd.SR
    hi = _noise(dur, 11, 5200) * np.exp(-t * 5.5)
    lo = _noise(dur, 12, 380) * np.exp(-t * 2.2)
    rng = np.random.default_rng(13)
    bub = np.zeros_like(t)
    n = int(0.06 * snd.SR)
    tt = np.arange(n) / snd.SR
    for _ in range(26):
        i0 = int(rng.uniform(0.05, dur * 0.8) * snd.SR)
        f0 = rng.uniform(500, 1600)
        s = np.sin(2 * np.pi * (f0 * tt + 2600 * tt * tt)) * np.exp(-tt * 70) * rng.uniform(0.2, 0.5)
        k = min(n, len(bub) - i0)
        bub[i0:i0 + k] += s[:k]
    return (0.6 * hi + 0.8 * lo + 0.5 * bub).astype(np.float32)


def deep_bed(total: float, depth_at) -> np.ndarray:
    """A low drone that sinks in pitch as the dive goes down, over water rumble."""
    n = int(snd.SR * total)
    t = np.arange(n) / snd.SR
    grid = np.linspace(0, total, 600)
    dep = np.interp(t, grid, [depth_at(x) for x in grid])
    f = 82.4 * 2 ** (-dep / 11.0)
    ph = 2 * np.pi * np.cumsum(f) / snd.SR
    tone = np.sin(ph) + 0.45 * np.sin(1.5 * ph + 0.7) + 0.25 * np.sin(2 * ph + 1.3)
    rum = _noise(total + 0.1, 21, 160)[:n]
    env = np.clip(t / 2.0, 0, 1) * np.clip((total - t) / 1.5, 0, 1)
    return ((0.5 * tone / 1.7 + (0.2 + 0.4 * np.clip(dep / 11, 0, 1)) * rum) * env).astype(np.float32)


def rumble(dur: float) -> np.ndarray:
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    env = (u ** 1.2) * np.clip((1 - u) / 0.15, 0, 1)
    return ((0.8 * _noise(dur + 0.1, 31, 120)[:len(t)] + 0.6 * np.sin(2 * np.pi * 36 * t)) * env).astype(np.float32)


def whoosh(dur: float, f0: float, f1: float, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = np.zeros_like(t)
    for _ in range(12):
        f = f0 * (f1 / f0) ** u * rng.uniform(0.8, 1.25)
        out += np.sin(2 * np.pi * np.cumsum(f) / snd.SR + rng.uniform(0, 6.3)) * rng.uniform(0.4, 1.0)
    return (out / 12 * np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6).astype(np.float32)


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
# The opening: from just above the sea, looking at the cut face almost square on
WIDE = dict(tgt=np.array([0.0, -4.44, Z0]), dist=43.0, yaw=8.0, pitch=7.94, fov=26.0)
LOOK = 0.45          # the camera rides this far above the depth it reads out
DIVE_FOV = 58.0
DIVE_X, DIVE_Z = 0.0, -0.9
DIVE_PITCH = 24.0
KEYS = ("scuba", "whale", "titanic", "fish", "bottom")


def dive_yaw(depth_km: float) -> float:
    """Heading in the water: across the trench (its wall slides past on the way
    down), swinging to look along the canyon floor at the bottom."""
    return 62.0 - 54.0 * smoother((depth_km - 8.7) / 1.9)


def ahead_of(depth_km: float, ahead: float, side: float = 0.0) -> np.ndarray:
    """A point at that depth, in front of where the dive camera will be looking."""
    h = math.radians(dive_yaw(depth_km))
    return np.array([DIVE_X + ahead * math.sin(h) + side * math.cos(h), -depth_km,
                     DIVE_Z + ahead * math.cos(h) - side * math.sin(h)])


def orbit_cam(tgt, dist, yaw, pitch, fov) -> Cam:
    yw, pt = math.radians(yaw), math.radians(pitch)
    tgt = np.asarray(tgt, np.float64)
    pos = tgt + dist * np.array([-math.sin(yw) * math.cos(pt), math.sin(pt), -math.cos(yw) * math.cos(pt)])
    return Cam(pos, tgt, fov)


def _num_word(line) -> float:
    """Seconds into a line where its number is spoken (the camera arrives then)."""
    for c in line.words:
        if any(ch.isdigit() for ch in c["text"]):
            return float(c["start"])
    return line.secs * 0.6


class Plan:
    def __init__(self, L: dict):
        self.L = L
        self.hook_at = 0.15
        self.rew = self.hook_at + L["hook"].secs + 0.2      # the finished picture is let go
        self.sink1 = self.rew + 0.8                          # Everest is gone
        self.fly0 = self.rew + 0.15
        self.plunge = self.fly0 + 1.75
        # the dive: each line starts so that its number lands as the camera arrives
        self.at, self.arr, self.hold = {}, {}, {}
        prev_end = self.plunge + 0.35
        prev_d, prev_a = 0.0, self.plunge
        for k in KEYS:
            d = MD[k]
            need = 0.5 + 0.22 * (d - prev_d)                 # shortest travel time for the gap
            s = max(prev_end, prev_a + need - _num_word(L[k]))
            self.at[k] = s
            self.arr[k] = s + _num_word(L[k])
            prev_end = s + L[k].secs + 0.15
            self.hold[k] = max(0.3, prev_end - self.arr[k] - 0.1)
            prev_d, prev_a = d, self.arr[k] + self.hold[k] * 0.6
        self.pull0 = self.at["bottom"] + L["bottom"].secs + 0.35
        self.xfade = 0.55
        self.pull1 = self.pull0 + 2.0
        self.rise0 = self.pull0 + 0.9
        self.rise1 = self.rise0 + 1.9
        self.payoff_at = self.rise0 + 0.05
        self.total = max(self.payoff_at + L["payoff"].secs + 1.1, self.rise1 + 1.3)
        # the depth read-out: eases into every marker, rests there, moves on
        ts, ds = [self.plunge], [0.0]
        for k in KEYS[:-1]:
            a, d = self.arr[k], MD[k]
            creep = 0.010 * (1 + d)
            ts += [a - 0.3, a, a + self.hold[k] * 0.6]
            ds += [d - creep, d, d]
        ts += [self.arr["bottom"] - 0.4, self.arr["bottom"], self.total + 5]
        ds += [DEEP - 0.07, DEEP, DEEP]
        keep = [0]
        for i in range(1, len(ts)):
            if ts[i] > ts[keep[-1]] + 0.05 and ds[i] >= ds[keep[-1]]:
                keep.append(i)
        self.depth = PchipInterpolator([ts[i] for i in keep], [ds[i] for i in keep])

    def readout(self, t: float) -> float:
        return min(DEEP, float(self.depth(t))) if t >= self.plunge else 0.0

    def rise(self, t: float) -> float:
        if t < self.rew:
            return 1.0
        if t < self.sink1:
            return 1 - smoother((t - self.rew) / (self.sink1 - self.rew))
        if t < self.rise0:
            return 0.0
        return smoother((t - self.rise0) / (self.rise1 - self.rise0))

    def outside_cam(self, t: float) -> Cam:
        w = WIDE
        if t < self.fly0:
            return orbit_cam(w["tgt"], w["dist"], w["yaw"] - 3.5 * (1 - t / max(self.fly0, 1e-3)), w["pitch"], w["fov"])
        if t < self.plunge + 0.3:
            # straight in over the block's top edge, never below the surface
            u = smoother((t - self.fly0) / (self.plunge - self.fly0))
            p0 = orbit_cam(w["tgt"], w["dist"], w["yaw"], w["pitch"], w["fov"]).pos
            p1 = np.array([DIVE_X, 0.34, DIVE_Z])
            k = (math.exp(-3.2 * u) - math.exp(-3.2)) / (1 - math.exp(-3.2))
            a1, h1 = math.radians(62), math.radians(dive_yaw(0.0))
            t1 = p1 + np.array([math.sin(h1) * math.cos(a1), -math.sin(a1), math.cos(h1) * math.cos(a1)])
            g = smooth(u * 1.15)
            return Cam(p1 + (p0 - p1) * k, w["tgt"] * (1 - g) + t1 * g, w["fov"] + (DIVE_FOV - w["fov"]) * u ** 2)
        # the pull back out: from just outside the glass to the wide shot
        u = smoother((t - self.pull0) / (self.pull1 - self.pull0))
        tgt = np.array([0.2, -DEEP + 0.5, -0.4]) * (1 - u) + w["tgt"] * u
        dist = 3.4 * (w["dist"] / 3.4) ** u
        drift = 1.6 * smooth((t - self.pull1) / 5.0)
        return orbit_cam(tgt, dist, 5 + (w["yaw"] - 5) * u + drift, 12 + (w["pitch"] - 12) * u,
                         46 + (w["fov"] - 46) * u)

    def dive_cam(self, t: float) -> Cam:
        d = self.readout(t)
        y = -max(0.0, d - LOOK * smooth(d / 0.5))
        pitch = 62 + (DIVE_PITCH - 62) * smoother((t - self.plunge) / 1.0)
        sway = 2.2 * math.sin(0.55 * t) + 1.0 * math.sin(1.13 * t + 1.0)
        x = DIVE_X + 0.03 * math.sin(0.37 * t)
        return Cam.look((x, y, DIVE_Z), dive_yaw(d) + sway, pitch, DIVE_FOV)

    def lamp(self, t: float) -> float:
        return smooth((self.readout(t) - 0.5) / 0.9)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    F = fields_x()
    clips = [(plan.hook_at, lines["hook"])] + [(plan.at[k], lines[k]) for k in KEYS] + \
        [(plan.payoff_at, lines["payoff"])]
    caps = []
    for k in KEYS:
        caps += kit.captions(plan.at[k], lines[k], SCRIPT[k][1])
    caps += kit.captions(plan.payoff_at, lines["payoff"], SCRIPT["payoff"][1])

    models = {k for k in CREATURES if model_poses(MODELS[k][0]) > 0}
    sprites = {k: v[0]() for k, v in CREATURES.items() if k not in models}       # drawn fallbacks
    sprite_px = {k: np.asarray(v, np.float32) for k, v in sprites.items()}
    f_tag, f_num = kit.sans(30, "bold"), kit.sans(48, "black")
    f_small, f_read = kit.sans(27, "bold"), kit.sans(88, "black")
    tags = {k: text_sprite([(title, WHITE, f_tag), (lab, GOLD, f_num)], align="centre")
            for k, d, title, lab in MARKERS}
    # the Titanic lies in another ocean: say so on the picture
    tags["titanic"] = text_sprite([("TITANIC WRECK", WHITE, f_tag), ("3,800 m", GOLD, f_num),
                                   ("lies in the North Atlantic \u00b7 shown here for depth", MUTED, kit.sans(24, "bold"))],
                                  align="centre")
    ev_tag = text_sprite([("MOUNT EVEREST", WHITE, f_tag), ("8,849 m tall", MUTED, f_small)])
    gap_tag = text_sprite([("2 km", GOLD, kit.sans(66, "black")), ("of water", WHITE, f_small),
                           ("above the peak", WHITE, f_small)])
    deep_tag = text_sprite([("CHALLENGER DEEP", WHITE, f_small), ("10,935 m", GOLD, kit.sans(36, "black"))],
                           align="centre")
    beams = lamp_beams()
    vy, vx = np.mgrid[0:H, 0:W].astype(np.float32)
    vignette = (1 - 0.22 * np.clip(((vx - W / 2) / (W * 0.62)) ** 2 + ((vy - H * 0.52) / (H * 0.62)) ** 2, 0, 1) ** 1.3)[..., None]
    # Everest's summit and the trench's deepest point on the front cut
    Fn = fields()
    ip, kp = np.unravel_index(int(np.argmax(Fn["S"])), Fn["S"].shape)
    peak_x, peak_z = float(Fn["xs"][ip]), float(Fn["zs"][kp])
    fx = np.linspace(-1.5, 1.5, 300)
    fh = height_np(F, fx, np.full_like(fx, Z0), 0.0)
    deep_pt = (float(fx[int(np.argmin(fh))]), float(fh.min()), Z0)

    rng = np.random.default_rng(seed)
    n_snow = 2400
    box = np.array([2.6, 2.6, 2.6])
    pts = rng.uniform(0, 1, (n_snow, 3)) * box
    psize = rng.uniform(0.0035, 0.009, n_snow) * rng.choice([1, 1, 1, 2.0], n_snow)
    pbright = rng.uniform(0.35, 1.0, n_snow)
    n_bio = 170
    bio = rng.uniform(0, 1, (n_bio, 3)) * box
    bio_ph = rng.uniform(0, 6.3, n_bio)
    bio_w = rng.uniform(1.2, 2.6, n_bio)

    # ---------------- the outside view's lines and labels ----------------
    def cut_overlays(img: Image.Image, cam: Cam, rise: float, a: float) -> None:
        """The waterline and the seabed along the cut, anti-aliased, so they never shimmer."""
        surf, ctx = _ctx()

        def stroke(P, rgba, wdt):
            x, y, z = cam.project(np.asarray(P, np.float64))
            if (z <= 0.05).any():
                return
            ctx.new_path()
            ctx.move_to(x[0], y[0])
            for xi, yi in zip(x[1:], y[1:]):
                ctx.line_to(xi, yi)
            ctx.set_source_rgba(rgba[0], rgba[1], rgba[2], rgba[3] * a)
            ctx.set_line_width(wdt)
            ctx.stroke()
        xs = np.linspace(-16.0, 16.0, 700)
        zc = np.full_like(xs, Z0)
        stroke(np.stack([xs, np.zeros_like(xs), zc], 1), (0.96, 0.95, 0.92, 0.42), 2.0)          # the waterline
        stroke(np.stack([xs, height_np(F, xs, zc, rise), zc], 1), (0.90, 0.82, 0.66, 0.50), 2.0)    # the seabed
        _over(img, surf)

    def cut_labels(img: Image.Image, cam: Cam, rise: float, a: float) -> None:
        """The summit, the water above it, and the trench's deepest point."""
        if a <= 0.01:
            return
        peak_y = float(everest_y(1.0, rise))
        sx, sy, _ = cam.project([(peak_x, peak_y, peak_z), (peak_x, 0.0, peak_z), deep_pt])
        surf, ctx = _ctx()
        g = [c / 255 for c in GOLD]
        ya, yb = sy[1] + 5, sy[0] - 12
        ctx.set_source_rgba(0, 0, 0, 0.35 * a)                    # a soft dark underlay
        ctx.set_line_width(9)
        ctx.move_to(sx[0], ya)
        ctx.line_to(sx[0], yb)
        ctx.stroke()
        ctx.set_source_rgba(*g, a)
        ctx.set_line_width(4.5)
        ctx.move_to(sx[0], ya)
        ctx.line_to(sx[0], yb)
        for yy in (ya, yb):
            ctx.move_to(sx[0] - 17, yy)
            ctx.line_to(sx[0] + 17, yy)
        ctx.stroke()
        ctx.arc(sx[0], sy[0], 5.5, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(0.96, 0.94, 0.9, 0.7 * a)             # leaders
        ctx.set_line_width(1.8)
        ctx.move_to(sx[0] - 9, sy[0] + 6)
        ctx.line_to(sx[0] - 96, sy[0] + 66)
        ctx.move_to(sx[2], sy[2] + 6)
        ctx.line_to(sx[2], sy[2] + 30)
        ctx.stroke()
        ctx.arc(sx[2], sy[2], 5, 0, 2 * math.pi)
        ctx.set_source_rgba(*g, a)
        ctx.fill()
        _over(img, surf)
        blit(img, gap_tag, sx[0] + 14, (ya + yb) / 2 - gap_tag.size[1] / 2, a)
        blit(img, ev_tag, sx[0] - 96 - ev_tag.size[0] + 18, sy[0] + 66 - 44, a)
        blit(img, deep_tag, sx[2] - deep_tag.size[0] / 2, sy[2] + 14, a)

    # ---------------- inside the water ----------------
    def particles(arr: np.ndarray, cam: Cam, cam_prev: Cam, t: float, depth: float, lamp: float,
                  alpha: float) -> None:
        """Marine snow, streaked by the camera's own motion, and bioluminescence."""
        if alpha <= 0.01:
            return
        centre = cam.pos + cam.f * 1.3
        rel = ((pts + t * np.array([0.012, -0.035, 0.008]) - (centre - box / 2)) % box) - box / 2
        P = centre + rel
        edge = np.clip((box[0] / 2 - np.abs(rel).max(axis=1)) / 0.3, 0, 1)   # fade at the wrap: no pops
        x1, y1, z1 = cam.project(P)
        x0, y0, z0 = cam_prev.project(P)
        ok = (z1 > 0.1) & (z0 > 0.1) & (x1 > -60) & (x1 < W + 60) & (y1 > -60) & (y1 < H + 60)
        v = P - cam.pos
        dist = np.linalg.norm(v, axis=1)
        sun = math.exp(-depth / 0.3)
        bm = beams[np.clip(y1, 0, H - 1).astype(int), np.clip(x1, 0, W - 1).astype(int)]
        lit = 0.30 * sun + 0.05 + lamp * 1.7 * bm * np.exp(-dist * 0.5)
        near = np.clip((z1 - 0.1) / 0.25, 0, 1)
        a = pbright * edge * near * np.exp(-0.7 * dist) * lit * alpha
        ok &= a > 0.012
        px = H / (2 * cam.t)
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
        ctx = cairo.Context(surf)
        ctx.set_antialias(cairo.ANTIALIAS_BEST)
        ctx.set_operator(cairo.OPERATOR_ADD)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for i in np.where(ok)[0]:
            wpx = min(5.0, max(1.1, psize[i] * px / z1[i]))
            ln = math.hypot(x1[i] - x0[i], y1[i] - y0[i])
            ai = min(1.0, a[i] * (wpx + 2.0) / (wpx + 2.0 + 0.55 * ln) * 1.5)
            ctx.set_source_rgb(0.80 * ai, 0.90 * ai, 0.96 * ai)
            ctx.set_line_width(wpx)
            ctx.move_to(x0[i], y0[i])
            ctx.line_to(x1[i] + 0.01, y1[i])
            ctx.stroke()
        if 0.3 < depth < 8.0:
            zone = smooth((depth - 0.3) / 0.6) * (1 - smooth((depth - 6.8) / 1.2))
            relb = ((bio - (centre - box / 2)) % box) - box / 2
            pb = centre + relb
            eb = np.clip((box[0] / 2 - np.abs(relb).max(axis=1)) / 0.3, 0, 1)
            bx, by, bz = cam.project(pb)
            pulse = (0.5 + 0.5 * np.sin(bio_w * t + bio_ph)) ** 3
            ab = eb * pulse * zone * np.exp(-0.55 * np.linalg.norm(pb - cam.pos, axis=1)) * alpha
            for i in np.where((bz > 0.25) & (ab > 0.02))[0]:
                r = min(30.0, max(5.0, 0.016 * px / bz[i]))
                g = cairo.RadialGradient(bx[i], by[i], 0, bx[i], by[i], r)
                g.add_color_stop_rgb(0, 0.50 * ab[i], 1.0 * ab[i], 0.92 * ab[i])
                g.add_color_stop_rgb(0.22, 0.16 * ab[i], 0.52 * ab[i], 0.50 * ab[i])
                g.add_color_stop_rgb(1, 0, 0, 0)
                ctx.set_source(g)
                ctx.arc(bx[i], by[i], r, 0, 2 * math.pi)
                ctx.fill()
        surf.flush()
        arr += np.ndarray((H, W, 4), np.uint8, surf.get_data())[..., 2::-1]

    def sun_shafts(arr: np.ndarray, t: float, depth: float) -> None:
        k = math.exp(-depth / 0.16)
        if k < 0.02:
            return
        hh, ww = 240, 135
        yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
        u, v = xx / ww - 0.5, yy / hh
        s = (u + 0.1) / (0.35 + v)                   # rays fanning out from above the frame
        rays = np.zeros_like(u)
        for f, ph, sp, amp in ((9, 0.3, 0.21, 1.0), (15, 1.9, -0.17, 0.7), (23, 4.1, 0.29, 0.45), (5, 2.6, 0.09, 0.8)):
            rays += amp * np.clip(np.sin(f * s + ph + sp * t), 0, 1) ** 3
        ray = rays / 2.2 * np.clip(1.1 - v * 1.25, 0, 1) ** 1.5 * k
        ray = np.asarray(Image.fromarray(np.clip(ray * 255, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC),
                         np.float32) / 255
        arr += ray[..., None] * np.array([96, 150, 168], np.float32)

    def creatures(img: Image.Image, cam: Cam, t: float, depth: float, lamp: float) -> None:
        base = to_np(fog_col(depth, _DIVE_C))
        for k, (_, ww, side, ahead) in CREATURES.items():
            d = MD[k]
            gap = abs(d - depth)
            if gap > 2.4:
                continue
            bob = 0.012 * math.sin(0.9 * t + d)
            P = ahead_of(d, ahead, side + 0.02 * math.sin(0.5 * t + d)) + np.array([0.0, bob, 0.0])
            sx, sy, zc = cam.project([P])
            if zc[0] < 0.15:
                continue
            wpx = ww * H / (2 * cam.t * zc[0])
            dist = float(np.linalg.norm(P - cam.pos))
            T = math.exp(-0.09 * dist)
            light = min(1.25, 1.05 * math.exp(-d / 0.9) + 0.20 + lamp * 1.0)
            if k in models:
                name, hold, tint, soft = MODELS[k]
                spr, sa = model_pose(name, (int(round(t * FPS)) // hold) % model_poses(name), tint, soft)
            else:
                spr, sa = sprites[k], sprite_px[k]
            rgb = sa[..., :3] * (light * T) + base * (1 - T)
            tinted = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), sa[..., 3]]).astype(np.uint8), "RGBA")
            hpx = wpx * spr.size[1] / spr.size[0]
            if k == "titanic" and k in models:          # a tall picture: its ship sits below its middle
                sy = sy + 0.13 * hpx
            vis = smooth((2.4 - gap) / 0.6) * smooth((depth - 0.3 * d) / (0.3 * d)) * smooth((sy[0] - 400) / 200)
            blit(img, tinted, sx[0] - wpx / 2, sy[0] - hpx / 2, vis, width=wpx)
            win = min(0.75, 0.3 * d + 0.05)
            near = vis * smooth((win - gap) / (0.5 * win)) * (1 - smooth((depth - d - 0.02 * (1 + d)) / (0.08 * (1 + d))))
            tag = tags[k]
            # the diver's label sits over the swimmer, clear of the bubble trail
            drop, cx_f = {"scuba": (0.31, 0.40), "titanic": (0.25, 0.50)}.get(k, (0.0, 0.5)) if k in models else (0.0, 0.5)
            ty = sy[0] - hpx / 2 + drop * hpx - tag.size[1] + 4
            near *= smooth((ty - 380) / 60)                      # never over the captions
            if near > 0.01:
                tx = min(W - 30 - tag.size[0], max(30.0, sx[0] + (cx_f - 0.5) * wpx - tag.size[0] / 2))
                blit(img, tag, tx, ty, near)

    def ring_marks(img: Image.Image, cam: Cam, depth: float) -> None:
        """The sunlight and midnight lines: rings the camera sinks through."""
        for k in ("midnight",):
            d = MD[k]
            a = smooth((0.62 - (d - depth)) / 0.3) * (1 - smooth((depth - d) / 0.2))
            if a <= 0.01:
                continue
            th = np.linspace(0, 2 * math.pi, 220)
            c = ahead_of(d, 1.45)
            P = np.stack([c[0] + 0.36 * np.cos(th), np.full_like(th, -d), c[2] + 0.36 * np.sin(th)], 1)
            x, y, z = cam.project(P)
            if (z < 0.1).any():
                continue
            surf, ctx = _ctx()
            ctx.move_to(x[0], y[0])
            for xi, yi in zip(x[1:], y[1:]):
                ctx.line_to(xi, yi)
            ctx.close_path()
            ctx.set_source_rgba(0.96, 0.93, 0.86, 0.6 * a)
            ctx.set_line_width(2.2)
            ctx.stroke()
            _over(img, surf)
            tag = tags[k]
            cx_, cy_, _ = cam.project([c])
            blit(img, tag, cx_[0] - tag.size[0] / 2, cy_[0] - tag.size[1] / 2, a)

    def floor_mark(img: Image.Image, cam: Cam, t: float) -> None:
        a = smooth((t - plan.arr["bottom"] + 0.15) / 0.4)
        if a <= 0.01:
            return
        pz_ = DIVE_Z + 1.2
        px_ = 0.35 * math.sin(0.45 * pz_ + 0.4)          # on the trench's axis
        P = [(px_, float(height_np(F, np.array([px_]), np.array([pz_]), 0.0)[0]), pz_)]
        x, y, z = cam.project(P)
        if z[0] < 0.1:
            return
        surf, ctx = _ctx()
        g = [c / 255 for c in GOLD]
        ctx.set_source_rgba(0.96, 0.94, 0.9, 0.7 * a)
        ctx.set_line_width(1.8)
        ctx.move_to(x[0], y[0] - 8)
        ctx.line_to(x[0], y[0] - 70)
        ctx.stroke()
        ctx.arc(x[0], y[0], 6, 0, 2 * math.pi)
        ctx.set_source_rgba(*g, a)
        ctx.fill()
        _over(img, surf)
        tag = tags["bottom"]
        blit(img, tag, x[0] - tag.size[0] / 2, y[0] - 70 - tag.size[1] + 14, a)

    def readout(img: Image.Image, t: float, a: float) -> None:
        if a <= 0.01:
            return
        from .star_ladder import fixed_digits, label

        s = f"{plan.readout(t) * 1000:,.0f} m"
        label(img, W / 2, 140, [("DEPTH", MUTED, f_small)], "centre", a)
        gold = t >= plan.arr["bottom"] - 0.02
        fixed_digits(img, W / 2, 218, s, f_read, GOLD if gold else WHITE, a)

    # ---------------- frames ----------------
    def outside(t: float, rise: float) -> Image.Image:
        cam = plan.outside_cam(t)
        near = smooth(((t - plan.fly0) / (plan.plunge - plan.fly0) - 0.4) / 0.4) if t < plan.plunge + 0.3 else 0.0
        # full sharpness for the held wide shots; the fast moves do not need it
        moving = plan.fly0 + 0.35 < t < plan.pull1 - 0.5
        img = to_image(grade(render_cutaway(F, cam, rise, t, ss=1.0 if moving else 1.25, near=near), 0.45))
        if t < plan.plunge + 0.3:
            ea = 1 - smooth((t - plan.fly0 - 0.3) / 0.7)
        else:
            ea = smooth((t - plan.pull0 - 0.5) / 0.9)
        if ea > 0.02:
            cut_overlays(img, cam, rise, ea)
        la = (1 - smooth((t - plan.rew) / 0.35)) if t < plan.plunge else smooth((t - plan.rise1 + 0.45) / 0.6)
        cut_labels(img, cam, rise, la)
        return img

    def inside(t: float) -> Image.Image:
        cam = plan.dive_cam(t)
        cam_prev = plan.dive_cam(t - 0.5 / FPS)
        depth = plan.readout(t)
        lamp = plan.lamp(t)
        still = abs(plan.readout(t + 0.05) - plan.readout(t - 0.05)) < 0.004     # resting on a record
        arr = render_dive(F, cam, 0.0, t, depth, lamp, ss=1.25 if still and depth > 1.6 else 1.0)
        if render_dive.centre is not None:
            pc = cam.pos + cam.f * render_dive.centre
            qx, qy, qz = plan.dive_cam(t - 1.0 / FPS).project([pc])
            bx_, by_ = abs(float(qx[0]) - W / 2) * 0.3, abs(float(qy[0]) - H / 2) * 0.3
            if max(bx_, by_) > 0.35:
                from scipy.ndimage import gaussian_filter

                arr = gaussian_filter(arr, (by_, bx_, 0), mode="nearest")
        sun_shafts(arr, t, depth)
        arr += beams[..., None] * (lamp * np.array([24, 44, 58], np.float32))
        particles(arr, cam, cam_prev, t, depth, lamp, smooth((t - plan.plunge) / 0.3))
        img = to_image(grade(arr * vignette))
        ring_marks(img, cam, depth)
        creatures(img, cam, t, depth, lamp)
        floor_mark(img, cam, t)
        fl = kit.flash(t, plan.plunge + 0.05, 0.17)              # the plunge: a wash of foam
        if fl > 0.01:
            a2 = np.asarray(img, np.float32) * (1 - 0.6 * fl) + np.array([206, 232, 240], np.float32) * 0.6 * fl
            img = Image.fromarray(np.clip(a2, 0, 255).astype(np.uint8))
        return img

    def frame(t: float) -> Image.Image:
        rise = plan.rise(t)
        if t < plan.plunge - 0.14:
            img = outside(t, rise)
        elif t < plan.plunge + 0.12:
            img = Image.blend(outside(t, rise), inside(max(t, plan.plunge)), smooth((t - plan.plunge + 0.14) / 0.26))
        elif t < plan.pull0:
            img = inside(t)
        elif t < plan.pull0 + plan.xfade:
            img = Image.blend(inside(t), outside(t, rise), smooth((t - plan.pull0) / plan.xfade))
        else:
            img = outside(t, rise)
        readout(img, t, smooth((t - plan.plunge - 0.2) / 0.4) * (1 - smooth((t - plan.pull0 - 0.1) / 0.45)))
        if t < plan.rew + 0.4:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            kit.hook(img, HOOK, t, t0=HOOK_T0, alpha=ha, size=64, ys=HOOK_YS)
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        m = snd.Mixer(total)
        m.add(0.0, deep_bed(total, plan.readout), 0.40)
        m.add(0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7)], dur=3.6), 0.5)
        m.add(plan.rew - 0.05, rumble(0.9)[::-1].copy(), 0.35)                       # Everest sinking away
        m.add(plan.fly0, whoosh(plan.plunge - plan.fly0 + 0.1, 200, 900, seed=3), 0.30)
        m.add(plan.plunge - 0.03, splash(), 0.75)
        notes = {"scuba": 12, "whale": 9, "titanic": 7, "fish": 4, "bottom": 0}
        prev = plan.plunge
        for i, k in enumerate(KEYS):
            a = plan.arr[k]
            if a - prev > 0.9:
                m.add(prev + 0.15, whoosh(a - prev - 0.15, 420, 110, seed=20 + i), 0.16)
            m.add(a - 0.02, snd.pluck(snd.scale_freq(notes[k]), dur=1.6, bright=0.5), 0.36)
            prev = a
        m.add(plan.arr["bottom"] - 0.02, snd.thud(52, 0.7), 0.6)
        m.add(plan.pull0, whoosh(plan.pull1 - plan.pull0, 120, 520, seed=41), 0.24)
        m.add(plan.rise0, rumble(plan.rise1 - plan.rise0 + 0.2), 0.55)
        m.add(plan.rise1 - 0.05, snd.chord([snd.scale_freq(i) for i in (0, 3, 5, 7, 10)],
                                           dur=total - plan.rise1 + 0.2), 0.6)
        voice.voice_over(m, clips, bed=0.7)
        m.write(path, total)

    def cost(t: float) -> float:
        """Rough seconds to draw the frame at t (measured), for even slices."""
        if GPU:                                  # measured on an RTX 4090
            if t < plan.fly0 + 0.35 or t >= plan.pull1 - 0.5:
                return 1.2
            if t < plan.plunge + 0.12:
                return 0.5
            if t < plan.pull0:
                return 0.85 if plan.readout(t) > 10.2 else 0.6
            return 1.6 if t < plan.pull0 + plan.xfade else 1.0
        if t < plan.fly0 + 0.35:
            return 13.0
        if t < plan.plunge - 0.14:
            return 12.0
        if t < plan.plunge + 0.12:
            return 16.0
        if t < plan.pull0:
            d = plan.readout(t)
            return 1.0 if d < 1.9 else (9.0 if d < 5.5 else (8.5 if d < 10.2 else 14.5))
        if t < plan.pull0 + plan.xfade:
            return 28.0
        return 13.0

    build.plan, build.cost = plan, cost    # for stills, tests and render()
    return total, frame, sound


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    # on the GPU a few workers keep the card busy (each also composites on its own CPU core);
    # more would only queue for it
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed}, cost=build.cost,
                      max_workers=GPU_WORKERS if GPU else None)
