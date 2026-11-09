"""Map plates for the documentary scenes (doc.py): South Asia at night, and in
perspective over real terrain.

Rules every plate follows:
  * India is drawn with its official boundary (assets/geo/india_pov.json).
    Natural Earth's Pakistan and China include parts of Jammu & Kashmir and
    Ladakh, so their masks, lights and outlines are always India-subtracted.
  * Relief comes from NOAA's ETOPO1 grid (assets/geo/etopo1_south_asia.npz);
    no extruded slabs, soft light from the north-west.

Plates are slow to make (a minute or two for terrain), so each is cached as a
PNG under data/cache/carto, keyed by everything that shapes it. They are drawn
``PS`` times larger than the video so a slow camera push only ever scales down.
"""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import cairo
import numpy as np
from PIL import Image, ImageFilter

from ..config import PROJECT_ROOT

GEO = PROJECT_ROOT / "assets" / "geo"
CACHE = PROJECT_ROOT / "data" / "cache" / "carto"
W, H = 1920, 1080
PS = 1.125                      # plate scale over the video frame
PW, PH = int(W * PS), int(H * PS)
VERSION = 3                     # bump when the plate drawing changes

MAIN = ("India", "Pakistan", "Bangladesh")
COL = {"India": np.array([0.76, 0.40, 0.17]), "Pakistan": np.array([0.24, 0.37, 0.60]),
       "Bangladesh": np.array([0.58, 0.16, 0.24])}
COL_LIGHT = {"India": (0.89, 0.57, 0.35), "Pakistan": (0.49, 0.61, 0.80), "Bangladesh": (0.82, 0.35, 0.42)}
GOLD = (0.79, 0.64, 0.36)

# Texture grid (lon/lat), shared by every plate.
LON0, LON1, LAT0, LAT1, RES = 30.0, 110.0, 0.0, 45.0, 0.025
TW, TH = int(round((LON1 - LON0) / RES)) + 1, int(round((LAT1 - LAT0) / RES)) + 1


