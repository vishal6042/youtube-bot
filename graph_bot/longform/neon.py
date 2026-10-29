"""The "neon" look for long-form data chapters (bar races and head-to-heads).

Same data, same motion as render.py (it reuses the race timeline and the
smoothed curves), drawn in the style of the animated intro and outro: the
deep-space backdrop, a metallic rank badge and year, glossy bars with medal
rims, glowing lines, flag tags. Everything is drawn with cairo straight into
the frames sent to ffmpeg, which is faster than the matplotlib renderer.

An episode opts in with ``style: neon``; other episodes keep the old look.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

import cairo
import numpy as np
import pandas as pd
from PIL import Image

from . import fx
from .. import render as R

VERSION = 2   # 2: labels fade while bars overlap mid-swap
W, H = fx.W, fx.H
SAFF = (1.0, 0.6, 0.2)
COOL = [(0.30, 0.79, 0.94), (0.62, 0.31, 0.87), (0.37, 0.88, 0.78), (0.97, 0.15, 0.52), (0.63, 0.77, 1.0)]
MEDAL = {0: (1.0, 0.82, 0.25), 1: (0.86, 0.89, 0.95), 2: (0.91, 0.60, 0.32)}
_KEEP: dict[int, bytearray] = {}


# --------------------------------------------------------------------------- #
# Cairo helpers
# --------------------------------------------------------------------------- #
def to_surface(img: Image.Image) -> cairo.ImageSurface:
    """A PIL RGBA image as a premultiplied cairo surface (kept alive with it)."""
    arr = np.asarray(img.convert("RGBA")).astype(np.float32)
    a = arr[..., 3:4] / 255.0
    bgra = np.concatenate([arr[..., 2:3] * a, arr[..., 1:2] * a, arr[..., 0:1] * a, arr[..., 3:4]], axis=2)
    h, w = bgra.shape[:2]
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, w)
    buf = np.zeros((h, stride // 4, 4), np.uint8)
    buf[:, :w] = np.clip(bgra, 0, 255).astype(np.uint8)
    data = bytearray(buf.tobytes())
    surf = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, stride)
    _KEEP[id(surf)] = data   # cairo reads this buffer for as long as the surface lives
    return surf


def blit(ctx: cairo.Context, s: cairo.ImageSurface, x: float, y: float, a: float = 1.0,
         anchor: str = "mm") -> None:
    ox = {"l": 0, "m": s.get_width() / 2, "r": s.get_width()}[anchor[0]]
    oy = {"t": 0, "m": s.get_height() / 2, "b": s.get_height()}[anchor[1]]
    ctx.set_source_surface(s, round(x - ox), round(y - oy))
    ctx.paint_with_alpha(a) if a < 0.999 else ctx.paint()


def rrect(ctx: cairo.Context, x0: float, y0: float, x1: float, y1: float, r: float) -> None:
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.arc(x1 - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    ctx.arc(x1 - r, y1 - r, r, 0, 0.5 * math.pi)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()


def text(ctx: cairo.Context, s: str, x: float, y: float, size: float, rgb, weight: str = "bold",
         anchor: str = "l", alpha: float = 1.0, glow: float = 0.0) -> float:
    """Draw text with its vertical centre on ``y``; returns its width."""
    # Cairo's toy font API on Windows only resolves the "Segoe UI" family (Black
    # and Semibold fall back to Arial), so every weight but regular is its bold.
    wt = cairo.FONT_WEIGHT_NORMAL if weight == "regular" else cairo.FONT_WEIGHT_BOLD
    ctx.select_font_face("Segoe UI", cairo.FONT_SLANT_NORMAL, wt)
    ctx.set_font_size(size)
    ext = ctx.text_extents(s)
    fe = ctx.font_extents()
    tx = {"l": x, "m": x - ext.x_advance / 2, "r": x - ext.x_advance}[anchor]
    ty = y + (fe[0] - fe[1]) / 2 - fe[0] * 0.08
    if glow:
        ctx.move_to(tx, ty)
        ctx.text_path(s)
        for w, a in ((10, 0.05), (6, 0.10), (3, 0.18)):
            ctx.set_source_rgba(*rgb, a * glow * alpha)
            ctx.set_line_width(w)
            ctx.stroke_preserve()
        ctx.new_path()
    ctx.move_to(tx + 2, ty + 3)          # shadow
    ctx.set_source_rgba(0, 0, 0, 0.45 * alpha)
    ctx.show_text(s)
    ctx.move_to(tx, ty)
    ctx.set_source_rgba(*rgb, alpha)
    ctx.show_text(s)
    return ext.x_advance


class Stream:
    """BGRA frames (cairo's native layout) straight into ffmpeg."""

    def __init__(self, path: Path, ffmpeg: str, encode_args: list[str]):
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
             "-r", str(fx.FPS), "-i", "-", *encode_args, "-pix_fmt", "yuv420p", str(path)],
            stdin=subprocess.PIPE)

    def write(self, surf: cairo.ImageSurface) -> None:
        surf.flush()
        self.proc.stdin.write(bytes(surf.get_data()))

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg failed writing the chart")


