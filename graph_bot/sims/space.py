"""Shared pieces for Space in Motion episodes (vertical 1080 x 1920).

- planet positions on any date from JPL's approximate orbital elements
  (Standish, valid 1800-2050, well under a degree off), so a scene can show the
  sky as it really is on the day it talks about;
- a deep-space backdrop: warm-lit charcoal, a faint Milky Way band, static stars;
- lit planet sprites (shaded from the Sun's real direction, not a fixed gloss),
  a Sun and star sprite with soft natural bloom, and the Voyager probe;
- additive sprite caches at sub-pixel offsets, so slow motion never shimmers.

Look: Visual Direction v2.0. Light, not neon: thin lines, soft bloom, gold
only on the number that matters.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import kit
from .canvas import H, W

AU_KM = 149_597_870.7
C_KMS = 299_792.458
AU_LIGHT_S = AU_KM / C_KMS                 # 499.005 s
LIGHT_DAY_AU = 86400 / AU_LIGHT_S          # 173.14 AU
LY_AU = 63_241.077

# --------------------------------------------------------------------------- #
# Where the planets are
# --------------------------------------------------------------------------- #
# a, e, I, L, long. perihelion, long. node at J2000, then rates per century.
_ELEMENTS = {
    "mercury": [0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593,
                0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081],
    "venus": [0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255,
              0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418],
    "earth": [1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0,
              0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0],
    "mars": [1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891,
             0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343],
    "jupiter": [5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909,
                -0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106],
    "saturn": [9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448,
               -0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794],
    "uranus": [19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503,
               -0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589],
    "neptune": [30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574,
                0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664],
}
PLANETS = list(_ELEMENTS)


def helio(name: str, jd: float) -> np.ndarray:
    """Heliocentric ecliptic position (AU) of a planet on Julian date jd."""
    el = _ELEMENTS[name]
    T = (jd - 2451545.0) / 36525
    a, e, inc, L, wbar, node = [el[i] + el[i + 6] * T for i in range(6)]
    M = math.radians((L - wbar + 180) % 360 - 180)
    om, inc, node = math.radians(wbar - node), math.radians(inc), math.radians(node)
    E = M
    for _ in range(30):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    x, y = a * (math.cos(E) - e), a * math.sqrt(1 - e * e) * math.sin(E)
    co, so, cn, sn, ci, si = math.cos(om), math.sin(om), math.cos(node), math.sin(node), math.cos(inc), math.sin(inc)
    return np.array([(co * cn - so * sn * ci) * x + (-so * cn - co * sn * ci) * y,
                     (co * sn + so * cn * ci) * x + (-so * sn + co * cn * ci) * y,
                     (so * si) * x + (co * si) * y])


def ecliptic_dir(ra_deg: float, dec_deg: float) -> np.ndarray:
    """Unit vector in ecliptic coordinates for an equatorial (J2000) direction."""
    ra, de, eps = math.radians(ra_deg), math.radians(dec_deg), math.radians(23.4393)
    v = np.array([math.cos(de) * math.cos(ra), math.cos(de) * math.sin(ra), math.sin(de)])
    return np.array([v[0], v[1] * math.cos(eps) + v[2] * math.sin(eps),
                     -v[1] * math.sin(eps) + v[2] * math.cos(eps)])


def julian(y: int, mo: int, d: int, hour: float = 0.0) -> float:
    if mo <= 2:
        y, mo = y - 1, mo + 12
    A = y // 100
    B = 2 - A + A // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (mo + 1)) + d + B - 1524.5 + hour / 24


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def light_time(minutes: float) -> str:
    """'8 min', '43 min', '1 h 13 min', '4 h 4 min'."""
    m = int(round(minutes))
    if m < 60:
        return f"{max(1, m)} min"
    return f"{m // 60} h {m % 60} min"


def km_text(km: float) -> str:
    if km >= 1e12:
        return f"{km / 1e12:.1f} trillion km"
    if km >= 1e9:
        v = km / 1e9
        return f"{v:.1f} billion km" if v < 100 else f"{v:.0f} billion km"
    if km >= 1e6:
        v = km / 1e6
        return f"{v:.0f} million km"
    return f"{km:,.0f} km"


# --------------------------------------------------------------------------- #
# Backdrop
# --------------------------------------------------------------------------- #
def starfield(seed: int = 4, n: int = 1500, band_angle: float = -28.0, cx: float = W / 2,
              cy: float = 1000, warm=(40, 30, 20)) -> np.ndarray:
    """Warm-lit charcoal, a faint Milky Way band and static stars, as float RGB."""
    base = np.asarray(kit.backdrop(cx, cy, warm=warm, rad=980, cool=(14, 20, 38)), np.float32)
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # The band: soft dust along a tilted line, broken up by blurred noise.
    a = math.radians(band_angle)
    dist = (xx - W / 2) * math.sin(a) + (yy - H * 0.42) * math.cos(a)
    band = np.exp(-(dist / 260) ** 2)
    noise = Image.fromarray((rng.random((H // 8, W // 8)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    noise = np.asarray(noise.filter(ImageFilter.GaussianBlur(26)), np.float32) / 255
    dust = band * (0.55 + 0.9 * (noise - 0.5))
    base += np.clip(dust, 0, None)[..., None] * np.array([16, 15, 19], np.float32)
    # Stars: many faint, a few bright; denser inside the band.
    ss = 3
    big = Image.new("L", (W * ss, H * ss), 0)
    tint = Image.new("RGB", (W * ss, H * ss), (0, 0, 0))
    d, dt = ImageDraw.Draw(big), ImageDraw.Draw(tint)
    k = 0
    while k < n:
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        db = (x - W / 2) * math.sin(a) + (y - H * 0.42) * math.cos(a)
        if rng.random() > 0.35 + 0.65 * math.exp(-(db / 300) ** 2):
            continue
        mag = rng.pareto(2.6)
        b = min(1.0, 0.16 + 0.22 * mag)
        r = (0.55 + 0.75 * min(1.0, mag * 0.5)) * ss
        col = [(255, 244, 228), (214, 226, 255), (255, 226, 190), (240, 240, 255)][rng.integers(0, 4)]
        v = int(255 * b)
        d.ellipse((x * ss - r, y * ss - r, x * ss + r, y * ss + r), fill=v)
        dt.ellipse((x * ss - r, y * ss - r, x * ss + r, y * ss + r), fill=col)
        k += 1
    lum = np.asarray(big.resize((W, H), Image.LANCZOS), np.float32)[..., None] / 255
    col = np.asarray(tint.resize((W, H), Image.LANCZOS), np.float32)
    col = col / np.maximum(1, col.max(axis=2, keepdims=True)) * 255
    stars = lum * col
    # The brightest get a tiny soft halo (light, not glare).
    halo = np.asarray(Image.fromarray(np.clip(stars, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3)),
                      np.float32)
    return np.clip(base + stars * 0.95 + halo * 0.5, 0, 255)


# --------------------------------------------------------------------------- #
# Sprites
# --------------------------------------------------------------------------- #
class SubSprites:
    """A sprite drawn at 4 x 4 sub-pixel offsets. make(ox, oy) -> RGBA Image or
    float RGB array (additive), centred at (size/2 + ox, size/2 + oy)."""

    def __init__(self, make, size: int, additive: bool, sub: int = 4):
        self.size, self.add, self.sub = size, additive, sub
        self.cache = {(i, k): make(i / sub, k / sub) for i in range(sub) for k in range(sub)}

    def paste(self, img: Image.Image, x: float, y: float, alpha: float = 1.0) -> None:
        if alpha <= 0.003:
            return
        fx, fy = int(math.floor(x)), int(math.floor(y))
        spr = self.cache[(int((x - fx) * self.sub), int((y - fy) * self.sub))]
        x0, y0 = fx - self.size // 2, fy - self.size // 2
        if x0 >= W or y0 >= H or x0 + self.size <= 0 or y0 + self.size <= 0:
            return
        if self.add:
            # Clip to the frame, then add.
            ax0, ay0 = max(0, -x0), max(0, -y0)
            ax1, ay1 = min(self.size, W - x0), min(self.size, H - y0)
            kit.add(img, (x0 + ax0, y0 + ay0, x0 + ax1, y0 + ay1), spr[ay0:ay1, ax0:ax1] * alpha)
        else:
            if alpha < 0.999:
                a = spr.getchannel("A").point(lambda v: int(v * alpha))
                spr = spr.copy()
                spr.putalpha(a)
            img.paste(spr, (x0, y0), spr)


def lit_planet(r: float, color, light: tuple[float, float], kind: str = "rock", ox: float = 0, oy: float = 0,
               size: int | None = None, ss: int = 6) -> Image.Image:
    """A planet lit from screen direction `light` (unit 2D vector towards the Sun).
    kind: rock | earth | gas (soft bands) | ice | saturn (with rings)."""
    size = size or int(math.ceil(r * (5.2 if kind == "saturn" else 2) + 6)) // 2 * 2 + 2
    n = size * ss
    c = n / 2 + np.array([ox, oy]) * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    nx, ny = (xx + 0.5 - c[0]) / (r * ss), (yy + 0.5 - c[1]) / (r * ss)
    rr = nx * nx + ny * ny
    inside = rr <= 1
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    L = np.array([light[0], light[1], 0.45])
    L = L / np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    shade = 0.035 + 0.965 * (lam ** 0.85) * (0.75 + 0.25 * nz)       # soft terminator, limb darkening
    base = np.array(color, np.float32)
    rgb = np.ones((n, n, 3), np.float32) * base
    if kind in ("gas", "saturn"):
        bands = 0.86 + 0.14 * np.sin(ny * 13.0 + 0.6) * np.cos(ny * 4.1)
        rgb *= bands[..., None]
    if kind == "earth":
        rng = np.random.default_rng(1)
        small = rng.random((24, 24)).astype(np.float32)
        cl = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255
        land = cl > 0.62
        rgb = np.where(land[..., None], np.array([70, 112, 74], np.float32), rgb)
        clouds = np.clip((cl - 0.45) * 3, 0, 1) * (cl < 0.62) * 0.45
        rgb = rgb * (1 - clouds[..., None]) + 235 * clouds[..., None]
    out = rgb * shade[..., None]
    if kind in ("earth", "ice"):
        # A thin bright rim of atmosphere on the lit side.
        rim = np.clip((np.sqrt(rr) - 0.82) / 0.18, 0, 1) * inside * lam ** 0.5
        out += rim[..., None] * np.array([90, 140, 230], np.float32) * 0.7
    alpha = inside.astype(np.float32)
    if kind == "saturn":
        # Rings: an ellipse tilted ~ 27 degrees, the back half hidden behind the globe.
        tilt = 0.32
        rx, ry = nx, ny / tilt
        rd = np.sqrt(rx * rx + ry * ry)
        ring = ((rd > 1.35) & (rd < 2.25)).astype(np.float32) * (0.75 - 0.25 * np.cos(rd * 9))
        behind = (ny < 0) & inside
        ring = ring * ~behind
        lit = 0.45 + 0.55 * np.clip((nx * L[0] + ny * L[1]) / 2.2 + 0.6, 0, 1)
        ring_col = np.array([206, 184, 140], np.float32) * lit[..., None]
        out = out * (1 - ring[..., None]) + ring_col * ring[..., None]
        alpha = np.maximum(alpha, ring)
    rgba = np.dstack([np.clip(out, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)


def bloom(core_r: float, color, gains=((1.6, 255), (7, 120), (26, 40), (80, 12)), ox: float = 0, oy: float = 0,
          size: int = 0) -> np.ndarray:
    """A star or the Sun: a hot core and nested soft halos, as an additive float array."""
    size = size or int(gains[-1][0] * 3.2 + core_r * 2) // 2 * 2 + 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xx + 0.5 - size / 2 - ox, yy + 0.5 - size / 2 - oy)
    core = np.clip(core_r + 0.6 - d, 0, 1)
    out = core * 255
    for sig, g in gains:
        out = out + g * np.exp(-0.5 * (np.maximum(0, d - core_r) / sig) ** 2)
    col = np.array(color, np.float32) / 255
    white = np.clip(core * 1.2, 0, 1)[..., None]
    return out[..., None] * (col * (1 - white) + white)


@lru_cache(maxsize=4)
def _probe_img(scale_px: float, ss: int = 8) -> Image.Image:
    """Voyager, side-on, dish facing down (towards Earth). About 5 x scale_px wide."""
    s = scale_px * ss
    n = int(s * 6) // 2 * 2
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = n / 2, n / 2
    metal, dark, foil = (205, 208, 214, 255), (120, 124, 132, 255), (214, 170, 92, 255)
    # magnetometer boom: long and thin, up and to the right
    d.line([(cx + 0.2 * s, cy - 0.5 * s), (cx + 2.7 * s, cy - 2.2 * s)], fill=(170, 174, 182, 255), width=max(1, int(0.07 * s)))
    # RTG boom to the left, with its three generators
    d.line([(cx - 0.4 * s, cy - 0.35 * s), (cx - 1.9 * s, cy - 0.95 * s)], fill=(160, 164, 172, 255), width=max(1, int(0.08 * s)))
    for k in range(3):
        px = cx - (1.05 + 0.32 * k) * s
        py = cy - (0.62 + 0.13 * k) * s
        d.rounded_rectangle((px - 0.14 * s, py - 0.11 * s, px + 0.14 * s, py + 0.11 * s), radius=0.05 * s, fill=dark)
    # science boom down-right
    d.line([(cx + 0.35 * s, cy - 0.2 * s), (cx + 1.5 * s, cy + 0.15 * s)], fill=(160, 164, 172, 255), width=max(1, int(0.07 * s)))
    d.rectangle((cx + 1.35 * s, cy + 0.02 * s, cx + 1.7 * s, cy + 0.3 * s), fill=dark)
    # bus (gold foil) above the dish
    d.polygon([(cx - 0.42 * s, cy - 0.62 * s), (cx + 0.42 * s, cy - 0.62 * s), (cx + 0.5 * s, cy - 0.2 * s),
               (cx - 0.5 * s, cy - 0.2 * s)], fill=foil)
    # the dish, seen nearly edge-on, facing down
    # the dish, tilted towards us so it reads as a bowl facing down (to Earth)
    d.ellipse((cx - 1.75 * s, cy - 0.5 * s, cx + 1.75 * s, cy + 0.95 * s), fill=metal)
    d.ellipse((cx - 1.5 * s, cy - 0.28 * s, cx + 1.5 * s, cy + 0.85 * s), fill=(150, 154, 164, 255))
    d.ellipse((cx - 1.1 * s, cy - 0.02 * s, cx + 1.1 * s, cy + 0.72 * s), fill=(176, 180, 190, 255))
    d.line([(cx - 1.2 * s, cy + 0.6 * s), (cx, cy + 1.15 * s), (cx + 1.2 * s, cy + 0.6 * s)],
           fill=(196, 198, 204, 255), width=max(1, int(0.05 * s)))
    d.ellipse((cx - 0.12 * s, cy + 1.05 * s, cx + 0.12 * s, cy + 1.25 * s), fill=(220, 222, 228, 255))
    out = n // ss
    return im.resize((out, out), Image.LANCZOS)


def probe_sprites(scale_px: float = 14) -> SubSprites:
    base = _probe_img(scale_px)
    size = base.width + 2

    def make(ox, oy):
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        big = base.resize((base.width * 4, base.height * 4), Image.BICUBIC)
        lay = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        lay.paste(big, (int(round((ox + 1) * 4)), int(round((oy + 1) * 4))), big)
        im = lay.resize((size, size), Image.LANCZOS)
        return im
    return SubSprites(make, size, additive=False)
