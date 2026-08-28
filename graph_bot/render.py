"""Video renderers: turn prepared data into a vertical MP4.

All modes output 1080x1920 (portrait) MP4 via ffmpeg:
  * bar_race    -> top-N horizontal bars that race/overtake over the years
  * line_grow   -> a single line that grows across the timeline
  * line_multi  -> a few named entities compared head-to-head
  * bump_race   -> rank lines that visibly cross when places change
  * waffle_grow -> a 100-dot grid filling as a percentage moves

Implemented directly on matplotlib.animation.FuncAnimation for full control of
the portrait layout and on-frame overlays (title, year, value labels, credit).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import animation  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.offsetbox import AnnotationBbox, OffsetImage  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

FG = "#f2f5fa"
MUTED = "#9aa4b2"
ACCENT = "#5ee0c8"
GRID = "#2a3350"
BG_TOP = "#182140"
BG_BOTTOM = "#0a0e1c"

# Vibrant, modern, well-separated palette for the bars.
PALETTE = [
    "#5ee0c8", "#4cc9f0", "#4895ef", "#4361ee", "#7b6cf6", "#9d4edd",
    "#c65fd6", "#f72585", "#ff5d8f", "#ff7b54", "#ff9e00", "#ffd60a",
    "#c8e64d", "#7ed957", "#2ec4b6", "#00bbf9", "#a0c4ff", "#ffadad",
    "#fdffb6", "#caffbf",
]
MEDALS = {0: "#ffd60a", 1: "#c9d1d9", 2: "#e8994e"}  # gold / silver / bronze rim


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render(mode: str, data: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path) -> float:
    """Render the video and return its duration in seconds."""
    _ensure_ffmpeg(settings)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "line_multi":
        return _render_multi_line(data, topic, settings, out_path)
    if mode == "line_grow":
        return _render_line(data, topic, settings, out_path)
    if mode == "bump_race":
        return _render_bump_race(data, topic, settings, out_path)
    if mode == "waffle_grow":
        return _render_waffle(data, topic, settings, out_path)
    return _render_bar_race(data, topic, settings, out_path)


# --------------------------------------------------------------------------- #
# Bar chart race
# --------------------------------------------------------------------------- #
def _render_bar_race(wide: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path) -> Path:
    vconf = settings.get("video", {})
    width, height = vconf.get("width", 1080), vconf.get("height", 1920)
    fps = int(vconf.get("fps", 30))
    years = list(wide.index)
    steps = max(1, int(round(fps * _seconds_per_year(topic, settings, len(years)))))
    dpi = 100

    entities = list(wide.columns)
    colors = _color_map(entities)

    # Rank of every entity in every year (0 = bottom bar). Bars are drawn at an
    # interpolated rank rather than at the current sort order, so an overtake
    # glides the two bars past each other instead of swapping them between
    # frames — the snap that made the motion look sudden.
    rank_by_year = [
        {ent: r for r, ent in enumerate(wide.iloc[i].sort_values(ascending=True).index)}
        for i in range(len(years))
    ]

    # Build interpolated frames between successive years, plus an end hold.
    frames: list[tuple[float, pd.Series, dict[str, float]]] = []
    for i in range(len(years) - 1):
        v0, v1 = wide.iloc[i], wide.iloc[i + 1]
        r0, r1 = rank_by_year[i], rank_by_year[i + 1]
        for s in range(steps):
            f = s / steps
            # Values move linearly (steady growth); ranks are eased, because a
            # rank change is a discrete event and easing is what sells the slide.
            fe = _ease(f)
            pos = {e: r0[e] + (r1[e] - r0[e]) * fe for e in entities}
            frames.append((years[i] + (years[i + 1] - years[i]) * f, v0 + (v1 - v0) * f, pos))
    final_pos = {e: float(r) for e, r in rank_by_year[-1].items()}
    frames.extend([(years[-1], wide.iloc[-1], final_pos)] * fps)  # 1s hold

    # Country flags (skipped for org/company topics via `flags: false`).
    flag_imgs: dict[str, Any] = {}
    if topic.get("flags", True):
        from . import flags as flagmod

        flag_imgs = flagmod.preload(entities)
        if flag_imgs:
            print(f"  🏴 flags: {len(flag_imgs)}/{len(entities)} matched")

    n_bars = len(entities)
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_BOTTOM)
    # Flags sit between the label and the bar, so labels need extra room.
    fig.subplots_adjust(left=0.38 if flag_imgs else 0.32, right=0.90, top=0.85, bottom=0.09)
    _add_gradient_bg(fig)
    n_frames = len(frames)

    def draw(idx: int) -> None:
        yr, vals, pos = frames[idx]
        ax.clear()
        ax.set_facecolor("none")
        # Bottom-to-top by drawn position, so medals and labels follow the bar
        # that is visually on top even midway through a swap.
        order = sorted(entities, key=lambda e: pos[e])
        positions = np.array([pos[e] for e in order])
        values = np.array([float(vals[e]) for e in order])
        vmax = float(values.max()) or 1.0
        xlim = vmax * 1.20

        rank_from_top = {ent: len(order) - 1 - i for i, ent in enumerate(order)}
        bar_colors = [colors[e] for e in order]
        edge_colors = [MEDALS.get(rank_from_top[e], "none") for e in order]
        line_widths = [3.0 if rank_from_top[e] in MEDALS else 0 for e in order]
        ax.barh(positions, values, height=0.72, color=bar_colors,
                edgecolor=edge_colors, linewidth=line_widths, zorder=3)

        for p, ent, val in zip(positions, order, values):
            ax.text(val + vmax * 0.015, p, _fmt(val, topic), va="center", ha="left",
                    color=FG, fontsize=14, fontweight="bold", zorder=4)

        ax.set_yticks(positions)
        ax.set_yticklabels(order, color=FG, fontsize=14)

        # Flags sit just left of the bar, inside the plot area.
        if flag_imgs:
            for p, ent in zip(positions, order):
                img = flag_imgs.get(ent)
                if img is None:
                    continue
                box = OffsetImage(img, zoom=0.40)
                ab = AnnotationBbox(
                    box, (0, p), xybox=(-14, 0), xycoords="data",
                    boxcoords="offset points", frameon=False,
                    box_alignment=(1.0, 0.5), annotation_clip=False, zorder=5,
                )
                ax.add_artist(ab)

        ax.set_xlim(0, xlim)
        ax.set_ylim(-0.7, n_bars - 0.3)
        ax.set_xticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
        if flag_imgs:
            # Flags occupy roughly -14..-46 points; keep labels clear of them.
            ax.tick_params(axis="y", pad=54)

        # Big year, bottom-right.
        ax.text(0.98, 0.05, str(int(round(yr))), transform=ax.transAxes,
                ha="right", va="bottom", color=ACCENT, alpha=0.30,
                fontsize=70, fontweight="bold", zorder=2)
        _progress_bar(ax, idx / max(1, n_frames - 1))

    _title_block(fig, topic, settings)
    anim = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    _save(anim, out_path, fps, dpi, settings)
    plt.close(fig)
    return len(frames) / fps


# --------------------------------------------------------------------------- #
# Growing line
# --------------------------------------------------------------------------- #
def _render_line(series_df: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], out_path: Path) -> Path:
    vconf = settings.get("video", {})
    width, height = vconf.get("width", 1080), vconf.get("height", 1920)
    fps = int(vconf.get("fps", 30))
    xs = [int(y) for y in series_df.index]
    steps = max(1, int(round(fps * _seconds_per_year(topic, settings, len(xs)))))
    dpi = 100

    ys = [float(v) for v in series_df["value"].values]
    ymax = max(ys) if ys else 1.0
    log_scale = bool(topic.get("log_scale"))
    # Log axes need a positive floor to fill/plot against.
    ymin_pos = min([v for v in ys if v > 0], default=1.0)
    ybase = ymin_pos / 5.0 if log_scale else 0.0

    # One dense curve through the yearly points; the animation then walks it, so
    # the trail and the moving head are the same smooth path with no corner at
    # each year.
    curve_x, curve_y = _smooth_path(xs, ys, steps, log_scale)
    n_pts = len(curve_x)
    frames: list[int] = list(range(n_pts)) + [n_pts - 1] * fps  # + 1s end hold

    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_BOTTOM)
    fig.subplots_adjust(left=0.16, right=0.92, top=0.82, bottom=0.11)
    _add_gradient_bg(fig)
    n_frames = len(frames)

    def draw(idx: int) -> None:
        k = frames[idx]
        cx, cy = float(curve_x[k]), float(curve_y[k])
        ax.clear()
        ax.set_facecolor("none")
        line_x = curve_x[: k + 1]
        line_y = curve_y[: k + 1]
        # Soft glow: a few translucent fills stacked under the line.
        for alpha in (0.06, 0.10, 0.16):
            ax.fill_between(line_x, line_y, ybase, color=ACCENT, alpha=alpha)
        ax.plot(line_x, line_y, color=ACCENT, linewidth=5, solid_capstyle="round", zorder=4)
        ax.scatter([cx], [cy], color=FG, s=90, zorder=5,
                   edgecolors=ACCENT, linewidths=2)

        ax.set_xlim(xs[0], xs[-1])
        if log_scale:
            ax.set_yscale("log")
            ax.set_ylim(ybase, ymax * 4)
        else:
            ax.set_ylim(0, ymax * 1.15)
        ax.grid(True, color=GRID, alpha=0.35)
        ax.tick_params(colors=MUTED, labelsize=13)
        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.text(0.04, 0.95, _fmt(cy, topic), transform=ax.transAxes, ha="left", va="top",
                color=FG, fontsize=40, fontweight="bold")
        ax.text(0.98, 0.05, str(int(round(cx))), transform=ax.transAxes, ha="right",
                va="bottom", color=ACCENT, alpha=0.30, fontsize=64, fontweight="bold")
        _progress_bar(ax, idx / max(1, n_frames - 1))

    _title_block(fig, topic, settings)
    anim = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    _save(anim, out_path, fps, dpi, settings)
    plt.close(fig)
    return len(frames) / fps


# --------------------------------------------------------------------------- #
# Head-to-head multi-line
# --------------------------------------------------------------------------- #
def _render_multi_line(wide: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any],
                       out_path: Path) -> float:
    """Two-or-more named series growing together — built for head-to-heads."""
    vconf = settings.get("video", {})
    width, height = vconf.get("width", 1080), vconf.get("height", 1920)
    fps = int(vconf.get("fps", 30))
    dpi = 100

    xs = [int(y) for y in wide.index]
    names = list(wide.columns)
    steps = max(1, int(round(fps * _seconds_per_year(topic, settings, len(xs)))))

    series = {n: [float(v) for v in wide[n].values] for n in names}
    ymax = max(max(v) for v in series.values())
    line_colors = {n: PALETTE[i * 5 % len(PALETTE)] for i, n in enumerate(names)}

    flag_imgs: dict[str, Any] = {}
    if topic.get("flags", True):
        from . import flags as flagmod

        flag_imgs = flagmod.preload(names)

    # One dense curve per series, all sharing the same x samples, so the frame
    # index walks every line in step and no line has a corner at a year mark.
    paths = {n: _smooth_path(xs, series[n], steps) for n in names}
    curve_x = paths[names[0]][0]
    curves = {n: p[1] for n, p in paths.items()}
    n_pts = len(curve_x)
    frames: list[int] = list(range(n_pts)) + [n_pts - 1] * fps  # + 1s end hold

    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_BOTTOM)
    fig.subplots_adjust(left=0.16, right=0.80, top=0.82, bottom=0.11)
    _add_gradient_bg(fig)
    n_frames = len(frames)

    def draw(idx: int) -> None:
        k = frames[idx]
        cx = float(curve_x[k])
        cvals = {n: float(curves[n][k]) for n in names}
        ax.clear()
        ax.set_facecolor("none")

        for n in names:
            col = line_colors[n]
            line_x = curve_x[: k + 1]
            line_y = curves[n][: k + 1]
            ax.fill_between(line_x, line_y, color=col, alpha=0.10)
            ax.plot(line_x, line_y, color=col, linewidth=5,
                    solid_capstyle="round", zorder=4)
            ax.scatter([cx], [cvals[n]], color=FG, s=80, zorder=5,
                       edgecolors=col, linewidths=2.5)

        # Labels: when the lines converge (the whole point of a head-to-head)
        # the labels would sit on top of each other, so push them apart.
        gap = ymax * 0.075
        ordered = sorted(names, key=lambda n: cvals[n], reverse=True)
        label_y: dict[str, float] = {}
        for rank, n in enumerate(ordered):
            y = cvals[n]
            if rank > 0:
                y = min(y, label_y[ordered[rank - 1]] - gap)
            label_y[n] = y

        for n in ordered:
            col = line_colors[n]
            ax.text(cx, label_y[n], f"{n}  {_fmt(cvals[n], topic)}",
                    color=col, fontsize=17, fontweight="bold",
                    va="center", ha="left", zorder=7,
                    transform=ax.transData, clip_on=False)
            img = flag_imgs.get(n)
            if img is not None:
                ab = AnnotationBbox(
                    OffsetImage(img, zoom=0.34), (cx, label_y[n]),
                    xybox=(-6, 0), xycoords="data", boxcoords="offset points",
                    frameon=False, box_alignment=(1.0, 0.5),
                    annotation_clip=False, zorder=7,
                )
                ax.add_artist(ab)

        ax.set_xlim(xs[0], xs[-1])
        ax.set_ylim(0, ymax * 1.15)
        ax.grid(True, color=GRID, alpha=0.35)
        ax.tick_params(colors=MUTED, labelsize=13)
        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.text(0.98, 0.05, str(int(round(cx))), transform=ax.transAxes, ha="right",
                va="bottom", color=ACCENT, alpha=0.30, fontsize=64, fontweight="bold")
        _progress_bar(ax, idx / max(1, n_frames - 1))

    _title_block(fig, topic, settings)
    anim = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    _save(anim, out_path, fps, dpi, settings)
    plt.close(fig)
    return len(frames) / fps


# --------------------------------------------------------------------------- #
# Motion helpers
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Bump race — ranks over time, so the OVERTAKES are the story
# --------------------------------------------------------------------------- #
def _render_bump_race(wide: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any],
                      out_path: Path) -> Path:
    """Lines through rank positions; crossings read as overtakes.

    A bar race hides mid-table movement — only the order changes and the bars
    look alike. Plotting rank directly turns every swap into a visible X.
    """
    vconf = settings.get("video", {})
    width, height = vconf.get("width", 1080), vconf.get("height", 1920)
    fps = int(vconf.get("fps", 30))
    dpi = 100

    years = [int(y) for y in wide.index]
    top_n = min(int(topic.get("top_n", vconf.get("top_n", 10))), len(wide.columns))
    # The final year decides who is shown, so the closing frame answers the
    # question the title asked.
    wide = wide[list(wide.iloc[-1].sort_values(ascending=False).index[:top_n])]
    entities = list(wide.columns)
    colors = _color_map(entities)

    ranks = wide.rank(axis=1, ascending=False, method="first")  # rank 1 = best
    steps = max(1, int(round(fps * _seconds_per_year(topic, settings, len(years)))))
    curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for e in entities:
        cx, cy = _smooth_path(years, [float(r) for r in ranks[e].values], steps, False)
        curves[e] = (np.asarray(cx), np.asarray(cy))
    n_pts = len(next(iter(curves.values()))[0])
    frames = list(range(1, n_pts + 1)) + [n_pts] * fps  # + 1s end hold

    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_BOTTOM)
    fig.subplots_adjust(left=0.16, right=0.72, top=0.85, bottom=0.10)
    _add_gradient_bg(fig)

    flag_imgs: dict[str, Any] = {}
    if topic.get("flags", True):
        from . import flags as flagmod

        flag_imgs = flagmod.preload(entities)

    def draw(idx: int) -> None:
        n = frames[idx]
        ax.clear()
        ax.set_facecolor("none")
        ax.set_xlim(years[0], years[-1])
        ax.set_ylim(top_n + 0.6, 0.4)  # rank 1 at the top
        ax.set_yticks(range(1, top_n + 1))
        ax.set_yticklabels([f"#{r}" for r in range(1, top_n + 1)], color=MUTED, fontsize=18)
        ax.tick_params(axis="x", colors=MUTED, labelsize=16)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color=GRID, linewidth=1, alpha=0.45)

        for e in entities:
            cx, cy = curves[e]
            ax.plot(cx[:n], cy[:n], color=colors[e], linewidth=5,
                    solid_capstyle="round", alpha=0.95, zorder=3)
            x, y = float(cx[n - 1]), float(cy[n - 1])
            ax.scatter([x], [y], s=200, color=colors[e], zorder=5,
                       edgecolors=BG_BOTTOM, linewidths=2)
            img = flag_imgs.get(e)
            if img is not None:
                ax.add_artist(AnnotationBbox(
                    OffsetImage(img, zoom=0.40), (x, y), frameon=False,
                    box_alignment=(0.5, 0.5), zorder=6, clip_on=False))
            ax.annotate(f"  {e}", (x, y), color=colors[e], fontsize=20,
                        fontweight="bold", va="center", ha="left",
                        annotation_clip=False, zorder=6)

        yr = int(round(float(curves[entities[0]][0][n - 1])))
        ax.text(0.99, 1.03, str(yr), transform=ax.transAxes, ha="right", va="bottom",
                color=FG, fontsize=44, fontweight="bold", alpha=0.9)
        _progress_bar(ax, n / n_pts)

    anim = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    _title_block(fig, topic, settings)
    _save(anim, out_path, fps, dpi, settings)
    plt.close(fig)
    return len(frames) / fps


# --------------------------------------------------------------------------- #
# Waffle grow — "X out of 100", which lands emotionally where an axis does not
# --------------------------------------------------------------------------- #
def _render_waffle(series_df: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any],
                   out_path: Path) -> Path:
    """A 10x10 dot grid filling as a bounded percentage moves over time."""
    vconf = settings.get("video", {})
    width, height = vconf.get("width", 1080), vconf.get("height", 1920)
    fps = int(vconf.get("fps", 30))
    dpi = 100

    years = [int(y) for y in series_df.index]
    vals = [float(v) for v in series_df["value"].values]
    steps = max(1, int(round(fps * _seconds_per_year(topic, settings, len(years)))))
    curve_x, curve_y = _smooth_path(years, vals, steps, False)
    n_pts = len(curve_x)
    frames = list(range(n_pts)) + [n_pts - 1] * fps

    rows = cols = 10
    cell = 1.0 / cols
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_BOTTOM)
    fig.subplots_adjust(left=0.10, right=0.90, top=0.74, bottom=0.20)
    _add_gradient_bg(fig)
    ax.set_aspect("equal")

    def draw(idx: int) -> None:
        i = frames[idx]
        pct = max(0.0, min(100.0, float(curve_y[i])))
        filled = pct / 100.0 * (rows * cols)
        ax.clear()
        ax.set_facecolor("none")
        ax.set_xlim(-0.04, 1.04)
        ax.set_ylim(-0.04, 1.04)
        ax.axis("off")

        for r in range(rows):
            for c in range(cols):
                n = r * cols + c  # fill bottom-up, left-to-right
                frac = max(0.0, min(1.0, filled - n))
                face, alpha = ((GRID, 0.5) if frac <= 0
                               else (ACCENT, 0.35 + 0.65 * frac))
                ax.add_patch(plt.Circle((c * cell + cell / 2, r * cell + cell / 2),
                                        cell * 0.34, facecolor=face, edgecolor="none",
                                        alpha=alpha, zorder=3))

        ax.text(0.5, 1.22, _fmt(pct, topic), transform=ax.transAxes, ha="center",
                va="center", color=ACCENT, fontsize=76, fontweight="bold")
        ax.text(0.5, 1.11, "out of every 100", transform=ax.transAxes, ha="center",
                va="center", color=MUTED, fontsize=22)
        ax.text(0.5, -0.12, str(int(round(float(curve_x[i])))), transform=ax.transAxes,
                ha="center", va="center", color=FG, fontsize=46, fontweight="bold",
                alpha=0.9)
        _progress_bar(ax, (i + 1) / n_pts)

    anim = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    _title_block(fig, topic, settings)
    _save(anim, out_path, fps, dpi, settings)
    plt.close(fig)
    return len(frames) / fps


def _ease(f: float) -> float:
    """Smoothstep: zero velocity at both ends, so moves start and stop softly."""
    return f * f * (3.0 - 2.0 * f)


def _mono_tangents(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fritsch-Carlson tangents for monotone cubic interpolation.

    Plain cubic splines overshoot: they invent peaks and dips between the real
    data points, which on a data channel is a chart that lies. These tangents
    are clamped so the curve is smooth but never leaves the range implied by
    the neighbouring points.
    """
    n = len(x)
    if n < 3:
        slope = (y[-1] - y[0]) / (x[-1] - x[0]) if n == 2 and x[-1] != x[0] else 0.0
        return np.full(n, slope, dtype=float)

    h = np.diff(x).astype(float)
    delta = np.diff(y) / h
    m = np.empty(n, dtype=float)
    m[0], m[-1] = delta[0], delta[-1]
    for i in range(1, n - 1):
        # A sign change means a local extremum: flatten so the curve turns there
        # rather than swinging past the data point.
        m[i] = 0.0 if delta[i - 1] * delta[i] <= 0 else (delta[i - 1] + delta[i]) / 2.0

    for i in range(n - 1):
        if delta[i] == 0.0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / delta[i], m[i + 1] / delta[i]
        norm = a * a + b * b
        if norm > 9.0:
            t = 3.0 / np.sqrt(norm)
            m[i], m[i + 1] = t * a * delta[i], t * b * delta[i]
    return m