# --------------------------------------------------------------------------- #
# Shared frame furniture
# --------------------------------------------------------------------------- #
def _tone(badge: str) -> str:
    m = re.match(r"#(\d+)", badge or "")
    if not m:
        return "teal"
    n = int(m.group(1))
    return {1: "gold", 2: "silver", 3: "bronze"}.get(n, "teal" if n <= 5 else "red")


def split_heading(heading: str) -> tuple[str, str]:
    """'#144 · Income per person' -> ('#144', 'Income per person')."""
    m = re.match(r"\s*(#\d+)\s*[·:\-–]?\s*(.*)$", heading or "")
    return (m.group(1), m.group(2)) if m else ("", heading or "")


def _flag(name: str, h: int) -> cairo.ImageSurface | None:
    from ..flags import flag_image
    from PIL import ImageDraw

    a = flag_image(name)
    if a is None:
        return None
    img = Image.fromarray((np.asarray(a) * 255).astype(np.uint8)).convert("RGBA")
    w = int(img.width * h / img.height)
    big = img.resize((w * 3, h * 3), Image.LANCZOS)
    m = Image.new("L", big.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, big.width - 1, big.height - 1], radius=int(h * 0.9), fill=255)
    big.putalpha(m)
    return to_surface(big.resize((w, h), Image.LANCZOS))


