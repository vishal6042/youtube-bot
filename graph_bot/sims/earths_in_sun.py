"""How many Earths fit inside the Sun? 1.3 million, but only if you melt them.

The Sun is 109.2 Earths wide, so it holds 109.2^3 = 1.30 million Earths by
volume. Round balls leave gaps. A perfect stack (the face-centred cubic
packing, oranges in a shop: 74.05%, proven best by Hales) placed inside the
Sun fits 938,086 whole Earths (counted directly; the 74% ceiling would be
964,000, but balls cannot fill the curved wall). Poured in at random they fill
about 64%: ~830,000.

Picture: a close-up of Earth pulls back to reveal the Sun; a row of 109 Earths
spans it. Then the Sun opens into a cross-section: melted Earth fills it to the
brim, drains, Earths rain in at random, then shake down into a perfect stack.
The camera dives into the stack, where the Sun's glow shines through the gaps.
The slice is schematic (every Earth cut through its centre); the numbers are
for the real 3D packing.

Hook: frame one is the finished stack with the question, then it rewinds.
"""
from __future__ import annotations

import math
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from ..config import PROJECT_ROOT
from . import canvas as cv
from . import kit
from . import sound as snd
from . import space as sp
from . import space3d as s3
from . import voice
from .canvas import GOLD, MUTED, WHITE, H, W, scale

FPS = 60
VOICE, RATE = "en-US-AndrewNeural", "+0%"   # the Space in Motion voice

K = 695_700 / 6_371          # Sun radius in Earth radii: 109.2
VOL = K ** 3                 # 1,302,097 Earths by volume
STACKED = 938_086            # FCC stack counted inside the Sun (whole Earths)
RANDOM = 830_000             # ~64% random close packing
CX, CY = 540.0, 1000.0       # the Sun's centre on screen
SUN_PX = 450.0
S_FULL = SUN_PX / K          # px per Earth radius with the whole Sun in view
S_EARTH = 160.0              # px per Earth radius in the opening close-up
S_GAP = 58.0                 # px per Earth radius inside the stack
S_END = 10.0                 # the closing shot: the top of the slice, a dome of Earths
END = (S_END, 0.0, K - (CY - 470.0) / S_END)
FULL = (S_FULL, 0.0, 0.0)
# The lone Earth, 4 of its radii outside the Sun's lower-left edge: in the
# opening close-up the Sun's limb is a glowing wall just past it.
EARTH_W = 113.5 * np.array([math.cos(math.radians(222)), math.sin(math.radians(222))])
EARTH_FAR = np.array([CX + EARTH_W[0] * S_FULL, CY - EARTH_W[1] * S_FULL])
EARTH_NEAR = np.array([CX - 60.0, CY + 300.0])
TOP_LABEL_Y, NUM_Y, SUB_Y = 130, 207, 280
LIGHT = np.array([-0.52, 0.58, 0.63])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
HOOK_T0 = -0.45
SUN_LIGHT = np.array([0.62, 0.56, 0.55])          # the lone Earth: lit from the Sun, up and to its right
SUN_LIGHT = SUN_LIGHT / np.linalg.norm(SUN_LIGHT)
CACHE = PROJECT_ROOT / "data" / "cache" / "sims"

HOOK = [[("1.3", GOLD), ("million", GOLD), ("Earths", WHITE), ("fit", WHITE)],
        [("inside", WHITE), ("the", WHITE), ("Sun.", WHITE), ("Or", WHITE), ("do", WHITE), ("they?", WHITE)]]

SCRIPT = {
    "hook": ("They say 1.3 million Earths fit inside the Sun. Not if they're round.", None),
    "wide": ("The Sun is 109 Earths wide. And 109 cubed is 1.3 million.",
             [("The Sun is", 3), ("*109 Earths* wide", 3), ("And 109 cubed", 3), ("is *1.3 million*", 3)]),
    "melt": ("But that only works if you melt the Earths down and pour them in.",
             [("But that only works", 4), ("if you melt the Earths down", 6), ("and pour them in", 4)]),
    "pour": ("Whole balls leave gaps. Tip them in at random, and about 830,000 fit.",
             [("Whole balls leave gaps", 4), ("Tip them in at random", 5), ("and about *830,000* fit", 4)]),
    "stack": ("Stack them perfectly, like oranges, and you still only get about 940,000.",
              [("Stack them perfectly,", 3), ("like oranges,", 2), ("and you still only get", 5),
               ("about *940,000*", 2)]),
    "end": ("Even then, a quarter of the Sun is just gaps.",
            [("Even then,", 2), ("a quarter of the Sun", 5), ("is just gaps", 3)]),
}


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def ease(u: float) -> float:
    return cv.ease(max(0.0, min(1.0, u)))


def _word(line, w, frac):
    try:
        return line.word_at(w)
    except KeyError:
        return line.secs * frac


# --------------------------------------------------------------------------- #
# The two packings of the slice: a perfect hexagonal stack and a random pour
# --------------------------------------------------------------------------- #
def lattice() -> np.ndarray:
    n = int(K) + 2
    pts = [(2 * i + (j % 2), j * math.sqrt(3)) for j in range(-n, n + 1) for i in range(-n, n + 1)]
    pts = np.array(pts, float)
    pts[:, 1] -= 0.4                                   # sit the rows a touch low, like a settled stack
    return pts[np.hypot(pts[:, 0], pts[:, 1]) <= K - 1.0]


