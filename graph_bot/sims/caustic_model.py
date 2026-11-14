"""Light reflected inside a cup, traced photon by photon (numpy, or CuPy on the GPU).

The cup's inside is a cylinder of radius 1 standing on the coffee's surface
(z = 0); its wall rises to the rim at z = HW. Light comes in either as
sunlight (parallel rays) or from a small lamp (a point). Each photon enters,
reflects off the glazed wall (Fresnel reflectance of glass-like glaze, up to
three times) and is collected where it lands on the coffee. Photons that land
without touching the wall are direct light, which Blender renders itself; the
map returned here holds only the reflected light, as irradiance relative to
the light's own strength (Blender sun: W/m2 at normal incidence; lamp: its
radiant intensity in W/sr). The bright curve in it is the caustic: a nephroid
for sunlight, a cardioid for a lamp on the rim.

Also: the ideal curves, for drawing over the picture, and single rays for the
explanation (their horizontal paths).
"""
from __future__ import annotations

import math

import numpy as np

try:                                  # the GPU when there is one
    import cupy as _cp
    _cp.zeros(1)
    xp = _cp
except Exception:                     # pragma: no cover
    xp = np

HW = 0.45                             # wall above the coffee, in cup radii (1.8 cm in a 4 cm-radius mug)
GLAZE_N = 1.50


def fresnel(cos_i, n: float = GLAZE_N):
    """Unpolarised reflectance of a smooth dielectric (the glaze)."""
    c = xp.clip(cos_i, 0.0, 1.0)
    s2 = 1 - c * c
    ct = xp.sqrt(xp.clip(1 - s2 / (n * n), 0, 1))
    rs = ((c - n * ct) / (c + n * ct)) ** 2
    rp = ((ct - n * c) / (ct + n * c)) ** 2
    return 0.5 * (rs + rp)


def sun_dir(el_deg: float, az_deg: float) -> np.ndarray:
    """Unit vector towards the sun (az measured from +X towards +Y)."""
    e, a = math.radians(el_deg), math.radians(az_deg)
    return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def _trace(p, d, w, res: int, bounces: int = 3):
    """Follow photons (p, d, w on xp) through up to `bounces` wall reflections;
    splat the ones that land on the coffee after at least one reflection."""
    img = xp.zeros((res, res), xp.float64)
    reflected = xp.zeros(p.shape[0], bool)
    alive = xp.ones(p.shape[0], bool)
    for _ in range(bounces + 1):
        dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
        px_, py_, pz = p[:, 0], p[:, 1], p[:, 2]
        a = dx * dx + dy * dy
        b = 2 * (px_ * dx + py_ * dy)
        c = px_ * px_ + py_ * py_ - 1.0
        disc = xp.sqrt(xp.clip(b * b - 4 * a * c, 0, None))
        t_wall = xp.where(a > 1e-12, (-b + disc) / (2 * xp.maximum(a, 1e-12)), xp.inf)
        t_liq = xp.where(dz < 0, -pz / xp.where(dz < 0, dz, -1.0), xp.inf)
        hit_liq = alive & (t_liq <= t_wall)
        land = hit_liq & reflected
        if bool(land.any()):
            q = p[land] + d[land] * t_liq[land][:, None]
            ix = xp.clip(((q[:, 0] + 1) * 0.5 * res).astype(xp.int64), 0, res - 1)
            iy = xp.clip(((q[:, 1] + 1) * 0.5 * res).astype(xp.int64), 0, res - 1)
            xp.add.at(img, (iy, ix), w[land])
        alive = alive & ~hit_liq
        q = p + d * xp.where(xp.isfinite(t_wall), t_wall, 0)[:, None]
        alive = alive & (q[:, 2] < HW) & xp.isfinite(t_wall)          # above the rim: it leaves the cup
        if not bool(alive.any()):
            break
        n = -xp.stack([q[:, 0], q[:, 1], xp.zeros_like(q[:, 0])], 1)  # inward normal
        dn = xp.sum(d * n, 1)
        w = w * fresnel(-dn)
        d = d - 2 * dn[:, None] * n
        p = q + n * 1e-6
        reflected = reflected | alive
    texel = (2.0 / res) ** 2
    return img / texel