class Frame:
    """The parts every chart frame shares: backdrop, header, year, progress."""

    def __init__(self, heading: str, subtitle: str, source: str, footer: str):
        self.bg = to_surface(fx.backdrop(map_alpha=0.10))
        badge, title = split_heading(heading)
        head = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
        x = 70
        if badge:
            b = fx.metal_text(badge, 104, _tone(badge))
            fx.paste(head, b, x, 112, anchor="lm")
            x += fx.font(104, "black").getlength(badge) + 70
        fx.paste(head, fx.text(title, 62, fx.FG, "black"), x - 8, 88, anchor="lm")
        sub = " · ".join(s for s in (subtitle, source) if s)
        fx.paste(head, fx.text(sub, 30, (170, 182, 204), "semibold", shadow=False), x - 4, 148, anchor="lm")
        self.head = to_surface(head)
        self.footer = to_surface(fx.text(footer, 22, (70, 84, 120), "bold", shadow=False)) if footer else None
        self.years: dict[int, cairo.ImageSurface] = {}
        self.ghosts: dict[int, cairo.ImageSurface] = {}
        self.motes = fx.particles(50)

    def year(self, y: int) -> tuple[cairo.ImageSurface, cairo.ImageSurface]:
        if y not in self.years:
            self.years[y] = to_surface(fx.metal_text(str(y), 132, "silver"))
            self.ghosts[y] = to_surface(fx.text(str(y), 420, (255, 255, 255), "black", shadow=False))
        return self.years[y], self.ghosts[y]

    def begin(self, year: int, t: float) -> tuple[cairo.ImageSurface, cairo.Context]:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        ctx = cairo.Context(surf)
        ctx.set_antialias(cairo.ANTIALIAS_BEST)
        ctx.set_source_surface(self.bg, 0, 0)
        ctx.paint()
        yr, ghost = self.year(year)
        blit(ctx, ghost, W - 120, H - 240, 0.035, anchor="rm")
        fx.draw_particles(ctx, self.motes, t, 0.8)
        blit(ctx, self.head, 0, 0, anchor="lt")
        blit(ctx, yr, W - 70, 112, anchor="rm")
        if self.footer is not None:
            blit(ctx, self.footer, 96 - 8, H - 26, 0.9, anchor="lm")
        return surf, ctx

    @staticmethod
    def progress(ctx: cairo.Context, u: float, y: float = H - 70, x0: float = 96, x1: float = W - 96) -> None:
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(x0, y)
        ctx.line_to(x1, y)
        ctx.set_source_rgba(1, 1, 1, 0.08)
        ctx.set_line_width(6)
        ctx.stroke()
        xe = x0 + (x1 - x0) * fx.clamp(u)
        g = cairo.LinearGradient(x0, 0, x1, 0)
        g.add_color_stop_rgb(0, 0.37, 0.88, 0.78)
        g.add_color_stop_rgb(1, 1.0, 0.6, 0.2)
        for w, a in ((14, 0.15), (6, 1.0)):
            ctx.move_to(x0, y)
            ctx.line_to(max(x0 + 0.1, xe), y)
            ctx.push_group()
            ctx.set_source(g)
            ctx.set_line_width(w)
            ctx.stroke()
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(a)
        for r, a in ((14, 0.2), (6, 1.0)):
            ctx.arc(xe, y, r, 0, 2 * math.pi)
            ctx.set_source_rgba(1, 0.85, 0.6, a)
            ctx.fill()


def _tick_labels(ticks: list[float], topic: dict[str, Any]) -> list[str]:
    """Axis labels with the fewest decimals that still show each tick exactly
    ("80 yrs", "0.5B"), not the chart's value precision ("80.0 yrs", "0.50B")."""
    scale = float(topic.get("value_scale") or 1)
    for d in range(0, 4):
        if all(abs(round(tv / scale, d) - tv / scale) < 1e-9 for tv in ticks):
            break
    t2 = {**topic, "value_decimals": d}
    return [R._fmt(tv, t2) if tv else "0" for tv in ticks]


def _value(v: float, topic: dict[str, Any], prefix: str) -> str:
    return prefix + R._fmt(float(v), topic)