def _smooth(a: float, b: float, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _ne() -> dict[str, Any]:
    return json.loads((GEO / "ne_110m_admin_0_countries.geojson").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _india() -> list[np.ndarray]:
    return [np.array(r) for r in json.loads((GEO / "india_pov.json").read_text(encoding="utf-8"))["rings"]]


@lru_cache(maxsize=None)
def rings(name: str) -> tuple[np.ndarray, ...]:
    if name == "India":
        return tuple(_india())
    for f in _ne()["features"]:
        p = f["properties"]
        if name in (p.get("NAME"), p.get("ADMIN")):
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            return tuple(np.array(pl[0]) for pl in polys)
    raise KeyError(name)


def all_names() -> list[str]:
    return [f["properties"]["NAME"] for f in _ne()["features"]]


@lru_cache(maxsize=1)
def _india_paths():
    from matplotlib.path import Path as MPath

    return [MPath(r) for r in _india()]


def in_india(pts: np.ndarray) -> np.ndarray:
    m = np.zeros(len(pts), bool)
    for p in _india_paths():
        m |= p.contains_points(pts)
    return m


def _raster(rs_list) -> np.ndarray:
    s = cairo.ImageSurface(cairo.FORMAT_A8, TW, TH)
    c = cairo.Context(s)
    c.set_antialias(cairo.ANTIALIAS_GOOD)
    for r in rs_list:
        c.move_to((r[0, 0] - LON0) / RES, (LAT1 - r[0, 1]) / RES)
        for lo, la in r[1:]:
            c.line_to((lo - LON0) / RES, (LAT1 - la) / RES)
        c.close_path()
    c.set_source_rgba(0, 0, 0, 1)
    c.fill()
    s.flush()
    a = np.frombuffer(s.get_data(), np.uint8).reshape(TH, s.get_stride())[:, :TW]
    return a.astype(np.float32) / 255.0


@lru_cache(maxsize=1)
def masks() -> dict[str, np.ndarray]:
    """Country masks on the texture grid; India's official boundary always wins."""
    from scipy import ndimage

    m_in = _raster(_india())
    out = {"India": m_in}
    for n in ("Pakistan", "Bangladesh"):
        m = np.clip(_raster(rings(n)) - m_in, 0, 1)
        out[n] = ndimage.grey_opening(m, size=(7, 7))   # slivers where the datasets disagree
    land = np.zeros((TH, TW), np.float32)
    for n in all_names():
        try:
            land = np.maximum(land, _raster(rings(n)))
        except KeyError:
            pass
    out["_land"] = np.maximum(land, m_in)
    return out


@lru_cache(maxsize=1)
def terrain() -> dict[str, np.ndarray]:
    """Elevation, land and hillshade relief on the texture grid."""
    from scipy import ndimage

    z = np.load(GEO / "etopo1_south_asia.npz")
    dem = z["dem"].astype(np.float32)
    lon0, lat0, cell = float(z["lon0"]), float(z["lat0"]), float(z["cell"])
    nr, nc = dem.shape
    lat1 = lat0 + (nr - 1) * cell
    lon_g = LON0 + np.arange(TW) * RES
    lat_g = LAT1 - np.arange(TH) * RES
    LON, LAT = np.meshgrid(lon_g, lat_g)
    r_idx = (lat1 - LAT) / cell
    c_idx = (LON - lon0) / cell
    inside = (r_idx >= 0) & (r_idx <= nr - 1) & (c_idx >= 0) & (c_idx <= nc - 1)
    elev = ndimage.map_coordinates(dem, [np.clip(r_idx, 0, nr - 1), np.clip(c_idx, 0, nc - 1)], order=1)
    land_ne = masks()["_land"]
    fallback = np.where(land_ne > 0.5, 150.0, -3000.0)
    edge = np.minimum.reduce([c_idx, nc - 1 - c_idx, r_idx, nr - 1 - r_idx]) / 40.0
    wdem = np.clip(edge, 0, 1) * inside
    elev = elev * wdem + fallback * (1 - wdem)
    land = np.where(wdem > 0.5, elev > 0, land_ne > 0.5).astype(np.float32)   # the grid's coast wins inside it
    land = ndimage.gaussian_filter(land, 0.8)
    height = np.where(elev > 0, elev, 0.0).astype(np.float32)
    cosl = np.cos(np.radians(LAT))
    dx, dy = RES * 111320 * cosl, RES * 111320
    gy, gx = np.gradient(ndimage.gaussian_filter(height, 0.6) * 4.0)
    gx, gy = gx / dx, -gy / dy
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(38)
    hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    relief = (hs - np.sin(alt)) * _smooth(0, 1, np.clip(edge / 3.0, 0, 1)) * inside
    return {"elev": elev, "land": land, "height": height, "relief": relief.astype(np.float32)}


def texture(mode: str, tints: dict[str, float] | None = None) -> np.ndarray:
    """RGB texture on the lon/lat grid: 'night' (flat, cinematic) or 'dusk' (terrain)."""
    t, m = terrain(), masks()
    if mode == "night":
        base = np.array([0.20, 0.19, 0.18])
        tint_a, rel_k = 0.34, 1.25
        sea_shallow, sea_deep = np.array([0.105, 0.125, 0.145]), np.array([0.055, 0.068, 0.085])
    else:
        base = np.array([0.50, 0.455, 0.40])
        tint_a, rel_k = 0.40, 1.7
        sea_shallow, sea_deep = np.array([0.30, 0.34, 0.37]), np.array([0.17, 0.20, 0.23])
    shade = np.clip(1.0 + rel_k * t["relief"], 0.3, 1.45 if mode == "night" else 1.7)[..., None]
    col = np.broadcast_to(base, (TH, TW, 3)).copy()
    snow = _smooth(3800, 6000, t["height"])[..., None] * (0.35 if mode == "dusk" else 0.0)
    col = col * (1 - snow) + np.array([0.86, 0.85, 0.83]) * snow
    for n in MAIN:
        a = (m[n] * (tints or {}).get(n, tint_a))[..., None]
        col = col * (1 - a) + COL[n] * (0.85 if mode == "night" else 1.0) * a
    col = col * shade
    depth = _smooth(0, 3500, -t["elev"])[..., None]
    sea = sea_shallow * (1 - depth) + sea_deep * depth
    lm = t["land"][..., None]
    return np.clip(col * lm + sea * (1 - lm), 0, 1).astype(np.float32)


def sample(tex: np.ndarray, lon, lat, order: int = 1) -> np.ndarray:
    from scipy import ndimage

    r, c = (LAT1 - lat) / RES, (lon - LON0) / RES
    return np.stack([ndimage.map_coordinates(tex[..., k], [r, c], order=order, mode="nearest")
                     for k in range(tex.shape[-1])], -1)


def sample1(a: np.ndarray, lon, lat) -> np.ndarray:
    from scipy import ndimage

    return ndimage.map_coordinates(a, [(LAT1 - np.asarray(lat)) / RES, (np.asarray(lon) - LON0) / RES],
                                   order=1, mode="nearest")


def elevation(lon: float, lat: float) -> float:
    return float(sample1(terrain()["height"], np.array([lon]), np.array([lat]))[0])


# --------------------------------------------------------------------------- #
# Drawing helpers
# --------------------------------------------------------------------------- #
def to_img(surf: cairo.ImageSurface) -> Image.Image:
    w, h = surf.get_width(), surf.get_height()
    a = np.frombuffer(surf.get_data(), np.uint8).reshape(h, surf.get_stride() // 4, 4)[:, :w]
    al = a[..., 3:4].astype(np.float32)
    rgb = np.where(al > 0, a[..., [2, 1, 0]] * 255.0 / np.maximum(al, 1), 0)
    return Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), al], 2).astype(np.uint8), "RGBA")


