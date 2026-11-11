"""3D pieces for Space in Motion: a perspective camera, textured lit planets,
the light front as a glowing bubble, and the Voyager probe.

Planet maps are the Solar System Scope 2k set (CC BY 4.0, assets/space/,
credit line TEXTURE_CREDIT). Everything here draws straight into a PIL frame
or a float array at exact sub-pixel positions, so slow camera moves never
shimmer.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .canvas import H, W

TEX_DIR = Path(__file__).resolve().parents[2] / "assets" / "space"
TEX_FILES = {
    "earth": "2k_earth_daymap.jpg", "clouds": "2k_earth_clouds.jpg", "jupiter": "2k_jupiter.jpg",
    "saturn": "2k_saturn.jpg", "mars": "2k_mars.jpg", "venus": "2k_venus_atmosphere.jpg",
    "mercury": "2k_mercury.jpg", "uranus": "2k_uranus.jpg", "neptune": "2k_neptune.jpg", "sun": "2k_sun.jpg",
}
TEXTURE_CREDIT = "Planet textures: Solar System Scope (CC BY 4.0)"


class Camera:
    """Perspective camera looking down `phi` at the ecliptic plane from behind
    Earth. World axes: X right, Y forward, Z up (AU, Earth at the origin).
    Its distance scales with V, so the framing of the light front never changes."""

    def __init__(self, V: float, phi: float, dist: float, f: float, cx: float, cy: float):
        self.look = np.array([0.0, math.cos(phi), -math.sin(phi)])
        self.up = np.array([0.0, math.sin(phi), math.cos(phi)])
        self.right = np.array([1.0, 0.0, 0.0])
        self.C = -dist * V * self.look
        self.f, self.cx, self.cy, self.V = f, cx, cy, V

    def cam(self, P) -> np.ndarray:
        """World point(s) -> camera coords (x right, y up, z forward)."""
        r = np.asarray(P, float) - self.C
        return np.stack([r @ self.right, r @ self.up, r @ self.look], axis=-1)

    def project(self, P):
        c = self.cam(P)
        z = c[..., 2]
        return self.cx + self.f * c[..., 0] / z, self.cy - self.f * c[..., 1] / z, z

    def to_cam_dir(self, v) -> np.ndarray:
        v = np.asarray(v, float)
        return np.array([v @ self.right, v @ self.up, v @ self.look])


class Texture:
    """An equirectangular map with mip levels, sampled bilinearly."""

    def __init__(self, path, gray: bool = False):
        im = Image.open(path).convert("L" if gray else "RGB")
        self.levels = []
        while True:
            a = np.asarray(im, np.float32)
            if a.ndim == 2:
                a = a[..., None]
            self.levels.append(a)
            if im.width <= 64:
                break
            im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)

    def sample(self, lon: np.ndarray, lat: np.ndarray, r_px: float) -> np.ndarray:
        """Trilinear: blend the two mip levels around the detail this size needs,
        so a planet that grows or shrinks never jumps sharp->soft at a level
        boundary. Bigger than the full-size map: the full-size map."""
        want = 2 * math.pi * max(r_px, 1) * 1.3
        lod = math.log2(self.levels[0].shape[1] / want)
        lod = min(max(lod, 0.0), len(self.levels) - 1.0)
        i = int(math.floor(lod))
        f = lod - i
        a = self._bilinear(self.levels[i], lon, lat)
        if f < 1e-3 or i + 1 >= len(self.levels):
            return a
        return a * (1 - f) + self._bilinear(self.levels[i + 1], lon, lat) * f

    @staticmethod
    def _bilinear(tex: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        h, w = tex.shape[:2]
        u = (lon / (2 * math.pi) % 1.0) * w - 0.5
        v = np.clip((0.5 - lat / math.pi) * h - 0.5, 0, h - 1.001)
        x0 = np.floor(u).astype(int)
        y0 = np.floor(v).astype(int)
        fx, fy = (u - x0)[..., None], (v - y0)[..., None]
        x0 %= w
        x1 = (x0 + 1) % w
        y1 = np.minimum(y0 + 1, h - 1)
        return ((tex[y0, x0] * (1 - fx) + tex[y0, x1] * fx) * (1 - fy)
                + (tex[y1, x0] * (1 - fx) + tex[y1, x1] * fx) * fy)


@lru_cache(maxsize=1)
def textures() -> dict:
    out = {k: Texture(TEX_DIR / v, gray=(k == "clouds")) for k, v in TEX_FILES.items()}
    ring = np.asarray(Image.open(TEX_DIR / "2k_saturn_ring_alpha.png").convert("RGBA"), np.float32)
    out["ring"] = ring.mean(axis=0)          # radial profile (2048, 4), inner -> outer
    return out


def _basis(pole: np.ndarray):
    pole = pole / np.linalg.norm(pole)
    a = np.array([1.0, 0, 0]) if abs(pole[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(pole, a)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(pole, e1), pole


ATMOS = {"earth": (110, 160, 255), "neptune": (120, 160, 255), "uranus": (170, 230, 240), "venus": (255, 230, 190)}


def draw_planet(img: Image.Image, cam: Camera, name: str, cx: float, cy: float, r: float, light_cam,
                rot: float = 0.0, alpha: float = 1.0, pole=(0.0, 0.0, 1.0), emissive: bool = False,
                ring_normal=None, clouds_rot: float = 0.0, flash: float = 0.0) -> None:
    """A textured, lit sphere of radius r px centred at (cx, cy), seen by `cam`.
    light_cam: vector towards the light in camera coords. Saturn gets rings
    (ring_normal in world coords); Earth gets clouds; gas/ice giants and Earth
    an atmosphere rim. `flash` brightens it when the light front arrives."""
    if alpha <= 0.01 or r < 0.6:
        return
    tex = textures()
    ext = 2.35 if ring_normal is not None else 1.0
    half = r * ext + 2
    bx0, by0 = max(0, int(math.floor(cx - half))), max(0, int(math.floor(cy - half)))
    bx1, by1 = min(W, int(math.ceil(cx + half)) + 1), min(H, int(math.ceil(cy + half)) + 1)
    if bx0 >= bx1 or by0 >= by1:
        return
    yy, xx = np.mgrid[by0:by1, bx0:bx1].astype(np.float32)
    sx, sy = (xx + 0.5 - cx) / r, -(yy + 0.5 - cy) / r          # up is +y
    rho2 = sx * sx + sy * sy
    rho = np.sqrt(rho2)
    cover = np.clip((1 - rho) * r + 0.5, 0, 1)                    # anti-aliased edge
    nz = -np.sqrt(np.clip(1 - rho2, 0, 1))                        # facing the camera
    n_w = sx[..., None] * cam.right + sy[..., None] * cam.up + nz[..., None] * cam.look
    e1, e2, p = _basis(np.asarray(pole, float))
    lat = np.arcsin(np.clip(n_w @ p, -1, 1))
    lon = np.arctan2(n_w @ e2, n_w @ e1) + rot
    col = tex[name].sample(lon, lat, r)
    L = np.asarray(light_cam, float)
    L = L / np.linalg.norm(L)
    lam = sx * L[0] + sy * L[1] + nz * L[2]
    mu = np.clip(-nz, 0, 1)
    if emissive:
        # A star, not a fireball: lift the map towards warm white, keep its texture.
        hot = np.array([255, 236, 196], np.float32)
        out = (col * 0.45 + hot * 0.62) * (0.7 + 0.38 * mu ** 0.5)[..., None]
    else:
        lit = np.clip(lam, 0, 1)
        soft = np.clip(lam * 0.5 + 0.5, 0, 1) ** 3                 # soft terminator
        shade = 0.11 + 0.89 * (0.68 * lit ** 0.85 + 0.32 * soft) * (0.8 + 0.2 * mu)
        out = col * shade[..., None]
        if name == "earth":
            cl = np.clip(tex["clouds"].sample(lon + clouds_rot, lat, r)[..., 0] / 255 * 1.1, 0, 1)
            out = out * (1 - cl[..., None] * 0.85) + (240 * shade * cl)[..., None]
        if name in ATMOS:
            rim = np.clip((rho - 0.7) / 0.3, 0, 1) ** 2 * np.clip(lam + 0.35, 0, 1)
            out = out + rim[..., None] * np.array(ATMOS[name], np.float32) * 0.55
    if flash > 0:
        out = out + flash * 70 * np.array([1.0, 0.9, 0.75], np.float32)
    a = cover * alpha
    reg = np.asarray(img.crop((bx0, by0, bx1, by1)), np.float32)
    if ring_normal is not None:
        nr = cam.to_cam_dir(ring_normal)
        nr = nr / np.linalg.norm(nr)
        zp = -(nr[0] * sx + nr[1] * sy) / (nr[2] if abs(nr[2]) > 1e-3 else 1e-3)
        dist_r = np.sqrt(sx * sx + sy * sy + zp * zp)
        prof = tex["ring"]
        u = (dist_r - 1.24) / (2.27 - 1.24)
        inside = (u >= 0) & (u < 1)
        rc = prof[np.clip((u * (len(prof) - 1)).astype(int), 0, len(prof) - 1)]
        ra = (rc[..., 3] / 255) * inside * 0.95 * alpha
        ring_rgb = rc[..., :3] * (0.35 + 0.65 * abs(float(L @ nr)))
        on_globe = rho < 1
        front = zp < nz
        ra_back = ra * (~front) * (~on_globe)
        ra_front = ra * front
        reg = reg * (1 - ra_back[..., None]) + ring_rgb * ra_back[..., None]
        reg = reg * (1 - a[..., None]) + out * a[..., None]
        reg = reg * (1 - ra_front[..., None]) + ring_rgb * ra_front[..., None]
    else:
        reg = reg * (1 - a[..., None]) + out * a[..., None]
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), (bx0, by0))


def glow(arr: np.ndarray, cx: float, cy: float, r: float, gain: float, col=(255, 214, 160), reach: float = 4.0) -> None:
    """Soft natural bloom around a bright disc (the Sun, a star), additive."""
    if gain <= 0:
        return
    wide = r * 1.1 + 16
    ext = r * 0.9 + wide * reach * 1.5
    x0, y0 = max(0, int(cx - ext)), max(0, int(cy - ext))
    x1, y1 = min(W, int(cx + ext)), min(H, int(cy + ext))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
    k = np.maximum(d - r * 0.9, 0)
    window = np.clip(1 - (d / ext) ** 2, 0, 1) ** 2          # fades to zero before the box edge
    v = (np.exp(-k / (r * 0.3 + 6)) * 0.55 + np.exp(-k / wide) * 0.22) * gain * window
    arr[y0:y1, x0:x1] += v[..., None] * np.array(col, np.float32)


def bubble(arr: np.ndarray, cam: Camera, R: float, gain: float = 1.0, col=(1.0, 0.88, 0.70)) -> None:
    """The light front as a thin glowing sphere around Earth: faint where we look
    through it, bright at its edge where the line of sight grazes the shell."""
    if gain <= 0 or R <= 0:
        return
    c = cam.cam(np.zeros(3))                       # Earth, the sphere's centre
    rpx = cam.f * R / c[2]
    ex, ey = cam.cx + cam.f * c[0] / c[2], cam.cy - cam.f * c[1] / c[2]
    reach = rpx * 1.25 + 30
    x0, y0 = max(0, int(ex - reach)), max(0, int(ey - reach))
    x1, y1 = min(W, int(ex + reach)), min(H, int(ey + reach))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = (xx + 0.5 - cam.cx) / cam.f, -(yy + 0.5 - cam.cy) / cam.f
    norm = np.sqrt(dx * dx + dy * dy + 1)
    t = (dx * c[0] + dy * c[1] + c[2]) / norm
    b2 = np.maximum(c @ c - t * t, 0)
    u = np.sqrt(b2) / R
    shell = np.where(u < 1, 1 / np.sqrt(np.maximum(1 - u * u, 1e-4)), 0.0)
    shell = np.minimum(shell, 7.0)
    edge = np.exp(-(((u - 1) * rpx) / 1.6) ** 2) * 120 + np.exp(-(((u - 1) * rpx) / 10) ** 2) * 26
    v = (3.2 * shell + edge) * gain
    arr[y0:y1, x0:x1] += v[..., None] * np.array(col, np.float32)


@lru_cache(maxsize=2)
def probe_master(width: int = 560) -> Image.Image:
    """Voyager seen from the Earth side: the big dish face-on (it points home),
    the gold bus behind it, booms out to the sides. Shaded, RGBA."""
    ss = 2
    n = width * ss
    h = int(n * 0.62)
    im = Image.new("RGBA", (n, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = n * 0.5, h * 0.5
    s = n / 5.6
    boom, dark, foil = (176, 180, 188, 255), (92, 96, 104, 255), (214, 168, 84, 255)

    def lw(v):
        return max(1, int(v * s))
    d.line([(cx + 0.6 * s, cy - 0.6 * s), (cx + 2.7 * s, cy - 1.75 * s)], fill=boom, width=lw(0.045))
    d.line([(cx - 0.7 * s, cy + 0.3 * s), (cx - 2.5 * s, cy + 1.05 * s)], fill=boom, width=lw(0.07))
    for k in range(3):
        px, py = cx - (1.45 + 0.36 * k) * s, cy + (0.72 + 0.15 * k) * s
        d.rounded_rectangle((px - 0.16 * s, py - 0.13 * s, px + 0.16 * s, py + 0.13 * s), radius=0.04 * s,
                            fill=(70, 72, 78, 255))
        d.line([(px - 0.12 * s, py - 0.13 * s), (px + 0.12 * s, py + 0.13 * s)], fill=(130, 134, 140, 255),
               width=lw(0.02))
    d.line([(cx + 0.7 * s, cy + 0.2 * s), (cx + 2.1 * s, cy + 0.55 * s)], fill=boom, width=lw(0.07))
    d.rounded_rectangle((cx + 1.95 * s, cy + 0.25 * s, cx + 2.45 * s, cy + 0.75 * s), radius=0.05 * s, fill=dark)
    d.rectangle((cx + 2.02 * s, cy + 0.33 * s, cx + 2.2 * s, cy + 0.5 * s), fill=(150, 160, 175, 255))
    d.polygon([(cx - 0.62 * s, cy - 0.98 * s), (cx + 0.62 * s, cy - 0.98 * s), (cx + 0.74 * s, cy - 0.55 * s),
               (cx - 0.74 * s, cy - 0.55 * s)], fill=foil)
    d.line([(cx - 0.5 * s, cy - 0.82 * s), (cx + 0.5 * s, cy - 0.82 * s)], fill=(240, 205, 130, 255), width=lw(0.03))
    arr = np.asarray(im, np.float32).copy()
    yy, xx = np.mgrid[0:h, 0:n].astype(np.float32)
    rx, ry = 1.25 * s, 1.08 * s
    dcx, dcy = cx, cy + 0.1 * s
    ex, ey = (xx - dcx) / rx, (yy - dcy) / ry
    rr = np.sqrt(ex * ex + ey * ey)
    disc = np.clip((1 - rr) * rx + 0.5, 0, 1)
    # A concave bowl lit from the upper left: the far inner wall catches the light.
    bowl = 0.58 + 0.32 * (ex * 0.6 + ey * 0.5) + 0.08 * (1 - rr)
    rim = np.clip((rr - 0.88) / 0.12, 0, 1)
    shade = bowl * (1 - rim) + (0.98 - 0.3 * (ex * 0.5 + ey * 0.6)) * rim
    dish = np.stack([shade * 224, shade * 228, shade * 236], -1)
    arr[..., :3] = arr[..., :3] * (1 - disc[..., None]) + dish * disc[..., None]
    arr[..., 3] = np.maximum(arr[..., 3], disc * 255)
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(im)
    for a in (-90, 30, 150):
        ar = math.radians(a)
        d.line([(dcx + math.cos(ar) * 1.12 * rx / s * s, dcy + math.sin(ar) * 0.98 * ry / s * s), (dcx, dcy)],
               fill=(200, 202, 208, 255), width=lw(0.035))
    d.ellipse((dcx - 0.17 * s, dcy - 0.17 * s, dcx + 0.17 * s, dcy + 0.17 * s), fill=(116, 120, 128, 255))
    d.ellipse((dcx - 0.09 * s, dcy - 0.09 * s, dcx + 0.09 * s, dcy + 0.09 * s), fill=(218, 220, 226, 255))
    return im.resize((width, int(h / ss)), Image.LANCZOS)


def paste_scaled(img: Image.Image, master: Image.Image, cx: float, cy: float, width: float, alpha: float = 1.0) -> None:
    """Paste an RGBA master scaled to `width` px, centred on a sub-pixel position."""
    if alpha <= 0.01 or width < 2:
        return
    k = master.width / width
    hgt = master.height / k
    X0, Y0 = int(math.floor(cx - width / 2)) - 1, int(math.floor(cy - hgt / 2)) - 1
    nw, nh = int(math.ceil(width)) + 3, int(math.ceil(hgt)) + 3
    pad = int(3 * k) + 4
    big = Image.new("RGBA", (master.width + 2 * pad, master.height + 2 * pad), (0, 0, 0, 0))
    big.paste(master, (pad, pad))
    box = ((X0 - (cx - width / 2)) * k + pad, (Y0 - (cy - hgt / 2)) * k + pad,
           (X0 + nw - (cx - width / 2)) * k + pad, (Y0 + nh - (cy - hgt / 2)) * k + pad)
    spr = big.resize((nw, nh), Image.LANCZOS, box=box)
    if alpha < 0.999:
        spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    img.paste(spr, (X0, Y0), spr)