# --------------------------------------------------------------------------- #
# Bar race
# --------------------------------------------------------------------------- #
def render_bar_race(wide: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path,
                    heading: str, prefix: str, footer: str, encode_args: list[str]) -> float:
    fps = fx.FPS
    years = list(wide.index)
    steps = max(1, int(round(fps * R._seconds_per_year(topic, settings, len(years)))))
    frames = R._race_frames(wide, steps, fps, fps)
    ents = list(wide.columns)
    n = len(ents)
    hero = topic.get("highlight")
    base = Frame(heading, topic.get("subtitle", ""), topic.get("source", ""), footer)
    flags = {e: _flag(e, 40) for e in ents} if topic.get("flags", True) else {}

    x0, x1 = 430, 1640
    top, bottom = 232, 950
    rowh = (bottom - top) / n
    bh = min(56.0, rowh * 0.74)
    out = Stream(out_path, R.ffmpeg_exe(settings), encode_args)
    try:
        for idx, (yr, vals, pos) in enumerate(frames):
            t = idx / fps
            surf, ctx = base.begin(int(round(yr)), t)
            # Smaller values first, so an overtaking bar is drawn over the one
            # it passes. While two bars overlap mid-swap, the smaller one's
            # labels fade out, so the names never print on top of each other.
            order = sorted(ents, key=lambda e: float(vals[e]))
            vmax = max(float(vals.max()), 1e-9)
            label_a = {}
            for e in ents:
                a = 1.0
                for o in ents:
                    if o != e and float(vals[o]) >= float(vals[e]):
                        d = abs(pos[e] - pos[o])
                        a = min(a, fx.clamp((d - 0.25) / 0.6))
                label_a[e] = a
            for e in order:
                p = pos[e]
                y = top + (n - 1 - p) * rowh + (rowh - bh) / 2
                cy = y + bh / 2
                v = float(vals[e])
                L = max(bh * 1.1, (x1 - x0) * v / vmax)
                rank = n - 1 - int(round(p))
                is_hero = e == hero
                if is_hero:   # soft halo
                    for k in range(7, 0, -1):
                        g = k * 4
                        rrect(ctx, x0 - g, y - g, x0 + L + g, y + bh + g, bh / 2 + g)
                        ctx.set_source_rgba(1.0, 0.55, 0.15, 0.022)
                        ctx.fill()
                rrect(ctx, x0, y, x0 + L, y + bh, bh / 2)
                grad = cairo.LinearGradient(x0, 0, x0 + L, 0)
                if is_hero:
                    grad.add_color_stop_rgb(0, 0.85, 0.35, 0.05)
                    grad.add_color_stop_rgb(1, 1.0, 0.72, 0.30)
                else:
                    grad.add_color_stop_rgb(0, 0.10, 0.17, 0.36)
                    grad.add_color_stop_rgb(1, 0.24, 0.38, 0.70)
                ctx.set_source(grad)
                ctx.fill_preserve()
                if rank in MEDAL:
                    ctx.set_source_rgba(*MEDAL[rank], 0.95)
                    ctx.set_line_width(3)
                else:
                    ctx.set_source_rgba(0.55, 0.7, 1.0, 0.0 if is_hero else 0.22)
                    ctx.set_line_width(1.5)
                ctx.stroke()
                # Glass sheen on the upper part of the bar.
                ctx.save()
                rrect(ctx, x0, y, x0 + L, y + bh, bh / 2)
                ctx.clip()
                sh = cairo.LinearGradient(0, y, 0, y + bh * 0.5)
                sh.add_color_stop_rgba(0, 1, 1, 1, 0.24 if is_hero else 0.11)
                sh.add_color_stop_rgba(1, 1, 1, 1, 0)
                ctx.rectangle(x0, y, L, bh * 0.5)
                ctx.set_source(sh)
                ctx.fill()
                ctx.restore()
                # Name, flag, value.
                la = label_a[e]
                if la <= 0.01:
                    continue
                name_rgb = SAFF if is_hero else (0.89, 0.91, 0.96)
                text(ctx, e, x0 - 98, cy, 33, name_rgb, "black" if is_hero else "bold", anchor="r", alpha=la)
                fl = flags.get(e)
                if fl is not None:
                    blit(ctx, fl, x0 - 52, cy, la)
                label = _value(v, topic, prefix)
                if is_hero:
                    text(ctx, label, x0 + L + 18, cy, 38, (1.0, 0.75, 0.38), "black", glow=1.0, alpha=la)
                else:
                    text(ctx, label, x0 + L + 18, cy, 33, (0.96, 0.97, 0.99), "black", alpha=la)
            Frame.progress(ctx, idx / max(1, len(frames) - 1))
            out.write(surf)
            _tell(settings, idx, len(frames))
    finally:
        out.close()
    return len(frames) / fps