def random_pack(seed: int = 11, phi: float = 0.815) -> np.ndarray:
    """Equal discs jammed at random inside the circle: start scattered and
    tiny, grow them while pushing overlaps apart, then let it settle."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"earths_in_sun_random_{seed}_{phi}.npy"
    if path.exists():
        return np.load(path)
    rng = np.random.default_rng(seed)
    n = int(phi * K * K)
    lim = K - 1.0
    r = np.sqrt(rng.random(n)) * lim
    a = rng.random(n) * 2 * math.pi
    p = np.stack([r * np.cos(a), r * np.sin(a)], -1)
    steps = 420
    for k in range(steps):
        rad = min(1.0, 0.35 + 0.65 * k / (steps * 0.6))
        tree = cKDTree(p)
        pairs = tree.query_pairs(2 * rad, output_type="ndarray")
        if len(pairs):
            d = p[pairs[:, 1]] - p[pairs[:, 0]]
            dist = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)
            push = ((2 * rad - dist) / dist * 0.5)[:, None] * d
            move = np.zeros_like(p)
            np.add.at(move, pairs[:, 0], -push)
            np.add.at(move, pairs[:, 1], push)
            p += move * 0.9
        rr = np.hypot(p[:, 0], p[:, 1])
        out = rr > lim
        p[out] *= (lim / rr[out])[:, None]
    np.save(path, p)
    return p


def match(rand: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Send each poured Earth to a nearby free place in the stack (bottom rows
    first). Returns target index per poured Earth and the leftover places."""
    tree = cKDTree(lat)
    free = np.ones(len(lat), bool)
    target = np.full(len(rand), -1)
    for i in np.argsort(rand[:, 1]):
        for k in (12, 48, 200):
            _, idx = tree.query(rand[i], k=k)
            ok = idx[free[idx]]
            if len(ok):
                target[i] = ok[0]
                free[ok[0]] = False
                break
        if target[i] < 0:
            j = np.flatnonzero(free)
            j = j[np.argmin(np.hypot(*(lat[j] - rand[i]).T))]
            target[i] = j
            free[j] = False
    return target, np.flatnonzero(free)


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
class Plan:
    def __init__(self, L: dict[str, voice.Line]):
        self.hook_at = 0.25
        self.rew = max(3.7, self.hook_at + L["hook"].secs + 0.4)
        self.rew_end = self.rew + 0.95
        self.z0 = self.rew_end + 0.25
        self.wide_at = self.z0 + 0.1
        wl = L["wide"]
        self.z1 = self.wide_at + _word(wl, "Earths", 0.25) + 0.3
        self.row0 = self.z1 - 0.15
        self.row1 = self.row0 + 1.15
        self.t_cubed = self.wide_at + _word(wl, "cubed", 0.55)
        self.t_mill = self.wide_at + _word(wl, "1.3", 0.72)
        self.melt_at = self.wide_at + wl.secs + 0.45
        ml = L["melt"]
        self.cut0 = self.melt_at + 0.05
        self.cut1 = self.cut0 + 0.8
        self.t_melt = self.melt_at + _word(ml, "melt", 0.35)
        self.fill0 = self.melt_at + _word(ml, "pour", 0.75) - 0.35
        self.fill1 = self.melt_at + ml.secs + 0.55
        self.pour_at = self.melt_at + ml.secs + 0.6
        pl = L["pour"]
        self.drain0 = self.pour_at + _word(pl, "gaps", 0.15) - 0.2
        self.drain1 = self.drain0 + 0.75
        self.pour0 = self.pour_at + _word(pl, "Tip", 0.32) - 0.15
        self.pour1 = self.pour_at + _word(pl, "830", 0.7) + 0.1
        self.stack_at = self.pour_at + pl.secs + 0.45
        sl = L["stack"]
        self.shake0 = self.stack_at + 0.1
        self.shake1 = self.shake0 + 1.7
        self.extra0 = self.shake0 + 1.2
        self.extra1 = self.stack_at + _word(sl, "940", 0.7)
        self.zg0 = self.extra1 + 0.25
        self.zg1 = self.zg0 + 1.5
        self.end_at = self.stack_at + sl.secs + 0.5
        el = L["end"]
        self.t_quarter = self.end_at + _word(el, "quarter", 0.35)
        self.t_gaps = self.end_at + _word(el, "gaps", 0.8)
        self.zg2 = self.end_at + el.secs + 0.25
        self.zg3 = self.zg2 + 1.4
        self.total = self.zg3 + 1.5

    # -- camera: (px per Earth radius, world point at the screen centre) --
    def view(self, t: float, gap_T: np.ndarray):
        gap = (S_GAP, gap_T[0] + 0.6 * math.sin((t - self.zg0) * 0.5), gap_T[1] + 120.0 / S_GAP)
        if t < self.rew:                                   # the finished image, slowly pushing in
            return END[0] * (1 + 0.035 * t / self.rew), END[1], END[2]
        if t < self.rew_end:                               # rewind: dive back to Earth
            u = ease((t - self.rew - 0.15) / (self.rew_end - self.rew - 0.15))
            return blend(END, self._earth_view(0.0), u)
        if t < self.z0:
            return self._earth_view(0.0)
        if t < self.z1:
            return self._earth_view(ease((t - self.z0) / (self.z1 - self.z0)))
        if t < self.zg0:
            return FULL
        if t < self.zg1:
            return blend(FULL, gap, ease((t - self.zg0) / (self.zg1 - self.zg0)))
        if t < self.zg2:
            return gap
        if t < self.zg3:
            return blend(gap, END, ease((t - self.zg2) / (self.zg3 - self.zg2)))
        return END[0] * (1 + 0.02 * (t - self.zg3)), END[1], END[2]

    @staticmethod
    def _earth_view(u: float):
        s = S_EARTH * (S_FULL / S_EARTH) ** u
        P = EARTH_NEAR + (EARTH_FAR - EARTH_NEAR) * u
        xc = EARTH_W[0] - (P[0] - CX) / s
        yc = EARTH_W[1] + (P[1] - CY) / s
        return s, xc, yc