def _smooth_path(xs: list[int], ys: list[float], steps: int,
                 log_scale: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Resample a yearly series into a dense, corner-free curve.

    Returns ``steps`` samples per year plus the final point, so a frame index
    walks the curve directly and the drawn trail always matches the moving head.
    """
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    # Exponential series (AI compute, costs) curve naturally in log space; doing
    # it linearly would flatten the early years into a straight floor.
    fit = np.log10(np.clip(y, 1e-12, None)) if log_scale else y

    m = _mono_tangents(x, fit)
    dense_x: list[float] = []
    dense_f: list[float] = []
    for i in range(len(x) - 1):
        h = x[i + 1] - x[i]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            dense_x.append(x[i] + h * t)
            dense_f.append(
                (2 * t3 - 3 * t2 + 1) * fit[i]
                + (t3 - 2 * t2 + t) * h * m[i]
                + (-2 * t3 + 3 * t2) * fit[i + 1]
                + (t3 - t2) * h * m[i + 1]
            )
    dense_x.append(float(x[-1]))
    dense_f.append(float(fit[-1]))

    out = np.asarray(dense_f)
    return np.asarray(dense_x), (np.power(10.0, out) if log_scale else out)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _add_gradient_bg(fig) -> None:
    """Full-figure vertical gradient behind everything (drawn once)."""
    bgax = fig.add_axes([0, 0, 1, 1], zorder=-10)
    bgax.axis("off")
    cmap = LinearSegmentedColormap.from_list("bg", [BG_BOTTOM, BG_TOP])
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    bgax.imshow(grad, aspect="auto", cmap=cmap, extent=[0, 1, 0, 1], origin="lower")


def _progress_bar(ax, frac: float) -> None:
    """Slim time-progress bar just below the plot area."""
    y, x0, w, h = -0.055, 0.0, 1.0, 0.012
    ax.add_patch(Rectangle((x0, y), w, h, transform=ax.transAxes,
                           facecolor=GRID, edgecolor="none", clip_on=False, zorder=5))
    ax.add_patch(Rectangle((x0, y), w * max(0.0, min(1.0, frac)), h, transform=ax.transAxes,
                           facecolor=ACCENT, edgecolor="none", clip_on=False, zorder=6))


def _title_block(fig, topic: dict[str, Any], settings: dict[str, Any]) -> None:
    fig.text(0.5, 0.962, topic.get("title", ""), ha="center", va="top",
             color=FG, fontsize=33, fontweight="bold")
    # Accent underline under the title.
    fig.add_artist(plt.Line2D([0.38, 0.62], [0.918, 0.918], color=ACCENT, linewidth=3))
    if topic.get("subtitle"):
        fig.text(0.5, 0.905, topic["subtitle"], ha="center", va="top", color=MUTED, fontsize=18)
    credit = f"Source: {topic.get('source', 'unknown')}"
    fig.text(0.5, 0.028, credit, ha="center", va="bottom", color=MUTED, fontsize=13)
    footer = settings.get("branding", {}).get("footer")
    if footer:
        fig.text(0.5, 0.008, footer, ha="center", va="bottom", color=GRID, fontsize=10)


_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _fmt(val: float, topic: dict[str, Any]) -> str:
    scale = topic.get("value_scale")
    suffix = topic.get("unit_suffix", "")
    # Head-to-heads often need extra precision — 1.42B vs 1.41B, not "1.4B" twice.
    decimals = int(topic.get("value_decimals", 1))

    # Whole-number display for counts (e.g. "50" not "50.0").
    if topic.get("value_fmt") == "integer":
        return f"{val:,.0f}{suffix}"

    # Scientific notation for astronomically large values (e.g. FLOP).
    if topic.get("value_fmt") == "scientific" and val > 0:
        exponent = int(np.floor(np.log10(abs(val))))
        mantissa = val / (10 ** exponent)
        return f"{mantissa:.1f}×10{str(exponent).translate(_SUPERSCRIPT)}{suffix}"
    if scale:
        return f"{val / float(scale):,.{decimals}f}{suffix}"
    if abs(val) >= 1000:
        return f"{val:,.0f}{suffix}"
    return f"{val:,.{decimals}f}{suffix}"


def _seconds_per_year(topic: dict[str, Any], settings: dict[str, Any], n_years: int) -> float:
    """Pace the animation.

    Topics span very different windows (50 years of world data vs ~11 years of
    AI-cluster data), so a fixed seconds-per-year makes short-window topics only
    a few seconds long. If ``video.target_seconds`` is set, derive the pace so
    every video lands near that length; a per-topic ``seconds_per_year`` wins.
    """
    vconf = settings.get("video", {})
    explicit = topic.get("seconds_per_year")
    if explicit:
        return float(explicit)

    target = vconf.get("target_seconds")
    steps = max(1, n_years - 1)
    if target:
        return min(3.0, max(0.25, float(target) / steps))
    return float(vconf.get("seconds_per_year", 0.5))


def _color_map(entities: list[str]) -> dict[str, Any]:
    return {e: PALETTE[i % len(PALETTE)] for i, e in enumerate(sorted(entities))}


def ffmpeg_exe(settings: dict[str, Any]) -> str:
    """Resolve an ffmpeg executable: config path -> system PATH -> pip-bundled binary."""
    configured = settings.get("ffmpeg_path")
    if configured:
        return configured
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError(
        "ffmpeg not found. Either `pip install imageio-ffmpeg`, install system ffmpeg "
        "(`winget install Gyan.FFmpeg`), or set `ffmpeg_path` in config/settings.yaml."
    )


def _ensure_ffmpeg(settings: dict[str, Any]) -> None:
    plt.rcParams["animation.ffmpeg_path"] = ffmpeg_exe(settings)


def _save(anim, out_path: Path, fps: int, dpi: int, settings: dict[str, Any]) -> None:
    writer = animation.FFMpegWriter(fps=fps, bitrate=6000, codec="libx264",
                                    extra_args=["-pix_fmt", "yuv420p"])
    anim.save(str(out_path), writer=writer, dpi=dpi)