# --------------------------------------------------------------------------- #
# Head-to-head lines
# --------------------------------------------------------------------------- #
def render_line_multi(wide: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path,
                      heading: str, prefix: str, footer: str, encode_args: list[str]) -> float:
    from matplotlib.ticker import MaxNLocator

    fps = fx.FPS
    xs = [int(y) for y in wide.index]
    names = list(wide.columns)
    steps = max(1, int(round(fps * R._seconds_per_year(topic, settings, len(xs)))))
    paths = {nm: R._smooth_path(xs, [float(v) for v in wide[nm].values], steps) for nm in names}
    cx_all = paths[names[0]][0]
    curves = {nm: p[1] for nm, p in paths.items()}
    n_pts = len(cx_all)
    frames = list(range(n_pts)) + [n_pts - 1] * fps
    hero = topic.get("highlight") if topic.get("highlight") in names else None
    others = [nm for nm in names if nm != hero]
    cols = {nm: COOL[i % len(COOL)] for i, nm in enumerate(others)}
    if hero:
        cols[hero] = SAFF
    base = Frame(heading, topic.get("subtitle", ""), topic.get("source", ""), footer)
    flags = {nm: _flag(nm, 32) for nm in names} if topic.get("flags", True) else {}

    ymax = max(float(wide[nm].max()) for nm in names)
    ticks = [t for t in MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]).tick_values(0, ymax * 1.08) if t >= 0]
    top_v = max(ticks[-1], ymax * 1.08)
    X0, X1, Y0, Y1 = 190, 1440, 250, 930
    lo, hi = xs[0], xs[-1]
    X = lambda yr: X0 + (X1 - X0) * (yr - lo) / max(1, hi - lo)  # noqa: E731
    Y = lambda v: Y1 - (Y1 - Y0) * v / top_v  # noqa: E731
    year_ticks = [int(t) for t in MaxNLocator(nbins=6, integer=True).tick_values(lo, hi) if lo <= t <= hi]
    tick_labels = _tick_labels(ticks, topic)
    rng = np.random.default_rng(5)
    sparks = rng.uniform(0, 1, (28, 4))

    out = Stream(out_path, R.ffmpeg_exe(settings), encode_args)
    try:
        for idx, k in enumerate(frames):
            t = idx / fps
            cx = float(cx_all[k])
            surf, ctx = base.begin(int(round(cx)), t)
            # Grid and axis labels.
            ctx.set_dash([2, 10])
            for tv in ticks:
                y = Y(tv)
                ctx.move_to(X0, y)
                ctx.line_to(X1, y)
                ctx.set_source_rgba(0.6, 0.7, 1.0, 0.18)
                ctx.set_line_width(1.5)
                ctx.stroke()
            ctx.set_dash([])
            for tv, lab in zip(ticks, tick_labels):
                text(ctx, lab, X0 - 26, Y(tv), 24, (0.55, 0.6, 0.69), "semibold", anchor="r")
            for yt in year_ticks:
                text(ctx, str(yt), X(yt), Y1 + 36, 24, (0.55, 0.6, 0.69), "semibold", anchor="m")
            # Lines: others first, the hero on top with an area fill.
            heads = {}
            for nm in others + ([hero] if hero else []):
                xsx = [X(v) for v in cx_all[: k + 1]]
                ys = [Y(float(v)) for v in curves[nm][: k + 1]]
                is_hero = nm == hero
                if is_hero:
                    ctx.move_to(xsx[0], Y1)
                    for a, b in zip(xsx, ys):
                        ctx.line_to(a, b)
                    ctx.line_to(xsx[-1], Y1)
                    ctx.close_path()
                    g = cairo.LinearGradient(0, Y0, 0, Y1)
                    g.add_color_stop_rgba(0, *SAFF, 0.30)
                    g.add_color_stop_rgba(1, *SAFF, 0.0)
                    ctx.set_source(g)
                    ctx.fill()
                widths = ((26, 0.06), (16, 0.12), (8, 1.0)) if is_hero else ((14, 0.06), (8, 0.12), (4.5, 0.95))
                for lw, a in widths:
                    ctx.new_path()
                    ctx.move_to(xsx[0], ys[0])
                    for a2, b2 in zip(xsx[1:], ys[1:]):
                        ctx.line_to(a2, b2)
                    ctx.set_source_rgba(*cols[nm], a)
                    ctx.set_line_width(lw)
                    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
                    ctx.stroke()
                hx, hy = xsx[-1], ys[-1]
                heads[nm] = (hx, hy, float(curves[nm][k]))
                for r, a in ((24 if is_hero else 15, 0.18), (11 if is_hero else 8, 0.5)):
                    ctx.arc(hx, hy, r, 0, 2 * math.pi)
                    ctx.set_source_rgba(*cols[nm], a)
                    ctx.fill()
                ctx.arc(hx, hy, 6 if is_hero else 5, 0, 2 * math.pi)
                ctx.set_source_rgba(1, 0.96, 0.88, 1)
                ctx.fill()
            if hero:   # sparks trailing the hero's head
                hx, hy, _ = heads[hero]
                for s in sparks:
                    ph = (t * (0.6 + s[3]) + s[0]) % 1.0
                    d = 10 + 70 * ph
                    ang = math.pi * (0.75 + 0.5 * s[1])
                    ctx.arc(hx + math.cos(ang) * d, hy + math.sin(ang) * d * 0.5 - 6 * ph, 1 + 2 * s[2], 0,
                            2 * math.pi)
                    ctx.set_source_rgba(1, 0.8, 0.45, 0.9 * (1 - ph))
                    ctx.fill()
            # End tags, pushed apart so they never overlap.
            order = sorted(names, key=lambda nm: heads[nm][1])
            placed: list[float] = []
            for nm in order:
                hx, hy, v = heads[nm]
                y = hy
                if placed and y - placed[-1] < 64:
                    y = placed[-1] + 64
                placed.append(y)
            shift = max(0.0, placed[-1] - (Y1 - 14)) if placed else 0
            for nm, y in zip(order, placed):
                hx, _, v = heads[nm]
                y -= shift
                is_hero = nm == hero
                tx = hx + 34
                w = 380
                for g in range(4, 0, -1):
                    rrect(ctx, tx - g * 3, y - 28 - g * 3, tx + w + g * 3, y + 28 + g * 3, 28 + g * 3)
                    ctx.set_source_rgba(*cols[nm], 0.035)
                    ctx.fill()
                rrect(ctx, tx, y - 28, tx + w, y + 28, 28)
                ctx.set_source_rgba(0.05, 0.07, 0.15, 0.92)
                ctx.fill_preserve()
                ctx.set_source_rgba(*cols[nm], 1)
                ctx.set_line_width(3)
                ctx.stroke()
                fl = flags.get(nm)
                nx = tx + 18
                if fl is not None:
                    blit(ctx, fl, nx, y, anchor="lm")
                    nx += fl.get_width() + 12
                label = R.SHORT_NAMES.get(nm, nm) if len(nm) > 12 else nm
                text(ctx, label, nx, y, 27, cols[nm] if is_hero else (0.95, 0.96, 0.99),
                     "black" if is_hero else "bold")
                text(ctx, _value(v, topic, prefix), tx + w - 18, y, 27, (1, 1, 1), "black", anchor="r")
            Frame.progress(ctx, idx / max(1, len(frames) - 1))
            out.write(surf)
            _tell(settings, idx, len(frames))
    finally:
        out.close()
    return len(frames) / fps


def _tell(settings: dict[str, Any], i: int, n: int) -> None:
    cb = settings.get("_progress")
    if cb:
        cb(i, n)


def render(mode: str, data: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path,
           heading: str, prefix: str, footer: str, encode_args: list[str]) -> float:
    fn = {"bar_race": render_bar_race, "line_multi": render_line_multi}[mode]
    return fn(data, topic, settings, out_path, heading, prefix, footer, encode_args)


SUPPORTED = ("bar_race", "line_multi")
