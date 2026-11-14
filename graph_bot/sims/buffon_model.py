"""Buffon's needle: the drops, their motion and the camera, as plain numpy.

Shared by the sim (graph_bot/sims/buffon.py, which counts and writes the text)
and the Blender scene (scripts/blender/buffon_scene.py, which renders the
floor and the needles). Blender loads this file by its path, so it imports
nothing but math and numpy.

Units: one board is 1 wide and a needle is 1 long (so P(cross) = 2/pi).
Boards run along +Y; the cracks between them are the lines x = whole number.
A needle's final pose is (x, y, phi): its centre and its angle from +X.
It crosses a crack when its ends fall on different boards.
"""
from __future__ import annotations

import math

import numpy as np

L = 1.0                     # needle length = board width
R_NEEDLE = 0.0125           # needle radius (a 40 mm sewing needle is about 1 mm thick)


def crosses(x: np.ndarray, phi: np.ndarray) -> np.ndarray:
    h = 0.5 * L * np.abs(np.cos(phi))
    return np.floor(x - h) != np.floor(x + h)


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def smoother(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


# --------------------------------------------------------------------------- #
# The drops
# --------------------------------------------------------------------------- #
def make_drops(n: int, seed: int, region, first_box, n_first: int):
    """Random final poses. region = (x0, x1, y0, y1): where needles may land
    (whole boards across). The first n_first are placed inside first_box (also
    whole boards across, so where a needle sits across a board is still uniform:
    which board it lands on does not change whether it crosses)."""
    rng = np.random.default_rng(seed)
    x0, x1, y0, y1 = region
    x = rng.uniform(x0, x1, n)
    y = rng.uniform(y0, y1, n)
    phi = rng.uniform(0, math.pi, n)
    fx0, fx1, fy0, fy1 = first_box
    k = min(n_first, n)
    frac = x[:k] - np.floor(x[:k])
    x[:k] = rng.integers(int(fx0), int(fx1), k) + frac
    y[:k] = rng.uniform(fy0, fy1, k)
    # the needles that land later lie on top of the earlier ones
    z = R_NEEDLE + np.arange(n) * (0.9 * R_NEEDLE / n) * 2.0
    tilt = rng.uniform(0.18, 0.42, n) * rng.choice([-1, 1], n)   # how steeply it comes down, end first
    spin = rng.uniform(-1.4, 1.4, n)                              # how much it turns in the air
    hop = rng.uniform(0.6, 1.0, n)
    return dict(x=x, y=y, phi=phi, z=z, tilt=tilt, spin=spin, hop=hop, hit=crosses(x, phi))


def schedule(n: int, t_first: list[float], rain0: float, rain1: float, power: float = 2.6) -> np.ndarray:
    """Landing times (story seconds): the first few by hand, the rest in an
    accelerating rain from rain0 to rain1 (most of them near the end)."""
    k = len(t_first)
    u = (np.arange(n - k) + 1) / (n - k)
    rest = rain0 + (rain1 - rain0) * u ** (1 / power)
    return np.concatenate([np.asarray(t_first, float), rest])


def fall_time(T: np.ndarray, slow_until: float, slow: float, fast: float, blend: float = 3.0) -> np.ndarray:
    """How long each needle is in the air: slow motion for the first ones."""
    u = np.clip((T - slow_until) / blend, 0, 1)
    return slow + (fast - slow) * smooth(u)


SETTLE = 0.55               # seconds from first touch to lying still (scaled by the fall's slow motion)


def poses(d: dict, T: np.ndarray, D: np.ndarray, s: float):
    """Every needle at story time s: (visible, centre (n,3), direction (n,3), up-tilt, hot 0..1).

    In the air (s < T): it drops from high up with gravity, one end lower,
    turning slowly. Then the low end strikes, it slaps down flat with a small
    hop and settles exactly on its final pose."""
    n = len(T)
    vis = s >= T - D
    a = np.clip((s - (T - D)) / D, 0, 1)                     # 0 as it comes into view .. 1 at first touch
    slow = D / D.min()                                       # slow-motion factor, 1 for the fastest
    tau = np.maximum(0.0, s - T) / (SETTLE * np.sqrt(slow))  # 0 .. 1 while settling
    falling = s < T
    h0 = np.where(slow > 1.5, 1.3, 7.0)                       # the slow-motion ones fall in shot all the way
    # height of the centre above its resting height, and the tilt (radians)
    lift_air = h0 * (1 - (0.3 * a + 0.7 * a * a)) + 0.5 * L * np.abs(np.sin(d["tilt"]))
    tilt_air = d["tilt"] * (1 + 0.6 * (1 - a))
    # settling: the tilt falls to zero with one small bounce
    bounce = np.abs(np.cos(np.pi * 1.5 * np.minimum(tau, 1))) * np.exp(-3.2 * tau)
    tilt_set = d["tilt"] * 0.55 * d["hop"] * bounce * (tau < 1)
    lift_set = 0.5 * L * np.abs(np.sin(tilt_set)) + 0.06 * d["hop"] * np.sin(np.pi * np.clip(tau / 0.45, 0, 1)) * (tau < 0.45)
    lift = np.where(falling, lift_air, lift_set)
    tilt = np.where(falling, tilt_air, tilt_set)
    yaw = d["phi"] + d["spin"] * (1 - a) ** 2 * falling
    c = np.stack([d["x"], d["y"], d["z"] + lift], 1)
    ct = np.cos(tilt)
    dirn = np.stack([np.cos(yaw) * ct, np.sin(yaw) * ct, np.sin(tilt)], 1)
    hot = d["hit"] * smooth((s - T - 0.12 * np.sqrt(slow)) / (0.35 * np.sqrt(slow)))
    return vis, c, dirn, hot


# --------------------------------------------------------------------------- #
# Camera: keyframes (video seconds) of position, look-at point, lens (mm), f-stop
# --------------------------------------------------------------------------- #
def camera(keys, t: float):
    """keys: [(t, (px,py,pz), (tx,ty,tz), lens, fstop, focus_dist or 0)], eased between."""
    if t <= keys[0][0]:
        k = keys[0]
        return np.array(k[1], float), np.array(k[2], float), k[3], k[4]
    for k0, k1 in zip(keys, keys[1:]):
        if t <= k1[0]:
            u = float(smoother((t - k0[0]) / (k1[0] - k0[0])))
            p = np.array(k0[1], float) * (1 - u) + np.array(k1[1], float) * u
            q = np.array(k0[2], float) * (1 - u) + np.array(k1[2], float) * u
            return p, q, k0[3] + (k1[3] - k0[3]) * u, math.exp(math.log(k0[4]) * (1 - u) + math.log(k1[4]) * u)
    k = keys[-1]
    return np.array(k[1], float), np.array(k[2], float), k[3], k[4]


def story_time(tmap, t: float) -> float:
    """Video time -> story time (the rewind runs the rain backwards)."""
    return float(np.interp(t, tmap[0], tmap[1]))