def finish(rgb: np.ndarray, grain: float = 5.0, vig: float = 0.45, seed: int = 3) -> Image.Image:
    h, w = rgb.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((x - w * 0.5) / (w * 0.62), (y - h * 0.5) / (h * 0.62))
    v = np.clip(1 - vig * np.clip(d - 0.55, 0, 1) ** 1.3, 0, 1)
    a = rgb * v[..., None] * 255
    a += np.random.default_rng(seed).normal(0, grain, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _trace(ctx, pts, skip=None) -> None:
    started = False
    for i, p in enumerate(pts):
        if p is None or (skip is not None and skip[i]):
            started = False
            continue
        if started:
            ctx.line_to(*p)
        else:
            ctx.move_to(*p)
            started = True


def borders(ctx, proj, focus_alpha: float = 0.95, other_alpha: float = 0.30, width: float = 1.6) -> None:
    """Neighbours in a hairline ivory; the three countries in their colour; India last.

    Coastlines come from the relief, so only land borders are traced for
    neighbours; China's and Pakistan's segments inside India are skipped.
    """
    height = terrain()["height"]
    for n in all_names():
        if n in MAIN:
            continue
        try:
            rs = rings(n)
        except KeyError:
            continue
        for r in rs:
            pts = [proj(lo, la) for lo, la in r]
            coast = sample1(height, r[:, 0], r[:, 1]) < 25
            skip = coast | (in_india(r) if n == "China" else False)
            _trace(ctx, pts + [pts[0]], np.r_[skip, skip[:1]])
    ctx.set_source_rgba(0.93, 0.89, 0.80, other_alpha)
    ctx.set_line_width(width * 0.7)
    ctx.stroke()
    for n in ("Pakistan", "Bangladesh", "India"):
        for r in rings(n):
            pts = [proj(lo, la) for lo, la in r]
            skip = np.r_[in_india(r), in_india(r[:1])] if n == "Pakistan" else None
            _trace(ctx, pts + [pts[0]], skip)
        ctx.set_source_rgba(*COL_LIGHT[n], focus_alpha)
        ctx.set_line_width(width * (1.25 if n == "India" else 1.0))
        ctx.stroke()


CITIES = {
    "India": [(77.2, 28.6, 9), (72.9, 19.1, 8), (88.4, 22.6, 7), (80.3, 13.1, 5), (77.6, 13.0, 6), (78.5, 17.4, 5),
              (72.6, 23.0, 4), (73.9, 18.5, 4), (80.9, 26.8, 3), (75.8, 26.9, 3), (85.1, 25.6, 3), (76.9, 8.5, 2),
              (76.3, 10.0, 2), (75.9, 22.7, 2), (79.1, 21.1, 2), (83.0, 25.3, 2), (74.9, 31.6, 2), (76.8, 30.7, 2),
              (83.2, 17.7, 2), (91.7, 26.1, 1), (85.8, 20.3, 2), (81.6, 21.2, 1), (78.0, 27.2, 2), (75.8, 11.3, 1),
              (74.8, 34.1, 1), (74.9, 32.7, 1)],
    "Pakistan": [(67.0, 24.9, 7), (74.3, 31.5, 6), (73.0, 33.6, 4), (73.1, 31.4, 3), (71.5, 34.0, 3), (71.5, 30.2, 2),
                 (68.4, 25.4, 2), (67.0, 30.2, 1), (74.5, 32.5, 2)],
    "Bangladesh": [(90.4, 23.8, 8), (91.8, 22.3, 4), (89.6, 22.8, 2), (88.6, 24.4, 2), (91.9, 24.9, 1), (89.4, 25.7, 1)],
}


def light_points(seed: int = 11) -> list[tuple[str, np.ndarray]]:
    """City-light points per country, inside India-subtracted masks only."""
    rng = np.random.default_rng(seed)
    m = masks()
    out = []
    for n in MAIN:
        pts = [np.c_[rng.normal(lo, 0.07 + 0.04 * w, int(110 * w)), rng.normal(la, 0.07 + 0.04 * w, int(110 * w))]
               for lo, la, w in CITIES[n]]
        allr = np.vstack(rings(n))
        k = {"India": 5200, "Pakistan": 1400, "Bangladesh": 900}[n]
        pts.append(np.c_[rng.uniform(allr[:, 0].min(), allr[:, 0].max(), k),
                         rng.uniform(allr[:, 1].min(), allr[:, 1].max(), k)])
        p = np.vstack(pts)
        out.append((n, p[sample1(m[n], p[:, 0], p[:, 1]) > 0.5]))
    return out


def _cached(name: str, params: dict[str, Any], make: Callable[[], Image.Image]) -> Image.Image:
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(json.dumps({**params, "v": VERSION, "ps": PS}, sort_keys=True).encode()).hexdigest()[:12]
    path = CACHE / f"{name}_{digest}.png"
    if path.exists():
        return Image.open(path).convert("RGBA")
    img = make()
    img.save(path)
    return img.convert("RGBA")


# --------------------------------------------------------------------------- #
# Flat night map
# --------------------------------------------------------------------------- #
class NightMap:
    """A flat night map: ``s`` px per degree of longitude at video scale,
    (cx, cy) in lon/lat drawn at video pixel (ox, oy)."""

    K = math.cos(math.radians(22))

    def __init__(self, s: float, cx: float, cy: float, ox: float, oy: float,
                 tints: dict[str, float] | None = None, key_light=(1500, 160)):
        self.s, self.cx, self.cy, self.ox, self.oy = s, cx, cy, ox, oy
        self.tints = tints or {}
        self.key_light = key_light
        self.params = {"s": s, "cx": cx, "cy": cy, "ox": ox, "oy": oy, "tints": self.tints, "kl": list(key_light)}

    def proj(self, lon: float, lat: float) -> tuple[float, float]:
        """Video-frame pixel (at plate zoom 1/PS, i.e. the whole plate shown)."""
        return self.ox + (lon - self.cx) * self.s, self.oy - (lat - self.cy) * self.s / self.K

    def _pproj(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.proj(lon, lat)
        return PW / 2 + (x - W / 2) * PS, PH / 2 + (y - H / 2) * PS

    def plate(self) -> Image.Image:
        return _cached("night", self.params, self._make)

    def lights(self) -> Image.Image:
        """City lights as their own layer, so a scene can fade them up."""
        return _cached("lights", self.params, self._make_lights)

    def _make(self) -> Image.Image:
        s = self.s * PS
        yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
        cx_p, cy_p = self._pproj(self.cx, self.cy)
        lon = self.cx + (xx - cx_p) / s
        lat = self.cy - (yy - cy_p) * self.K / s
        tex = texture("night", self.tints)
        rgb = sample(tex, lon.ravel(), lat.ravel()).reshape(PH, PW, 3)
        kx, ky = PW / 2 + (self.key_light[0] - W / 2) * PS, PH / 2 + (self.key_light[1] - H / 2) * PS
        d = np.hypot(xx - kx, yy - ky) / (1300 * PS)
        rgb = rgb * (1 + 0.32 * np.clip(1 - d, 0, 1)[..., None] * np.array([1.0, 0.92, 0.78]))
        base = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
        bs = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        bc = cairo.Context(bs)
        bc.set_antialias(cairo.ANTIALIAS_BEST)
        bc.set_line_join(cairo.LINE_JOIN_ROUND)
        borders(bc, self._pproj, 0.9, 0.34, 1.8 * s / 25)
        base = Image.alpha_composite(base, to_img(bs))
        return finish(np.asarray(base.convert("RGB")).astype(np.float32) / 255, 5, 0.5)

    def lights_of(self, name: str) -> Image.Image:
        """One country's city lights, so a scene can light the countries one by one."""
        return _cached("lights_" + name, self.params, lambda: self._make_lights(only=name))

    def edge(self, name: str) -> Image.Image:
        """A country picked out: a faint wash of its colour and a glowing outline.
        Pakistan's wash and outline stop at India's boundary."""
        return _cached("edge_" + name, self.params, lambda: self._make_edge(name))

    def flag_of(self, name: str, at: tuple[float, float] | None = None, fit: float = 0.8) -> Image.Image:
        """The country filled with its flag (India's official boundary; a neighbour's
        flag stops at it), with the map's relief showing through like cloth laid
        over the land. The emblem (chakra, crescent and star, red disc) sits in the
        middle of the country, sized to fit inside it; ``at`` (lon, lat) moves it.
        Full strength: a scene sets how much of it to show."""
        key = {**self.params, "flag_at": list(at) if at else None, "fit": fit}
        return _cached("flag2_" + name, key, lambda: self._make_flag(name, at, fit))

    def _make_flag(self, name: str, at: tuple[float, float] | None = None, fit: float = 0.8) -> Image.Image:
        from scipy import ndimage
        from . import flags

        ms = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        c = cairo.Context(ms)
        c.set_antialias(cairo.ANTIALIAS_BEST)

        def path(n: str) -> None:
            for r in rings(n):
                pts = [self._pproj(lo, la) for lo, la in r]
                c.move_to(*pts[0])
                for q in pts[1:]:
                    c.line_to(*q)
                c.close_path()

        path(name)
        c.set_source_rgba(0, 0, 0, 1)
        c.fill()
        if name != "India":
            c.set_operator(cairo.OPERATOR_CLEAR)
            path("India")
            c.fill()
        ms.flush()
        mask = np.frombuffer(ms.get_data(), np.uint8).reshape(PH, ms.get_stride() // 4, 4)[:, :PW, 3]
        mask = mask.astype(np.float32) / 255
        inside = mask > 0.5
        ys, xs = np.nonzero(inside)
        # the emblem's centre: roomy (far from the border) but near the middle of the
        # shape, so it reads as centred rather than pushed into one lobe
        dist = ndimage.distance_transform_edt(inside)
        if at:
            ex, ey = self._pproj(*at)
            r_in = float(dist[int(min(max(ey, 0), PH - 1)), int(min(max(ex, 0), PW - 1))])
        else:
            yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
            cy_, cx_ = ys.mean(), xs.mean()
            score = dist - 0.35 * np.hypot(xx - cx_, yy - cy_)
            iy, ix = np.unravel_index(np.argmax(np.where(inside, score, -1e9)), score.shape)
            ex, ey, r_in = float(ix), float(iy), float(dist[iy, ix])
        # size: the emblem fits inside the country; India's bands span the country
        fh = fit * r_in / flags.EMBLEM_R[name]
        if name == "India":
            fh = min(fh, float(ys.max() - ys.min()))
        fs = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        fc = cairo.Context(fs)
        fc.set_antialias(cairo.ANTIALIAS_BEST)
        flags.field(fc, name, ex, ey, fh, PW, PH)
        fs.flush()
        f = np.frombuffer(fs.get_data(), np.uint8).reshape(PH, fs.get_stride() // 4, 4)[:, :PW, [2, 1, 0]]
        rgb = f.astype(np.float32) / 255
        # relief from the map underneath, and a few soft folds
        base = np.asarray(self.plate().convert("L")).astype(np.float32)
        inside = mask > 0.5
        lum = base / max(1.0, float(base[inside].mean()))
        shade = 0.78 + 0.22 * np.clip(lum, 0.4, 1.8)
        yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
        u = (xx * 0.8 + yy * 0.6) / (210 * PS)
        shade *= 1 + 0.06 * np.sin(2 * np.pi * u) + 0.03 * np.sin(2 * np.pi * u * 2.3 + 1.1)
        rgb = np.clip(rgb * shade[..., None], 0, 1)
        out = np.dstack([rgb * 255, mask * 255]).astype(np.uint8)
        return Image.fromarray(out, "RGBA")

    def _make_edge(self, name: str) -> Image.Image:
        s = self.s * PS
        es = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        c = cairo.Context(es)
        c.set_antialias(cairo.ANTIALIAS_BEST)
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        rgb = COL_LIGHT[name]

        def path(n: str) -> None:
            for r in rings(n):
                pts = [self._pproj(lo, la) for lo, la in r]
                c.move_to(*pts[0])
                for q in pts[1:]:
                    c.line_to(*q)
                c.close_path()

        path(name)
        c.set_source_rgba(*rgb, 0.17)
        c.fill()
        if name != "India":
            c.set_operator(cairo.OPERATOR_CLEAR)
            path("India")
            c.fill()
            c.set_operator(cairo.OPERATOR_OVER)
        for r in rings(name):
            pts = [self._pproj(lo, la) for lo, la in r]
            skip = np.r_[in_india(r), in_india(r[:1])] if name == "Pakistan" else None
            _trace(c, pts + [pts[0]], skip)
        c.set_source_rgba(*rgb, 1.0)
        c.set_line_width(2.4 * s / 25)
        c.stroke()
        img = to_img(es)
        out = img.filter(ImageFilter.GaussianBlur(7 * s / 25))
        out.alpha_composite(img)
        return out

    def _make_lights(self, only: str | None = None) -> Image.Image:
        s = self.s * PS
        ls = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        lc = cairo.Context(ls)
        rng = np.random.default_rng(11)
        for n, pts in light_points():
            if only and n != only:
                continue
            for lo, la in pts:
                x, y = self._pproj(lo, la)
                lc.arc(x, y, rng.uniform(0.5, 1.3) * s / 25, 0, 2 * math.pi)
                lc.set_source_rgba(1.0, 0.84, 0.58, rng.uniform(0.15, 0.5))
                lc.fill()
        li = to_img(ls)
        glow = li.filter(ImageFilter.GaussianBlur(3 * s / 25))
        g = np.asarray(glow).astype(np.float32)
        g[..., 3] *= 0.6
        out = Image.fromarray(g.astype(np.uint8), "RGBA")
        out.alpha_composite(li)
        return out


# --------------------------------------------------------------------------- #
# Perspective terrain
# --------------------------------------------------------------------------- #
KX = 111.32 * math.cos(math.radians(22))
KY = 111.32


class TerrainView:
    """A camera over the terrain (low, looking north), golden-hour light."""

    def __init__(self, lon: float, lat: float, h_km: float, f: float, horizon: float, yaw_deg: float = 0.0,
                 exag: float = 11.0, z_near: float = 1500, z_far: float = 6300,
                 tints: dict[str, float] | None = None):
        self.x, self.y = (lon - 80) * KX, (lat - 22) * KY
        self.h, self.f, self.hz = h_km, f, horizon
        self.yaw = math.radians(yaw_deg)
        self.exag, self.z_near, self.z_far = exag, z_near, z_far
        self.tints = tints or {}
        self.params = {"cam": [lon, lat, h_km, f, horizon, yaw_deg, exag, z_near, z_far], "tints": self.tints}

    def proj(self, lon: float, lat: float, elev_m: float | None = None) -> tuple[float, float, float]:
        """Video-frame pixel (x, y) and forward distance of a ground point."""
        if elev_m is None:
            elev_m = elevation(lon, lat)
        X, Y = (lon - 80) * KX - self.x, (lat - 22) * KY - self.y
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        fwd = X * s + Y * c
        lat_off = X * c - Y * s
        Z = elev_m / 1000 * self.exag
        return W / 2 + lat_off / fwd * self.f, self.hz + (self.h - Z) / fwd * self.f, fwd

    def plate(self) -> Image.Image:
        return _cached("terrain", self.params, self._make)

    def _make(self, ss: int = 2) -> Image.Image:
        tex = texture("dusk", self.tints)
        height = terrain()["height"]
        Wr, Hr = PW * ss, PH * ss
        f = self.f * PS * ss
        hz = (PH / 2 + (self.hz - H / 2) * PS) * ss
        u = (np.arange(Wr) - Wr / 2 + 0.5) / f
        zs = [self.z_near]
        while zs[-1] < self.z_far:
            zs.append(zs[-1] * (1 + 1.32 / f))
        zs = np.array(zs)
        S = len(zs)
        Ys = np.empty((S, Wr), np.float32)
        Cs = np.empty((S, Wr, 3), np.float32)
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        haze = np.array([0.66, 0.58, 0.50])
        for i, z in enumerate(zs):
            lat_off = u * z
            X = self.x + lat_off * c + z * s
            Y = self.y - lat_off * s + z * c
            lon, lat = X / KX + 80, Y / KY + 22
            hgt = sample1(height, lon, lat)
            Ys[i] = hz + (self.h - hgt / 1000 * self.exag) / z * f
            col = sample(tex, lon, lat)
            fog = _smooth(self.z_far * 0.40, self.z_far * 0.98, z) ** 0.8
            Cs[i] = col * (1 - fog) + haze * fog
        Mn = np.minimum.accumulate(Ys, axis=0)
        rows = np.arange(Hr, dtype=np.float32)
        img = np.zeros((Hr, Wr, 3), np.float32)
        sky_top = np.array([0.40, 0.355, 0.32])
        y_hor = (hz + self.h / self.z_far * f) / Hr
        t = (rows / Hr)[:, None]
        sky = sky_top * (1 - _smooth(0, y_hor, t)) + haze * _smooth(0, y_hor, t)
        for x in range(Wr):
            idx = np.searchsorted(-Mn[:, x], -rows - 0.5, side="left")
            ok = idx < S
            img[ok, x] = Cs[idx[ok], x]
            img[~ok, x] = sky[~ok]
        del Cs, Ys, Mn
        im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((PW, PH), Image.LANCZOS)
        base = im.convert("RGBA")
        bs = cairo.ImageSurface(cairo.FORMAT_ARGB32, PW, PH)
        bc = cairo.Context(bs)
        bc.set_antialias(cairo.ANTIALIAS_BEST)
        bc.set_line_join(cairo.LINE_JOIN_ROUND)

        def pproj(lo, la):
            x, y, fwd = self.proj(lo, la)
            if fwd < self.z_near or fwd > self.z_far * 0.97:
                return None
            return PW / 2 + (x - W / 2) * PS, PH / 2 + (y - H / 2) * PS

        borders(bc, pproj, 0.95, 0.38, 1.7 * PS)
        base = Image.alpha_composite(base, to_img(bs))
        return finish(np.asarray(base.convert("RGB")).astype(np.float32) / 255, 4, 0.35)


TERRAIN_VIEWS = {
    # All three countries level at the starting line.
    "level": dict(lon=80.0, lat=-12.0, h_km=1500, f=1960, horizon=-340, exag=11, z_near=1500, z_far=6300,
                  tints={"India": 0.40, "Pakistan": 0.72, "Bangladesh": 0.62}),
    # Pakistan and Bangladesh at the two ends, India quiet between them.
    "flanks": dict(lon=80.5, lat=-8.0, h_km=1250, f=2150, horizon=-330, yaw_deg=-4, exag=11, z_near=1300,
                   z_far=6200, tints={"India": 0.12, "Pakistan": 0.72, "Bangladesh": 0.62}),
}

NIGHT_VIEWS = {
    "wide": dict(s=25.0, cx=80.0, cy=22.5, ox=1270, oy=560),
    "centre": dict(s=27.0, cx=80.5, cy=23.0, ox=960, oy=540),
    "east": dict(s=44.0, cx=86.0, cy=23.5, ox=1330, oy=560, tints={"India": 0.2, "Pakistan": 0.22, "Bangladesh": 0.75}),
}


def night(view: str) -> NightMap:
    return NightMap(**NIGHT_VIEWS[view])


def terrain_view(view: str) -> TerrainView:
    return TerrainView(**TERRAIN_VIEWS[view])


# --------------------------------------------------------------------------- #
# Silhouettes
# --------------------------------------------------------------------------- #
HEX = {"India": (194, 102, 43), "Pakistan": (46, 74, 120), "Bangladesh": (140, 35, 53)}


@lru_cache(maxsize=None)
def silhouette(name: str, height_px: int, rgb: tuple[int, int, int] | None = None) -> Image.Image:
    """A country's shape (India-subtracted for its neighbours), ``height_px`` tall."""
    m = masks()[name]
    ys, xs = np.where(m > 0.5)
    y0, y1, x0, x1 = ys.min() - 4, ys.max() + 5, xs.min() - 4, xs.max() + 5
    crop = m[y0:y1, x0:x1]
    rgba = np.zeros(crop.shape + (4,), np.uint8)
    rgba[..., :3] = rgb or HEX[name]
    rgba[..., 3] = (np.clip(crop, 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    im = im.resize((im.width, int(round(im.height / NightMap.K))), Image.LANCZOS)
    k = height_px / im.height
    return im.resize((max(1, int(im.width * k)), height_px), Image.LANCZOS)


# Where labels, cards and rings sit on each country (lon, lat).
COUNTRY_POINTS = {"India": (78.5, 22.0), "Pakistan": (69.8, 29.0), "Bangladesh": (90.3, 23.75)}
