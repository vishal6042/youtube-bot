"""A designed thumbnail for a long-form video, from a `thumbnail:` block in its script.

The generic thumbnail grabs a frame from the video, which may be any chapter's
chart and rarely the one that tells the story. A video that says what its
thumbnail is about gets this instead, 1280x720:

    thumbnail:
      kicker: HOW CHINA BECAME          # small line above the headline
      headline: [THE WORLD'S, FACTORY]  # the last line is set huge, in `accent`
      accent: "#ffcc33"
      stat: 27th → 1st                  # the badge
      stat_label: biggest exporter of goods, 1980 → 2009
      chart:                            # the one picture that tells the story
        code: NV.IND.MANF.CD
        entities: [China, United States]
        labels: {China: CHINA, United States: USA}
        hero: China
        year_min: 2004
        year_max: 2021
        mark: {year: 2010, text: "2010"}

The chart is the real data, drawn bold and without axes: at browse size only
the shape and the crossing read, so that is all it shows.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
INK = (11, 14, 22)
HERO = "#ff4d4d"
OTHER = "#5b7cfa"
_BLACK = ["seguibl.ttf", "ariblk.ttf", "impact.ttf", "DejaVuSans-Bold.ttf"]
_BOLD = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    import matplotlib

    for root in (Path("C:/Windows/Fonts"), Path(matplotlib.get_data_path()) / "fonts" / "ttf"):
        for n in names:
            if (root / n).exists():
                return ImageFont.truetype(str(root / n), size)
    return ImageFont.load_default()


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _background(glow_rgb: tuple[int, int, int] = (120, 26, 30),
                glow2_rgb: tuple[int, int, int] | None = None) -> Image.Image:
    """Deep navy, darker at the edges, with a warm glow behind the chart.

    ``glow2_rgb`` adds a second, smaller glow low on the left (a two-colour
    look, e.g. saffron and green for India).
    """
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base[...] = (14, 20, 38)
    vignette = 1 - 0.55 * (((x - W * 0.45) / W) ** 2 + ((y - H * 0.5) / H) ** 2)
    base *= np.clip(vignette, 0.35, 1)[..., None]
    glow = np.exp(-(((x - W * 0.78) / (W * 0.32)) ** 2 + ((y - H * 0.42) / (H * 0.55)) ** 2))
    base += glow[..., None] * np.array(glow_rgb, np.float32)
    if glow2_rgb:
        g2 = np.exp(-(((x - W * 0.12) / (W * 0.28)) ** 2 + ((y - H * 1.0) / (H * 0.45)) ** 2))
        base += g2[..., None] * np.array(glow2_rgb, np.float32)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


# Medal colours for a leaderboard: (card fill, rank text) per tone.
_TONES = {
    "gold": ("#ffcf3f", "#2a1d00"),
    "silver": ("#dfe6f0", "#1b2230"),
    "bronze": ("#e59a5b", "#2b1607"),
    "red": ("#ff4d4d", "#ffffff"),
}


def _leaderboard(canvas: Image.Image, rows: list[dict[str, Any]], box: tuple[int, int, int, int]) -> None:
    """A stack of rank cards: a coloured rank tile, then the label.

    A row with ``gap: true`` is drawn as a dotted break, the visual "..."
    between the top of the list and a rank far below it.
    """
    x0, y0, x1, y1 = box
    gap_h = 34
    n_cards = sum(1 for r in rows if not r.get("gap"))
    n_gaps = len(rows) - n_cards
    spacing = 16
    card_h = int((y1 - y0 - n_gaps * gap_h - spacing * (n_cards - 1)) / max(1, n_cards))
    rank_f = _font(_BLACK, int(card_h * 0.56))
    probe = ImageDraw.Draw(canvas)

    def tile_width(r: dict[str, Any]) -> int:
        return int(card_h * 1.55) if len(str(r["rank"])) > 2 else int(card_h * 1.2)

    def label_font(r: dict[str, Any]):
        return _fit(probe, r["label"], _BLACK, int(card_h * 0.42), x1 - x0 - tile_width(r) - 40)

    # The medal rows share one label size (the largest that fits all of them),
    # so they read as one list; the red outlier is sized on its own.
    top_rows = [r for r in rows if not r.get("gap") and r.get("tone") != "red"]
    shared = _font(_BLACK, min(label_font(r).size for r in top_rows)) if top_rows else None
    y = y0
    for r in rows:
        if r.get("gap"):
            draw = ImageDraw.Draw(canvas)
            cx = x0 + int(card_h * 0.6)
            for i in range(3):
                cy = y + 4 + i * 13
                draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(200, 208, 224, 255))
            y += gap_h
            continue
        fill, ink = _TONES.get(r.get("tone", ""), ("#2b3550", "#ffffff"))
        # Soft shadow under the whole card.
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([x0 + 4, y + 8, x1 + 4, y + card_h + 8], radius=22,
                                             fill=(0, 0, 0, 150))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
        card = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle([x0, y, x1, y + card_h], radius=22, fill=(18, 24, 44, 235),
                             outline=(*_rgb(fill), 150), width=3)
        canvas.alpha_composite(card)
        draw = ImageDraw.Draw(canvas)
        tile_w = tile_width(r)
        draw.rounded_rectangle([x0, y, x0 + tile_w, y + card_h], radius=22, fill=fill,
                               corners=(True, False, False, True))
        draw.text((x0 + tile_w / 2, y + card_h / 2 + 2), str(r["rank"]), font=rank_f, fill=ink,
                  anchor="mm")
        label_f = shared if (shared and r.get("tone") != "red") else label_font(r)
        draw.text((x0 + tile_w + 26, y + card_h / 2 + 2), r["label"], font=label_f,
                  fill=_rgb(fill) if r.get("tone") == "red" else (245, 247, 252), anchor="lm")
        y += card_h + spacing


def _chart(spec: dict[str, Any], settings: dict[str, Any], size: tuple[int, int]) -> Image.Image:
    """The story's lines, bold, on a transparent background."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .build import _indicator

    df = _indicator(spec["code"], settings)
    lo, hi = int(spec["year_min"]), int(spec["year_max"])
    df = df[(df["year"] >= lo) & (df["year"] <= hi)]
    names = spec["entities"]
    hero = spec.get("hero", names[0])
    labels = spec.get("labels", {})
    wide = df.pivot_table(index="year", columns="entity", values="value")[names].dropna()

    dpi = 100
    fig = plt.figure(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0.07, 0.10, 0.66, 0.80])
    from matplotlib.font_manager import FontProperties

    heavy = next((FontProperties(fname=str(p)) for p in (Path("C:/Windows/Fonts") / n for n in _BLACK)
                  if p.exists()), FontProperties(weight="bold"))
    ax.set_facecolor("none")
    ymax = float(wide.max().max()) * 1.08
    for n in names:
        xs, ys = wide.index.values, wide[n].values
        col = HERO if n == hero else OTHER
        if n == hero:
            for lw, a in ((34, 0.06), (22, 0.12), (14, 0.25)):   # glow under the hero line
                ax.plot(xs, ys, color=col, lw=lw, alpha=a, solid_capstyle="round")
        ax.plot(xs, ys, color=col, lw=11 if n == hero else 7, solid_capstyle="round", zorder=3)
        ax.scatter([xs[-1]], [ys[-1]], s=420 if n == hero else 260, color="white", zorder=4,
                   edgecolors=col, linewidths=5)
        ax.text(xs[-1] + (hi - lo) * 0.045, ys[-1], labels.get(n, n.upper()), color=col, va="center",
                fontproperties=heavy, fontsize=34 if n == hero else 28, zorder=5, clip_on=False)
    mark = spec.get("mark")
    if mark:
        ax.axvline(mark["year"], color="white", alpha=0.55, lw=3, ls=(0, (4, 4)), zorder=2)
        ax.text(mark["year"], ymax * 0.98, f"  {mark['text']}", color="white", fontsize=26,
                fontproperties=heavy, va="top", ha="left", alpha=0.9)
    for yr in (lo, hi):
        ax.text(yr, -ymax * 0.06, str(yr), color="#9aa4b8", fontsize=20, ha="center", va="top",
                fontproperties=heavy, clip_on=False)
    ax.set_xlim(lo - (hi - lo) * 0.02, hi + (hi - lo) * 0.02)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _shadowed_text(canvas: Image.Image, xy: tuple[int, int], text: str, font, fill, stroke: int = 0) -> None:
    """Text with a soft drop shadow, so it holds up over the glow at any size."""
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((xy[0] + 5, xy[1] + 7), text, font=font, fill=(0, 0, 0, 200),
                                stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(canvas).text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=INK)