def blend(a, b, u: float):
    """Zoom from view a to view b: scale moves evenly in log, and the centre
    moves so that the picture flows (no swing out and back)."""
    u = max(0.0, min(1.0, u))
    s = a[0] ** (1 - u) * b[0] ** u
    w = u if abs(a[0] - b[0]) < 1e-9 else (1 / s - 1 / a[0]) / (1 / b[0] - 1 / a[0])
    return s, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def _bilinear(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = tex.shape[:2]
    u = np.clip(u, 0, w - 1.001)
    v = np.clip(v, 0, h - 1.001)
    x0, y0 = u.astype(int), v.astype(int)
    fx, fy = (u - x0)[..., None], (v - y0)[..., None]
    return ((tex[y0, x0] * (1 - fx) + tex[y0, x0 + 1] * fx) * (1 - fy)
            + (tex[y0 + 1, x0] * (1 - fx) + tex[y0 + 1, x0 + 1] * fx) * fy)


def _fft_noise(rng, n: int, beta: float, lo: float, hi: float) -> np.ndarray:
    """Periodic noise (tiles seamlessly): white noise shaped in frequency."""
    f = np.fft.fftfreq(n)[:, None] ** 2 + np.fft.fftfreq(n)[None, :] ** 2
    f = np.sqrt(f) * n
    shape = np.where(f > 0, f, 1.0) ** (-beta / 2) * np.exp(-(f / hi) ** 2) * (1 - np.exp(-(f / lo) ** 2))
    a = np.real(np.fft.ifft2(np.fft.fft2(rng.normal(0, 1, (n, n))) * shape))
    return ((a - a.min()) / (a.max() - a.min())).astype(np.float32)


def plasma_texture(seed: int = 3, n: int = 1024) -> np.ndarray:
    """Soft turbulent noise (0..1), seamless, for the Sun's glowing interior."""
    return _fft_noise(np.random.default_rng(seed), n, 2.4, 2.0, 140.0)[..., None]


def granule_texture(seed: int = 5, n: int = 512) -> np.ndarray:
    """The Sun's surface up close: bright cells split by darker lanes (seamless)."""
    a = _fft_noise(np.random.default_rng(seed), n, 0.6, 6.0, 26.0)
    cells = 1 - np.abs(a - 0.5) * 2                    # ridges -> dark lanes between cells
    b = _fft_noise(np.random.default_rng(seed + 1), n, 2.0, 1.0, 40.0)
    return (np.clip(cells, 0, 1) ** 0.7 * 0.75 + b * 0.25)[..., None]


def plasma_colour(i: np.ndarray) -> np.ndarray:
    """Ember red -> orange -> warm white."""
    stops = np.array([[34, 6, 2], [120, 30, 6], [214, 92, 22], [255, 170, 70], [255, 226, 170]], np.float32)
    x = np.clip(i, 0, 0.999) * (len(stops) - 1)
    k = x.astype(int)
    f = (x - k)[..., None]
    return stops[k] * (1 - f) + stops[k + 1] * f


def draw_balls(arr: np.ndarray, view, P: np.ndarray, alpha: np.ndarray, rot: np.ndarray, warm: float,
               tex, light=LIGHT) -> None:
    """Every Earth at once: for each pixel, the nearest ball; shade it as a lit,
    textured sphere (clouds, atmosphere, a warm rim from the glow behind)."""
    s, xc, yc = view
    keep = alpha > 0.01
    if not keep.any():
        return
    P, alpha, rot = P[keep], alpha[keep], rot[keep]
    sx = CX + s * (P[:, 0] - xc)
    sy = CY - s * (P[:, 1] - yc)
    on = (sx > -s - 2) & (sx < W + s + 2) & (sy > -s - 2) & (sy < H + s + 2)
    if not on.any():
        return
    P, alpha, rot, sx, sy = P[on], alpha[on], rot[on], sx[on], sy[on]
    x0, x1 = max(0, int(sx.min() - s - 2)), min(W, int(sx.max() + s + 3))
    y0, y1 = max(0, int(sy.min() - s - 2)), min(H, int(sy.max() + s + 3))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    wx = xc + (xx.ravel() + 0.5 - CX) / s
    wy = yc - (yy.ravel() + 0.5 - CY) / s
    d, idx = cKDTree(P).query(np.stack([wx, wy], -1), distance_upper_bound=1.0 + 1.0 / s)
    hit = np.isfinite(d)
    if not hit.any():
        return
    flat = np.flatnonzero(hit)
    j = idx[hit]
    dx, dy = wx[hit] - P[j, 0], wy[hit] - P[j, 1]
    rho = np.minimum(d[hit], 1.0)
    cover = np.clip((1 - d[hit]) * s + 0.5, 0, 1) * alpha[j]
    nz = np.sqrt(np.clip(1 - rho * rho, 0, 1))
    lat = np.arcsin(np.clip(dy, -1, 1))
    lon = np.arctan2(dx, np.maximum(nz, 1e-4)) + rot[j]
    col = tex["earth"].sample(lon, lat, s)
    lam = dx * light[0] + dy * light[1] + nz * light[2]
    lit = np.clip(lam, 0, 1)
    soft = np.clip(lam * 0.5 + 0.5, 0, 1) ** 3
    shade = 0.12 + 0.98 * (0.66 * lit ** 0.85 + 0.34 * soft) * (0.74 + 0.26 * nz)
    col = col * np.array([0.92, 1.0, 1.16], np.float32) + np.array([0, 4, 14], np.float32)   # a touch bluer
    out = col * shade[:, None] * 1.12
    cl = np.clip(tex["clouds"].sample(lon + 0.7, lat, s)[:, 0] / 255 * 1.1, 0, 1)
    cl = cl * (0.55 + 0.3 * smooth((s - 8) / 30))                  # thinner clouds on small Earths
    out = out * (1 - cl[:, None] * 0.8) + (236 * shade * cl)[:, None]
    spec = np.clip(lam, 0, 1) ** 24 * 0.35                          # a soft sheen on the oceans
    out += (spec * 255)[:, None]
    rim = np.clip((rho - 0.72) / 0.28, 0, 1) ** 2
    out += (rim * np.clip(lam + 0.4, 0, 1))[:, None] * np.array([110, 160, 255], np.float32) * 0.5
    if warm > 0:
        bleed = 1 + 1.6 * smooth((9 - s) / 5)          # sub-pixel gaps: their glow tints the edges
        out += (rim ** 1.5 * warm * bleed)[:, None] * np.array([255, 128, 48], np.float32) * 0.42
    reg = arr[y0:y1, x0:x1].reshape(-1, 3)
    c = cover[:, None]
    reg[flat] = reg[flat] * (1 - c) + out * c
    arr[y0:y1, x0:x1] = reg.reshape(y1 - y0, x1 - x0, 3)


def draw_slice(arr: np.ndarray, view, t: float, reveal: float, level: float, glow_gain: float,
               plasma: np.ndarray, tex) -> None:
    """The opened Sun: a glowing interior (and the melted Earth, up to `level`)
    inside a circle of radius reveal x K."""
    if reveal <= 0:
        return
    s, xc, yc = view
    R = reveal * K
    x0 = max(0, int(CX + s * (-R - xc)) - 2)
    x1 = min(W, int(CX + s * (R - xc)) + 3)
    y0 = max(0, int(CY - s * (R - yc)) - 2)
    y1 = min(H, int(CY - s * (-R - yc)) + 3)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    wx = xc + (xx + 0.5 - CX) / s
    wy = yc - (yy + 0.5 - CY) / s
    rr = np.hypot(wx, wy)
    inside = np.clip((R - rr) * s + 0.5, 0, 1)
    if not inside.any():
        return
    n = plasma.shape[0]
    drift = t * 0.9
    u = (wx / (2.3 * K) + 0.5) * (n - 1) + drift
    v = (0.5 - wy / (2.3 * K)) * (n - 1) + drift * 0.4
    nz = _bilinear(plasma, u % (n - 1), v % (n - 1))[..., 0]
    nz2 = _bilinear(plasma, (u * 2.1 + 300) % (n - 1), (v * 2.1 + 200) % (n - 1))[..., 0]
    core = 1 - 0.5 * (rr / K) ** 2
    inten = core * (0.42 + 0.5 * nz + 0.22 * nz2) * glow_gain
    col = plasma_colour(inten * 0.82)
    if level > -K - 1:
        # Melted Earth: marbled blue, green and brown, a bright rippling surface.
        surf = level + 0.9 * np.sin(wx * 0.11 + t * 2.6) + 0.5 * np.sin(wx * 0.23 - t * 3.7)
        below = np.clip((surf - wy) * s * 0.5 + 0.5, 0, 1)
        if below.any():
            lon = wx / K * 6.0 + (nz - 0.5) * 5.0 + t * 0.08
            lat = np.clip(wy / K * 2.6 + (nz2 - 0.5) * 2.4, -1.4, 1.4)
            earth = tex["earth"].sample(lon, lat, s * 60)
            depth = np.clip((surf - wy) / 70, 0, 1)
            liquid = (earth * 0.42 + np.array([16, 54, 128], np.float32) * 0.72) * (1.08 - 0.5 * depth)[..., None]
            liquid += (np.clip(1 - (surf - wy) * s / 14, 0, 1) ** 2)[..., None] * np.array([150, 200, 255]) * 0.8
            liquid += (nz2[..., None] - 0.5) * 30
            col = col * (1 - below[..., None]) + liquid * below[..., None]
    reg = arr[y0:y1, x0:x1]
    reg[:] = reg * (1 - inside[..., None]) + col * inside[..., None]


def label(img, x: float, y: float, txt: str, col, fnt, alpha: float, align: str = "centre") -> None:
    if alpha <= 0.01 or not (-400 < x < W + 400 and 20 < y < H - 20):
        return
    wdt = fnt.getlength(txt)
    lx = x if align == "left" else (x - wdt if align == "right" else x - wdt / 2)
    kit.solid_text(img, 0, y, [(txt, col)], fnt, alpha=alpha, shadow=0.85, left=lx)


def fixed_digits(img, cx: float, y: float, s: str, fnt, col, alpha: float) -> None:
    """Digits in equal-width cells, so a ticking number never jitters."""
    if alpha <= 0.01:
        return
    cell = max(fnt.getlength(str(d)) for d in range(10))
    widths = [cell if ch.isdigit() else fnt.getlength(ch) for ch in s]
    x = cx - sum(widths) / 2
    for ch, wd in zip(s, widths):
        if ch != " ":
            off = (wd - fnt.getlength(ch)) / 2
            kit.solid_text(img, 0, y, [(ch, col)], fnt, alpha=alpha, shadow=0.8, left=x + off)
        x += wd


def ring_layer(view, reveal: float, a: float) -> np.ndarray | None:
    """The Sun's cut edge: a thin bright shell around the slice."""
    if a <= 0.01 or reveal <= 0:
        return None
    s, xc, yc = view
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_ADD)
    x, y, r = CX - s * xc, CY + s * yc, reveal * K * s
    for wdt, g in ((16.0, 0.08), (6.0, 0.25), (2.2, 0.9)):
        ctx.set_source_rgb(1.0 * g * a, 0.82 * g * a, 0.55 * g * a)
        ctx.set_line_width(wdt)
        ctx.arc(x, y, r, 0, 2 * math.pi)
        ctx.stroke()
    surf.flush()
    buf = np.ndarray((H, surf.get_stride() // 4, 4), np.uint8, surf.get_data())[:, :W]
    return buf[..., 2::-1].astype(np.float32)


def draw_sun(arr: np.ndarray, view, t: float, gran: np.ndarray, tex) -> None:
    """The Sun's face: its map for the big patterns, limb darkening, and fine
    granulation that only shows when we are close to its surface."""
    s, xc, yc = view
    R = K * s
    cx, cy = CX - s * xc, CY + s * yc
    x0, x1 = max(0, int(cx - R) - 2), min(W, int(cx + R) + 3)
    y0, y1 = max(0, int(cy - R) - 2), min(H, int(cy + R) + 3)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    wx = xc + (xx + 0.5 - CX) / s
    wy = yc - (yy + 0.5 - CY) / s
    rr = np.hypot(wx, wy)
    cover = np.clip((K - rr) * s + 0.5, 0, 1)
    if not cover.any():
        return
    rho = np.minimum(rr / K, 1.0)
    mu = np.sqrt(1 - rho * rho)
    lat = np.arcsin(np.clip(wy / K, -1, 1))
    lon = np.arctan2(wx / K, np.maximum(mu, 1e-4)) + 0.6 + t * 0.03
    col = tex["sun"].sample(lon, lat, R)
    hot = np.array([255, 236, 196], np.float32)
    out = (col * 0.45 + hot * 0.62) * (0.62 + 0.46 * mu ** 0.6)[..., None]
    close = smooth((s - 7) / 30)
    if close > 0:
        # Up close: granulation, a hotter orange, and limb darkening you can see.
        n = gran.shape[0]
        g = _bilinear(gran, (wx * 30 + t * 3) % (n - 1), (wy * 30 + 200) % (n - 1))[..., 0]
        lum = (0.5 + 0.55 * mu ** 0.45) * (0.72 + 0.5 * g)
        near = np.stack([255 * lum ** 0.8, 178 * lum ** 1.15, 92 * lum ** 1.6], -1)
        out = out * (1 - close) + near * close
    reg = arr[y0:y1, x0:x1]
    reg[:] = reg * (1 - cover[..., None]) + out * cover[..., None]


def sun_glow(arr: np.ndarray, view, gain: float = 1.0) -> None:
    """Bloom around the Sun measured in pixels from its edge, so a close-up
    of its limb does not flood the whole frame."""
    s, xc, yc = view
    R = K * s
    cx, cy = CX - s * xc, CY + s * yc
    rg = min(R, 470.0)
    reach = rg * 1.1 + 16
    ext = reach * 6
    x0, x1 = max(0, int(cx - R - ext)), min(W, int(cx + R + ext))
    y0, y1 = max(0, int(cy - R - ext)), min(H, int(cy + R + ext))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    k = np.maximum(np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) - R * 0.97, 0)
    win = np.clip(1 - k / ext, 0, 1) ** 2
    v = (np.exp(-k / (rg * 0.3 + 6)) * 0.55 + np.exp(-k / reach) * 0.22) * gain * win
    arr[y0:y1, x0:x1] += v[..., None] * np.array([255, 214, 160], np.float32)


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def pad(dur: float, freqs, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    out = np.zeros_like(t)
    for f in freqs:
        for det in (-0.6, 0.0, 0.7):
            out += np.sin(2 * np.pi * (f + det) * t + rng.uniform(0, 6.3))
    out /= len(freqs) * 3
    env = np.clip(t / 2.5, 0, 1) * np.clip((dur - t) / 2.0, 0, 1)
    return (out * env * (0.8 + 0.2 * np.sin(2 * np.pi * t / 7.0))).astype(np.float32)


def whoosh(dur, f0, f1, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = np.zeros_like(t)
    for _ in range(14):
        f = f0 * (f1 / f0) ** u * rng.uniform(0.8, 1.25)
        out += np.sin(2 * np.pi * np.cumsum(f) / snd.SR + rng.uniform(0, 6.3)) * rng.uniform(0.4, 1.0)
    return (out / 14 * np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6).astype(np.float32)


def click(freq: float, dur: float = 0.09) -> np.ndarray:
    """A small glassy tick, like a marble landing."""
    t = np.arange(int(snd.SR * dur)) / snd.SR
    return ((np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.76 * t))
            * np.exp(-t * 70) * (1 - np.exp(-t * 4000))).astype(np.float32)


def pour_noise(dur: float, seed: int = 4) -> np.ndarray:
    """Liquid: soft filtered noise with a slow gurgle."""
    rng = np.random.default_rng(seed)
    n = int(snd.SR * dur)
    x = rng.normal(0, 1, n)
    k = np.exp(-np.arange(60) / 12.0)
    x = np.convolve(x, k / k.sum(), mode="same")
    t = np.arange(n) / snd.SR
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.7 * (0.75 + 0.25 * np.sin(2 * np.pi * 5.3 * t))
    return (x * env * 1.6).astype(np.float32)


def _soundtrack(plan: Plan, path: Path, clips, land_t: np.ndarray, extra_t: np.ndarray) -> None:
    total = plan.total
    m = snd.Mixer(total)
    m.add(0.0, pad(total, [55.0, 82.4, 110.0, 130.8]), 0.3)
    m.add(plan.rew - 0.05, whoosh(1.0, 1500, 140), 0.5)
    m.add(plan.z0, whoosh(plan.z1 - plan.z0 + 0.3, 180, 900, seed=8), 0.35)
    rows = plan.row0 + np.arange(109) / 108 * (plan.row1 - plan.row0)
    for i, (tt, g) in enumerate(zip(rows, snd.density_gains(rows, 0.12, 0.05, 1.0))):
        m.add(tt, click(1400 + 9 * i), g, float(np.clip((i - 54) / 70, -0.7, 0.7)))
    m.add(plan.t_mill, snd.chord([snd.scale_freq(i) for i in (5, 8, 10, 12)], dur=2.4), 0.45)
    m.add(plan.cut0, whoosh(1.2, 120, 420, seed=3), 0.35)
    m.add(plan.fill0, pour_noise(plan.fill1 - plan.fill0 + 0.3), 0.28)
    m.add(plan.drain0, pour_noise(plan.drain1 - plan.drain0 + 0.3, seed=6), 0.22)
    rng = np.random.default_rng(9)
    for ts in (land_t, extra_t):
        pick = rng.choice(len(ts), size=min(len(ts), 700), replace=False)
        tt = ts[pick]
        for t_, g in zip(tt, snd.density_gains(tt, 0.1, 0.06, 2.0)):
            m.add(float(t_), click(rng.uniform(1700, 4200)), g, float(rng.uniform(-0.6, 0.6)))
    m.add(plan.shake0, snd.thud(70, 0.4), 0.4)
    m.add(plan.shake1 - 0.1, snd.thud(60, 0.5), 0.35)
    m.add(plan.extra1, snd.pluck(snd.scale_freq(12), dur=1.6, bright=0.6), 0.3)
    m.add(plan.zg0, whoosh(plan.zg1 - plan.zg0 + 0.2, 300, 90, seed=11), 0.35)
    m.add(plan.t_gaps, snd.chord([snd.scale_freq(i) for i in (8, 10, 12, 15)], dur=3.5), 0.5)
    m.add(plan.zg2, whoosh(plan.zg3 - plan.zg2 + 0.2, 90, 300, seed=12), 0.3)
    m.add(plan.zg3 - 0.1, snd.chord([snd.scale_freq(i) for i in (5, 8, 10, 12)], dur=total - plan.zg3 + 0.1), 0.55)
    voice.voice_over(m, list(clips), bed=0.75)
    m.write(path, total)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(ffmpeg: str, seed: int = 7):
    lines = kit.spoken(SCRIPT, ffmpeg, voice_name=VOICE, rate=RATE)
    plan = Plan(lines)
    total = plan.total
    keys = ["hook", "wide", "melt", "pour", "stack", "end"]
    starts = [plan.hook_at, plan.wide_at, plan.melt_at, plan.pour_at, plan.stack_at, plan.end_at]
    clips = [(a, lines[k]) for a, k in zip(starts, keys)]
    caps = []
    for (at, line), key in zip(clips[1:], keys[1:]):
        caps += kit.captions(at, line, SCRIPT[key][1])

    rng = np.random.default_rng(seed)
    lat = lattice()
    rnd = random_pack()
    target, extras = match(rnd, lat)
    n_r, n_l = len(rnd), len(lat)
    rot_l = rng.uniform(0, 2 * math.pi, n_l)
    rot_r = rot_l[target]                       # each poured Earth keeps its face when it moves
    # Pour: bottom first, a little jitter, landing on a slightly easing schedule.
    order = np.argsort(rnd[:, 1] + rng.normal(0, 3.0, n_r))
    rank = np.empty(n_r)
    rank[order] = np.arange(n_r) / (n_r - 1)
    land = plan.pour0 + (plan.pour1 - plan.pour0 - 0.3) * rank ** 0.92
    # Shake: ripple up from the bottom.
    hgt = (rnd[:, 1] + K) / (2 * K)
    delay = hgt * 0.75 + rng.uniform(0, 0.15, n_r)
    wob = rng.uniform(0, 2 * math.pi, n_r)
    # The extra places fill in from the bottom as the stack closes up.
    eo = np.argsort(lat[extras, 1] + rng.normal(0, 4.0, len(extras)))
    erank = np.empty(len(extras))
    erank[eo] = np.arange(len(extras)) / max(1, len(extras) - 1)
    eland = plan.extra0 + (plan.extra1 - plan.extra0 - 0.3) * erank
    # Row of 109 across the middle.
    row = np.stack([-108.0 + 2.0 * np.arange(109), np.zeros(109)], -1)
    row_rot = rng.uniform(0, 2 * math.pi, 109)
    row_t = plan.row0 + np.arange(109) / 108 * (plan.row1 - plan.row0)
    # Where we dive in: a gap between three Earths, below and left of centre.
    li = int(np.argmin(np.hypot(lat[:, 0] + 9, lat[:, 1] - 34)))
    gap_T = lat[li] + np.array([1.0, 1 / math.sqrt(3)])

    bg = sp.starfield(seed=4, cx=CX, cy=CY)
    tex = s3.textures()
    plasma = plasma_texture()
    gran = granule_texture()
    f_top, f_num, f_sub = kit.sans(24, "bold"), kit.sans(96, "black"), kit.sans(32, "semi")
    f_lab, f_big = kit.sans(26, "bold"), kit.sans(84, "black")
    hook_end = kit.hook_done(HOOK, t0=HOOK_T0)
    soft = (196, 200, 210)

    def pile(t: float):
        """Positions, alphas and faces of the slice's Earths at time t."""
        if t < plan.rew or t >= plan.extra1:
            return lat, np.ones(n_l), rot_l
        if t < plan.rew + 0.6:                     # rewind: they lift out, top rows first
            a = 1 - np.clip((t - plan.rew - (1 - (lat[:, 1] + K) / (2 * K)) * 0.3) / 0.25, 0, 1)
            return lat, a, rot_l
        if t < plan.pour0:
            return lat[:0], np.zeros(0), rot_l[:0]
        if t < plan.shake0:
            u = np.clip((t - (land - 0.32)) / 0.32, 0, 1)
            P = rnd.copy()
            P[:, 1] += 9.0 * (1 - u) ** 2
            return P, smooth_arr(u * 2.5), rot_r
        # shaking down into the stack, extra Earths dropping into the spaces left
        u = np.clip((t - plan.shake0 - delay) / 0.85, 0, 1)
        e = u * u * (3 - 2 * u)
        P = rnd + (lat[target] - rnd) * e[:, None]
        amp = 0.35 * np.sin(math.pi * u) * (1 - u)
        P = P + np.stack([np.sin(t * 31 + wob), np.cos(t * 27 + wob * 1.3)], -1) * amp[:, None]
        ue = np.clip((t - (eland - 0.3)) / 0.3, 0, 1)
        Pe = lat[extras].copy()
        Pe[:, 1] += 6.0 * (1 - ue) ** 2
        return (np.concatenate([P, Pe]), np.concatenate([np.ones(n_r), smooth_arr(ue * 2.5)]),
                np.concatenate([rot_r, rot_l[extras]]))

    def frame(t: float) -> Image.Image:
        view = plan.view(t, gap_T)
        s, xc, yc = view
        arr = bg.copy()
        sun_x, sun_y, sun_r = CX - s * xc, CY + s * yc, K * s
        # reveal of the cross-section
        if t < plan.rew:
            reveal = 1.0
        elif t < plan.cut0:
            reveal = 1 - ease((t - plan.rew - 0.3) / 0.45)
        else:
            reveal = ease((t - plan.cut0) / (plan.cut1 - plan.cut0))
        # the melted Earth's surface
        if plan.fill0 <= t < plan.drain1:
            if t < plan.fill1:
                level = -K - 2 + (2 * K + 6) * ease((t - plan.fill0) / (plan.fill1 - plan.fill0))
            elif t < plan.drain0:
                level = K + 4
            else:
                level = K + 4 - (2 * K + 8) * ease((t - plan.drain0) / (plan.drain1 - plan.drain0))
        else:
            level = -K - 9
        glow_gain = 1.0 + 0.45 * kit.flash(t, plan.t_gaps + 0.15, 0.6) + 0.2 * smooth((t - plan.t_gaps) / 0.6)
        if t < plan.rew:
            glow_gain = 1.2

        sun_glow(arr, view)
        if reveal < 0.999:
            draw_sun(arr, view, t, gran, tex)
        draw_slice(arr, view, t, reveal, level, glow_gain, plasma, tex)
        rl = ring_layer(view, reveal, smooth(reveal * 3))
        if rl is not None:
            arr += rl

        # Earths: the lone Earth, the row, and the slice's pile
        Ps, As, Rs = [], [], []
        if plan.rew <= t < plan.cut1:
            ea = smooth((t - plan.rew - 0.35) / 0.4) if t < plan.z0 else 1 - smooth((t - plan.cut0) / 0.5)
            draw_balls(arr, view, EARTH_W[None], np.array([ea]), np.array([2.2 + t * 0.12]), 0.0, tex,
                       light=SUN_LIGHT)
        if plan.row0 <= t < plan.cut1:
            a = np.clip((t - row_t) / 0.12, 0, 1) * (1 - smooth((t - plan.cut0) / 0.5))
            Ps.append(row), As.append(a), Rs.append(row_rot)
        P, a, r = pile(t)
        if len(P):
            Ps.append(P), As.append(a), Rs.append(r)
        if Ps:
            warm = 1.0 if (t < plan.rew or t >= plan.cut0) else 0.0
            draw_balls(arr, view, np.concatenate(Ps), np.concatenate(As), np.concatenate(Rs), warm, tex)
        busy = smooth((s - 6) / 5) if (t < plan.rew or t >= plan.zg0) else 0.0
        if busy > 0:                                       # shade the top so the count reads
            ys = np.arange(H, dtype=np.float32)
            k = 1 - 0.62 * busy * np.clip((520 - ys) / 260, 0, 1)
            arr *= k[:, None, None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        # ---- labels in the picture ----
        if plan.rew + 0.4 <= t < plan.cut0 + 0.3:
            ea = smooth((t - plan.rew - 0.5) / 0.4) * (1 - smooth((t - plan.cut0) / 0.3))
            ex, ey = CX + s * (EARTH_W[0] - xc), CY - s * (EARTH_W[1] - yc)
            label(img, ex, ey + s + 34, "EARTH", (214, 218, 228), f_lab, ea)
        if plan.z1 - 0.4 <= t < plan.cut0 + 0.3:
            sa = smooth((t - plan.z1) / 0.5) * (1 - smooth((t - plan.cut0) / 0.3))
            label(img, sun_x, sun_y - sun_r - 34, "THE SUN", (214, 218, 228), f_lab, sa)
        if plan.zg1 - 0.2 <= t < plan.zg2 + 0.3:
            ga = smooth((t - plan.zg1 + 0.2) / 0.4) * (1 - smooth((t - plan.zg2) / 0.3))
            gx, gy = CX + s * (gap_T[0] - xc), CY - s * (gap_T[1] - yc)
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
            ctx = cairo.Context(surf)
            ctx.set_source_rgba(1, 0.92, 0.8, 0.85 * ga)
            ctx.set_line_width(2.0)
            lx, ly = gx + 1.9 * s, gy - 1.9 * s
            ctx.move_to(gx + 0.28 * s, gy - 0.28 * s)
            ctx.line_to(lx, ly)
            ctx.line_to(lx + 26, ly)
            ctx.stroke()
            ctx.arc(gx, gy, 5, 0, 2 * math.pi)
            ctx.fill()
            surf.flush()
            ov = Image.frombuffer("RGBA", (W, H), bytes(surf.get_data()), "raw", "BGRA", 0, 1)
            img.paste(ov, (0, 0), ov)
            kit.darken(img, (lx + 30, ly - 26, lx + 30 + f_lab.getlength("A GAP") + 4, ly + 26), 0.5 * ga, 22)
            label(img, lx + 34, ly, "A GAP", WHITE, f_lab, ga, "left")

        # ---- the count (top) ----
        top, num, num_col, sub, sub_a = None, None, WHITE, None, 0.0
        if plan.row0 <= t < plan.melt_at:
            k = int(np.sum(t >= row_t))
            top = "EARTHS ACROSS THE SUN" if t < plan.t_cubed - 0.1 else "EARTHS INSIDE THE SUN"
            if t < plan.t_cubed - 0.1:
                num, num_col = f"{k}", (GOLD if k >= 109 else WHITE)
            elif t < plan.t_mill:
                num = "109 × 109 × 109"
            else:
                num, num_col = "1.3 million", GOLD
        elif plan.melt_at <= t < plan.drain0 + 0.3:
            top, num, num_col = "EARTHS INSIDE THE SUN", "1.3 million", GOLD
            sub, sub_a = "MELTED DOWN", smooth((t - plan.t_melt) / 0.4)
        elif t >= plan.drain0 + 0.3 or t < 0:
            top = "EARTHS INSIDE THE SUN"
            if t < plan.shake0:
                landed = float(np.mean(t >= land)) if t >= plan.pour0 else 0.0
                val = int(round(RANDOM * landed / 1000)) * 1000
                num, num_col = f"{val:,}", (GOLD if landed >= 0.999 else WHITE)
                sub, sub_a = "POURED IN AT RANDOM", smooth((t - plan.pour0) / 0.4)
            else:
                landed = float(np.mean(t >= eland))
                val = RANDOM + (940_000 - RANDOM) * landed
                val = int(round(val / 1000)) * 1000
                num, num_col = f"{val:,}", (GOLD if landed >= 0.999 else WHITE)
                sub, sub_a = "STACKED PERFECTLY", smooth((t - plan.shake0) / 0.4)
        ca = smooth((t - plan.row0 + 0.1) / 0.4) if t < plan.melt_at else 1.0
        for ts in (plan.t_cubed - 0.1, plan.t_mill, plan.drain0 + 0.3):   # dip as the number changes
            ca *= smooth(abs(t - ts) / 0.12)
        if top and t >= plan.rew_end:
            label(img, W / 2, TOP_LABEL_Y, top, MUTED, f_top, ca)
            fixed_digits(img, W / 2, NUM_Y, num, f_num, num_col, ca)
            if sub:
                label(img, W / 2, SUB_Y, sub, soft, f_sub, sub_a * ca)
        # the payoff: a quarter of the Sun is gaps
        if t >= plan.t_quarter - 0.05:
            fa = ease((t - plan.t_quarter) / 0.5)
            if fa > 0.01:
                kit.darken(img, (300, 1488, 780, 1596), 0.55 * fa, 30)
                kit.solid_text(img, W / 2, 1532 + 16 * (1 - fa), [("26%", GOLD), (" gaps", WHITE)], f_big,
                               alpha=fa, shadow=0.85)
                label(img, W / 2, 1610, "EVEN IN A PERFECT STACK", MUTED, f_top, smooth((t - plan.t_quarter - 0.3) / 0.4))
        # the hook
        if t < plan.rew + 0.4:
            ha = 1.0 if t < plan.rew else 1 - smooth((t - plan.rew) / 0.4)
            kit.hook(img, HOOK, t if t < hook_end + 0.1 else 99.0, t0=HOOK_T0, alpha=ha)
        kit.draw_captions(img, caps, t)
        return img

    def sound(path: Path) -> None:
        _soundtrack(plan, path, clips, land, eland)

    return total, frame, sound


def smooth_arr(u: np.ndarray) -> np.ndarray:
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    total, frame, sound = build(ffmpeg, seed)
    return kit.encode(out_path, ffmpeg, total, frame, sound, FPS, progress,
                      module=__name__, build_kw={"seed": seed})
