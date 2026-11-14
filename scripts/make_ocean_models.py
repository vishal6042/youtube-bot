"""Make the 3D models for the ocean-depth episode (Science in Motion, ep. 1).

    .venv/Scripts/python.exe scripts/make_ocean_models.py [diver whale titanic snailfish]

Two steps:
1. paint the textures the models wear (whale scars, the Titanic's portholes,
   windows and rust) into a temp folder;
2. run Blender (scripts/blender/ocean_models.py), which builds the four models
   from scratch, animates them and renders each as a loop of transparent PNGs,
   assets/ocean/<name>/000.png ... (diver 40 poses, whale 48, snailfish 48, the
   Titanic's wrecked bow 1). graph_bot/sims/ocean_depth.py plays those; without
   them it falls back to its flat drawn sprites. About 10 minutes on an RTX 4090.

Blender is found from the BLENDER environment variable, else the portable build
in E:/tools/blender, else `blender` on PATH. Nothing is downloaded: every model
is original work made here.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "ocean"


def find_blender() -> str:
    cands = [os.environ.get("BLENDER", "")]
    cands += [str(p) for p in sorted(Path("E:/tools/blender").glob("blender-*/blender.exe"), reverse=True)]
    cands += [shutil.which("blender") or ""]
    for c in cands:
        if c and Path(c).exists():
            return c
    raise SystemExit("Blender not found: set BLENDER to blender.exe")


def _surface(w: int, h: int):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    return surf, ctx


def _rgb(surf) -> np.ndarray:
    surf.flush()
    w, h = surf.get_width(), surf.get_height()
    return np.ndarray((h, w, 4), np.uint8, surf.get_data())[..., 2::-1].astype(np.float32) / 255


def _alpha(surf) -> np.ndarray:
    surf.flush()
    w, h = surf.get_width(), surf.get_height()
    return np.ndarray((h, w, 4), np.uint8, surf.get_data())[..., 3].astype(np.float32) / 255


def _save(arr: np.ndarray, path: Path) -> None:
    Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(path)


def _noise(shape, sigma, seed):
    n = gaussian_filter(np.random.default_rng(seed).normal(0, 1, shape).astype(np.float32), sigma)
    return n / (np.abs(n).max() + 1e-9)


# --------------------------------------------------------------------------- #
# Cuvier's beaked whale: seen from the side. Left = tail, right = head; top = back.
# --------------------------------------------------------------------------- #
def paint_whale(path: Path) -> None:
    w, h = 4096, 1024
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h                                    # v: 0 back, 1 belly
    back = np.array([0.30, 0.25, 0.22], np.float32)          # rusty grey-brown
    flank = np.array([0.44, 0.38, 0.34], np.float32)
    belly = np.array([0.66, 0.63, 0.60], np.float32)
    t1 = np.clip((v - 0.15) / 0.40, 0, 1)[..., None]
    t2 = np.clip((v - 0.62) / 0.30, 0, 1)[..., None]
    col = (back * (1 - t1) + flank * t1) * (1 - t2) + belly * t2
    # older animals go pale from the head back
    pale = (np.clip((u - 0.66) / 0.26, 0, 1) ** 1.3 * (0.75 + 0.25 * _noise((h, w), 60, 1)))[..., None]
    col = col * (1 - 0.72 * pale) + np.array([0.86, 0.84, 0.80], np.float32) * 0.72 * pale
    col *= (1 + 0.10 * _noise((h, w), 90, 2) + 0.06 * _noise((h, w), 22, 3) + 0.03 * _noise((h, w), 5, 4))[..., None]
    # scars: long pale rake marks from other males' teeth, often in pairs
    surf, ctx = _surface(w, h)
    for _ in range(120):
        x0, y0 = rng.uniform(0.05, 0.98) * w, rng.uniform(0.04, 0.90) * h
        ang = rng.normal(0, 0.45) + (math.pi if rng.random() < 0.5 else 0)
        ln = rng.uniform(70, 620) * (1.4 if x0 > 0.6 * w else 1.0)
        bend = rng.normal(0, 0.25)
        wd = rng.uniform(1.2, 3.0)
        a = rng.uniform(0.10, 0.42)
        for off in ((0.0,) if rng.random() < 0.55 else (0.0, rng.uniform(9, 20))):
            ox, oy = -math.sin(ang) * off, math.cos(ang) * off
            x1, y1 = x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln
            mx = (x0 + x1) / 2 - math.sin(ang) * ln * bend * 0.3
            my = (y0 + y1) / 2 + math.cos(ang) * ln * bend * 0.3
            ctx.move_to(x0 + ox, y0 + oy)
            ctx.curve_to(mx + ox, my + oy, mx + ox, my + oy, x1 + ox, y1 + oy)
            ctx.set_source_rgba(0.93, 0.91, 0.87, a)
            ctx.set_line_width(wd)
            ctx.stroke()
    # cookie-cutter shark bites: small pale ovals and rings
    for _ in range(110):
        x0, y0 = rng.uniform(0.03, 0.97) * w, rng.uniform(0.10, 0.95) * h
        r = rng.uniform(6, 15)
        ctx.save()
        ctx.translate(x0, y0)
        ctx.rotate(rng.uniform(0, math.pi))
        ctx.scale(1.0, rng.uniform(0.6, 0.95))
        ctx.arc(0, 0, r, 0, 2 * math.pi)
        ctx.restore()
        if rng.random() < 0.45:
            ctx.set_source_rgba(0.92, 0.90, 0.86, rng.uniform(0.18, 0.5))
            ctx.set_line_width(rng.uniform(2, 4))
            ctx.stroke()
        else:
            ctx.set_source_rgba(0.90, 0.88, 0.84, rng.uniform(0.15, 0.5))
            ctx.fill()
    marks = gaussian_filter(_alpha(surf), 0.8)[..., None]
    col = col * (1 - marks) + np.array([0.92, 0.90, 0.86], np.float32) * marks
    # a darker smudge round the eye
    ex, ey = 0.888 * w, 0.535 * h
    smudge = np.exp(-(((xx - ex) / 46) ** 2 + ((yy - ey) / 30) ** 2))[..., None]
    col = col * (1 - 0.45 * smudge)
    _save(col, path)


# --------------------------------------------------------------------------- #
# RMS Titanic. Left = stern, right = bow.
# --------------------------------------------------------------------------- #
LEN_M = 269.0


def _px(u_from_bow: float, w: int) -> float:
    return (1 - u_from_bow) * w


def paint_titanic_hull(path: Path) -> None:
    """The hull from keel (bottom) to 24 m: anti-fouling red, black, the white
    sheer strake with its gold line, three rows of portholes, plating, rust."""
    w, h, top_m = 8192, 736, 24.0
    ppm = h / top_m
    rng = np.random.default_rng(21)

    def y(z_m):
        return h - z_m * ppm
    surf, ctx = _surface(w, h)
    ctx.set_source_rgb(0.030, 0.030, 0.034)                           # black topsides
    ctx.paint()
    ctx.rectangle(0, y(10.2), w, h)                                   # red below the waterline
    ctx.set_source_rgb(0.40, 0.11, 0.075)
    ctx.fill()
    ctx.rectangle(0, 0, w, y(20.4))                                   # white sheer strake
    ctx.set_source_rgb(0.86, 0.85, 0.80)
    ctx.fill()
    ctx.rectangle(0, y(20.4) - 5, w, 10)                              # the gold line
    ctx.set_source_rgb(0.80, 0.62, 0.16)
    ctx.fill()
    for z in np.arange(1.6, 20.0, 1.75):                              # plating strakes
        ctx.move_to(0, y(z))
        ctx.line_to(w, y(z))
        ctx.set_source_rgba(1, 1, 1, 0.055)
        ctx.set_line_width(1.6)
        ctx.stroke()
    for _ in range(520):                                              # butt joints
        x0, z0 = rng.uniform(0, w), 1.6 + 1.75 * rng.integers(0, 11)
        ctx.move_to(x0, y(z0))
        ctx.line_to(x0, y(z0 + 1.75))
        ctx.set_source_rgba(1, 1, 1, 0.05)
        ctx.set_line_width(1.4)
        ctx.stroke()
    ports = []
    for z, lo, hi in ((12.3, 0.045, 0.955), (15.0, 0.035, 0.965), (17.6, 0.03, 0.97), (21.8, 0.012, 0.145),
                      (21.8, 0.865, 0.985)):
        x_m = lo * LEN_M
        while x_m < hi * LEN_M:
            if rng.random() > 0.10:
                ports.append((_px(x_m / LEN_M, w), y(z)))
            x_m += rng.choice([2.1, 2.3, 2.3, 2.6, 4.4])
    for px_, py_ in ports:
        ctx.arc(px_, py_, 7.6, 0, 2 * math.pi)
        ctx.set_source_rgb(0.50, 0.38, 0.16)
        ctx.fill()
        ctx.arc(px_, py_, 5.2, 0, 2 * math.pi)
        ctx.set_source_rgb(0.012, 0.016, 0.022)
        ctx.fill()
    col = _rgb(surf)
    # rust: streaks weeping down from every porthole, heavier low on the hull
    surf2, c2 = _surface(w, h)
    for px_, py_ in ports:
        ln = rng.uniform(30, 150)
        g = cairo.LinearGradient(0, py_, 0, py_ + ln)
        g.add_color_stop_rgba(0, 1, 1, 1, rng.uniform(0.2, 0.55))
        g.add_color_stop_rgba(1, 1, 1, 1, 0)
        c2.set_source(g)
        c2.rectangle(px_ - rng.uniform(3, 7), py_, rng.uniform(6, 13), ln)
        c2.fill()
    streak = gaussian_filter(_alpha(surf2), (3, 1.6))
    drip = np.clip(gaussian_filter(np.random.default_rng(5).random((h, w)).astype(np.float32), (46, 1.2)) * 6 - 2.6, 0, 1)
    rust = np.clip(streak + 0.22 * drip * np.linspace(0.3, 1.0, h, dtype=np.float32)[:, None], 0, 1)[..., None]
    col = col * (1 - 0.8 * rust) + np.array([0.42, 0.19, 0.07], np.float32) * 0.8 * rust
    col *= (1 + 0.10 * _noise((h, w), 30, 7))[..., None]
    _save(col, path)


def paint_titanic_decks(path: Path) -> None:
    """The white upperworks, 20 m to 33 m above the keel: C-deck portholes, B-deck
    windows, the A-deck promenade (glazed forward, open aft), deck-house windows."""
    w, h, z0, z1 = 8192, 400, 20.0, 33.0
    ppm = h / (z1 - z0)
    rng = np.random.default_rng(31)

    def y(z_m):
        return h - (z_m - z0) * ppm
    surf, ctx = _surface(w, h)
    ctx.set_source_rgb(0.88, 0.87, 0.82)
    ctx.paint()
    glass = (0.035, 0.045, 0.055)
    for z in (23.2, 26.0, 28.9):                                      # deck edges: a thin shadow line
        ctx.rectangle(0, y(z) - 2, w, 4)
        ctx.set_source_rgba(0.2, 0.2, 0.2, 0.55)
        ctx.fill()
    x_m = 0.0
    while x_m < LEN_M:                                                # C deck: portholes
        if rng.random() > 0.08:
            ctx.arc(_px(x_m / LEN_M, w), y(21.8), 6.6, 0, 2 * math.pi)
            ctx.set_source_rgb(*glass)
            ctx.fill()
        x_m += rng.choice([2.1, 2.3, 2.5])
    x_m = 0.19 * LEN_M
    while x_m < 0.81 * LEN_M:                                         # B deck: tall windows, uneven
        if rng.random() > 0.12:
            ctx.rectangle(_px(x_m / LEN_M, w) - 0.32 * ppm, y(25.25), 0.64 * ppm, 1.0 * ppm)
            ctx.set_source_rgb(*glass)
            ctx.fill()
        x_m += rng.choice([1.5, 1.9, 1.9, 2.6])
    x_m = 0.205 * LEN_M
    while x_m < 0.80 * LEN_M:                                         # A deck promenade
        fwd = x_m < 0.47 * LEN_M
        ww, hh, step = (0.95, 1.25, 1.6) if fwd else (2.5, 1.75, 3.1)
        ctx.rectangle(_px(x_m / LEN_M, w) - ww / 2 * ppm, y(28.25), ww * ppm, hh * ppm)
        ctx.set_source_rgb(*((0.05, 0.065, 0.08) if fwd else (0.10, 0.09, 0.08)))
        ctx.fill()
        x_m += step
    x_m = 0.215 * LEN_M
    while x_m < 0.71 * LEN_M:                                         # deck houses
        if rng.random() > 0.2:
            ctx.rectangle(_px(x_m / LEN_M, w) - 0.3 * ppm, y(31.1), 0.6 * ppm, 0.9 * ppm)
            ctx.set_source_rgb(*glass)
            ctx.fill()
        x_m += rng.choice([2.2, 2.6, 3.4])
    col = _rgb(surf)
    drip = np.clip(gaussian_filter(np.random.default_rng(6).random((h, w)).astype(np.float32), (30, 1.2)) * 6 - 2.75, 0, 1)
    col = col * (1 - 0.35 * drip[..., None]) + np.array([0.46, 0.24, 0.10], np.float32) * 0.35 * drip[..., None]
    col *= (1 + 0.07 * _noise((h, w), 24, 8))[..., None]
    _save(col, path)


def main() -> None:
    names = sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    blender = find_blender()
    with tempfile.TemporaryDirectory() as tmp:
        tex = Path(tmp)
        paint_whale(tex / "whale.png")
        paint_titanic_hull(tex / "titanic_hull.png")
        paint_titanic_decks(tex / "titanic_decks.png")
        keep = os.environ.get("OCEAN_KEEP_TEX")
        if keep:
            for f in tex.glob("*.png"):
                shutil.copy(f, Path(keep) / f.name)
        cmd = [blender, "-b", "--factory-startup", "-P", str(ROOT / "scripts" / "blender" / "ocean_models.py"),
               "--", str(OUT), str(tex), *names]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = [ln for ln in res.stdout.splitlines() if ln.startswith(("==", "rendered", "GPU", "Error", "Traceback"))
                or "Error" in ln]
        print("\n".join(tail[-30:]))
        if res.returncode != 0 or "Traceback" in res.stdout + res.stderr:
            print(res.stdout[-3000:])
            print(res.stderr[-3000:])
            raise SystemExit("Blender failed")


if __name__ == "__main__":
    main()