def sun_map(el_deg: float, az_deg: float, n: int = 20_000_000, res: int = 1024, seed: int = 1,
            sun_size_deg: float = 0.53, batch: int = 4_000_000) -> np.ndarray:
    """Reflected irradiance on the coffee from sunlight of strength 1 (W/m2 at normal incidence)."""
    s = sun_dir(el_deg, az_deg)
    rng = xp.random.default_rng(seed) if xp is not np else np.random.default_rng(seed)
    out = None
    done = 0
    # the sun's disc: small random tilts so the curve has a true (not a pixel-sharp) width
    ang = math.radians(sun_size_deg / 2)
    u = np.cross(s, [0, 0, 1.0]); u /= np.linalg.norm(u)
    v = np.cross(s, u)
    while done < n:
        k = min(batch, n - done)
        r = xp.sqrt(rng.random(k))
        th = rng.random(k) * 2 * math.pi
        p = xp.stack([r * xp.cos(th), r * xp.sin(th), xp.full(k, HW)], 1)
        rr = xp.sqrt(rng.random(k)) * ang
        tt = rng.random(k) * 2 * math.pi
        dirs = (xp.asarray(s)[None] + xp.asarray(u)[None] * (rr * xp.cos(tt))[:, None]
                + xp.asarray(v)[None] * (rr * xp.sin(tt))[:, None])
        dirs = -dirs / xp.linalg.norm(dirs, axis=1, keepdims=True)
        # flux through the opening (horizontal disc of area pi) is sin(elevation) per unit area
        w = xp.full(k, math.pi * s[2] / n)
        img = _trace(p, dirs, w, res)
        out = img if out is None else out + img
        done += k
    return _to_np(out)


def lamp_map(src, aim, cone_deg: float, n: int = 20_000_000, res: int = 1024, seed: int = 2,
             batch: int = 4_000_000) -> np.ndarray:
    """Reflected irradiance from a lamp of radiant intensity 1 W/sr at `src`, lighting a
    cone of half-angle cone_deg round `aim` (like a Blender spot)."""
    src = np.asarray(src, float)
    a = np.asarray(aim, float); a /= np.linalg.norm(a)
    u = np.cross(a, [0, 0, 1.0]); u /= np.linalg.norm(u)
    v = np.cross(a, u)
    cmin = math.cos(math.radians(cone_deg))
    omega = 2 * math.pi * (1 - cmin)
    rng = xp.random.default_rng(seed) if xp is not np else np.random.default_rng(seed)
    out = None
    done = 0
    while done < n:
        k = min(batch, n - done)
        cz = 1 - rng.random(k) * (1 - cmin)                   # uniform over the cone's solid angle
        sz = xp.sqrt(xp.clip(1 - cz * cz, 0, 1))
        ph = rng.random(k) * 2 * math.pi
        dirs = (xp.asarray(a)[None] * cz[:, None] + xp.asarray(u)[None] * (sz * xp.cos(ph))[:, None]
                + xp.asarray(v)[None] * (sz * xp.sin(ph))[:, None])
        p = xp.broadcast_to(xp.asarray(src)[None], (k, 3)).copy()
        w = xp.full(k, omega / n)
        img = _trace(p, dirs, w, res)
        out = img if out is None else out + img
        done += k
    return _to_np(out)


def _to_np(a):
    return a.get() if hasattr(a, "get") else np.asarray(a)


# --------------------------------------------------------------------------- #
# The ideal curves (horizontal plane, cup radius 1)
# --------------------------------------------------------------------------- #
def nephroid(az_deg: float, m: int = 400) -> np.ndarray:
    """The caustic of parallel light coming from azimuth az: the half nephroid
    on the side away from the light, with its cusp halfway to the far wall."""
    t = np.linspace(-math.pi / 2, math.pi / 2, m)
    x = 0.25 * (3 * np.cos(t) - np.cos(3 * t))
    y = 0.25 * (3 * np.sin(t) - np.sin(3 * t))
    # in this form the light travels along -x (comes from +x); turn so it comes from az
    a = math.radians(az_deg)
    c, s = math.cos(a), math.sin(a)
    return np.stack([-(x * c - y * s), -(x * s + y * c)], 1)


def cardioid(src_angle_deg: float, m: int = 500) -> np.ndarray:
    """Caustic of a point light on the circle at angle src_angle: a cardioid. Its
    cusp is where a curved mirror focuses the light (two thirds of the way
    across, a third of a radius past the centre) and its round end touches the
    light itself."""
    t = np.linspace(0, 2 * math.pi, m)
    r = (2.0 / 3.0) * (1 - np.cos(t))                          # polar about the cusp; t = pi points at the light
    x, y = -1.0 / 3.0 - r * np.cos(t), -r * np.sin(t)            # light at (1, 0), cusp at (-1/3, 0)
    a = math.radians(src_angle_deg)
    c, s = math.cos(a), math.sin(a)
    return np.stack([x * c - y * s, x * s + y * c], 1)