def _fit(draw: ImageDraw.ImageDraw, text: str, names: list[str], start: int, max_w: int):
    size = start
    while size > 20:
        f = _font(names, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return _font(names, size)


def build_hero(ep: dict[str, Any], out_path: Path, settings: dict[str, Any]) -> Path:
    spec = ep["thumbnail"]
    if spec.get("style") == "neon":   # the look of the animated intro/outro (thumb_neon.py)
        from .thumb_neon import build_neon

        return build_neon(ep, out_path, settings)
    glow = _rgb(spec["glow"]) if spec.get("glow") else (120, 26, 30)
    glow2 = _rgb(spec["glow2"]) if spec.get("glow2") else None
    canvas = _background(glow, glow2).convert("RGBA")
    if spec.get("chart"):
        chart = _chart(spec["chart"], settings, (760, 560))
        canvas.alpha_composite(chart, (W - 760, 118))
    if spec.get("ranks"):
        _leaderboard(canvas, spec["ranks"], (W - 560, 48, W - 44, H - 76))
    draw = ImageDraw.Draw(canvas)
    left = 56
    col_w = 560 if spec.get("ranks") else 640
    accent = spec.get("accent", "#ffcc33")

    y = int(spec.get("top", 70))
    if spec.get("kicker"):
        f = _fit(draw, spec["kicker"], _BLACK, 54 if not spec.get("ranks") else 64, col_w)
        _shadowed_text(canvas, (left, y), spec["kicker"], f, "white")
        y += int(f.size * 1.15)
    lines = spec.get("headline") or [ep.get("title", "")]
    # By default only the last line is huge and in the accent colour; a script
    # can make several lines huge (`big_lines`) and choose which get the accent.
    big = set(spec.get("big_lines", [len(lines) - 1]))
    accented = set(spec.get("accent_lines", [len(lines) - 1]))
    for i, line in enumerate(lines):
        huge = i in big
        f = _fit(draw, line, _BLACK, 170 if huge else 76, col_w + (90 if huge else 0))
        _shadowed_text(canvas, (left - (6 if huge else 0), y), line, f,
                       accent if i in accented else "white", stroke=5 if huge else 0)
        y += int(f.size * (1.02 if huge else 1.12))

    if spec.get("stripe"):
        # A short bar of colours under the headline (e.g. the tricolour).
        sx, sw = left, 70
        for col in spec["stripe"]:
            draw.rounded_rectangle([sx, y + 34, sx + sw, y + 46], radius=6, fill=col)
            sx += sw + 8
        y += 58
    if spec.get("footnote"):
        ff = _font(_BOLD, 30)
        draw.text((left + 2, y + 8), spec["footnote"], font=ff, fill=(214, 220, 234))

    if spec.get("stat"):
        sf = _font(_BLACK, 60)
        lf = _font(_BOLD, 26)
        tw = draw.textlength(spec["stat"], font=sf)
        top = H - 170
        draw.rounded_rectangle([left, top, left + tw + 56, top + 92], radius=24, fill=HERO)
        draw.text((left + 28, top + 46), spec["stat"], font=sf, fill="white", anchor="lm")
        if spec.get("stat_label"):
            draw.text((left + 4, top + 108), spec["stat_label"], font=lf, fill=(220, 226, 238))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)
    return out_path