def direct_sun(el_deg: float, az_deg: float, res: int = 1024) -> np.ndarray:
    """Direct sunlight on the coffee (irradiance, sun strength 1): sin(elevation) where the rim lets it in."""
    s = sun_dir(el_deg, az_deg)
    y, x = (np.mgrid[0:res, 0:res] + 0.5) / res * 2 - 1
    t = HW / s[2]
    lit = ((x + t * s[0]) ** 2 + (y + t * s[1]) ** 2 < 1) & (x * x + y * y < 1)
    return lit * s[2]


def direct_lamp(src, aim, cone_deg: float, res: int = 1024) -> np.ndarray:
    """Direct light from a lamp of intensity 1 W/sr on the coffee (no wall in the way: it sits on the rim)."""
    src = np.asarray(src, float)
    a = np.asarray(aim, float); a /= np.linalg.norm(a)
    y, x = (np.mgrid[0:res, 0:res] + 0.5) / res * 2 - 1
    v = np.stack([x - src[0], y - src[1], np.full_like(x, -src[2])], -1)
    d = np.linalg.norm(v, axis=-1)
    cos_cone = (v @ a) / d
    return np.where((cos_cone > math.cos(math.radians(cone_deg))) & (x * x + y * y < 1), src[2] / d ** 3, 0.0)


def ray_paths(src_or_sun, kind: str, count: int, spread=None, seed: int = 0, el_deg: float = 0.0):
    """Horizontal paths of `count` rays for drawing: [(entry, wall hit, landing)] in the plane.
    kind 'sun': parallel rays from azimuth src_or_sun (deg), entering across the whole opening;
    kind 'lamp': rays from the point src_or_sun (x, y) spread over angles `spread` (deg range)."""
    out = []
    if kind == "sun":
        a = math.radians(src_or_sun)
        dvec = -np.array([math.cos(a), math.sin(a)])
        perp = np.array([-dvec[1], dvec[0]])
        offs = (np.linspace(-0.98, 0.98, count) if count > 1 else np.array([0.35]))
        for o in offs:
            start = perp * o - dvec * math.sqrt(max(0.0, 1 - o * o))     # where the ray crosses the rim, sun side
            out.append(_bounce2d(start, dvec))
    else:
        src = np.asarray(src_or_sun, float)
        lo, hi = spread
        for ang in np.linspace(lo, hi, count):
            dv = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
            out.append(_bounce2d(src, dv))
    return out


def _bounce2d(p, d, reach: float = 2.2):
    """One horizontal path: from p along d to the wall, then the reflected leg (length `reach`, clipped at the wall)."""
    b = 2 * p @ d
    c = p @ p - 1
    t = (-b + math.sqrt(max(0.0, b * b - 4 * c))) / 2
    if t < 1e-6:                              # starting on the wall heading out: no hit
        t = 0.0
    q = p + d * t
    n = -q / np.linalg.norm(q)
    r = d - 2 * (d @ n) * n
    b2 = 2 * q @ r
    t2 = -b2                                  # next wall hit along r from q (c = 0 there)
    end = q + r * min(reach, max(0.0, t2))
    return p, q, end


def lamp_envelope(src2d, a0_deg: float, a1_deg: float, m: int = 1200) -> np.ndarray:
    """The true caustic of a point light at src2d inside the circle (first reflection),
    for rays leaving between angles a0..a1 (degrees): the envelope of the reflected
    lines, found where neighbouring lines cross. For a light on the rim this is
    the cardioid; a light a little inside it gives a near-cardioid."""
    src = np.asarray(src2d, float)
    a = np.radians(np.linspace(a0_deg, a1_deg, m))
    d = np.stack([np.cos(a), np.sin(a)], 1)
    b = 2 * d @ src
    c = src @ src - 1
    t = (-b + np.sqrt(b * b - 4 * c)) / 2
    q = src + d * t[:, None]
    n = -q
    r = d - 2 * np.sum(d * n, 1)[:, None] * n
    # intersect line i with line i+1: q_i + s r_i = q_j + u r_j
    q0, q1, r0, r1 = q[:-1], q[1:], r[:-1], r[1:]
    den = r0[:, 0] * r1[:, 1] - r0[:, 1] * r1[:, 0]
    w = q1 - q0
    s = (w[:, 0] * r1[:, 1] - w[:, 1] * r1[:, 0]) / np.where(np.abs(den) > 1e-12, den, 1e-12)
    return q0 + r0 * s[:, None]
