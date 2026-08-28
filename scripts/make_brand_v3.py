"""Generate v3 channel brand assets (avatar + banner) into assets/brand/.

v3 rationale: the channel outgrew the v2 banner copy — three series became
six visible pillars (+ How Charts Lie). The mark keeps the bars+trendline
identity (recognition anchor) with a polish pass: 6 bars = 6 series.

    .venv/Scripts/python.exe scripts/make_brand_v3.py

Outputs: channel_avatar_v3.png (800x800), channel_banner_v3.png (2560x1440).
v1/v2 files are left untouched. YouTube banner safe area is the centered
1546x423 band — all must-see content is placed inside it.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BRAND = Path(__file__).resolve().parents[1] / "assets" / "brand"

NAVY_TOP = (16, 20, 42)
NAVY_BOT = (10, 13, 30)
TEAL = (64, 224, 200)
WHITE = (245, 248, 255)
GREY = (168, 178, 205)
# One color per series: world, ai, ml, money, india, sports
PALETTE = ["#5EE6A9", "#45CFF2", "#6E7BF2", "#B65CE8", "#E8447F", "#FF8A4C"]


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    names = {"black": ["seguibl.ttf", "arialbd.ttf"],
             "bold": ["segoeuib.ttf", "arialbd.ttf"],
             "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
             "regular": ["segoeui.ttf", "arial.ttf"]}[weight]
    for n in names:
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{n}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(w: int, h: int, top=NAVY_TOP, bot=NAVY_BOT) -> Image.Image:
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        img.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
    return img.resize((w, h))


def draw_tracked(draw: ImageDraw.ImageDraw, xy, text, fnt, fill, tracking=0, anchor_center_x=None):
    """Draw text with letter-spacing; optionally centered on anchor_center_x."""
    widths = [draw.textlength(c, font=fnt) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (anchor_center_x - total / 2) if anchor_center_x is not None else xy[0]
    y = xy[1]
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=fnt, fill=fill)
        x += w + tracking
    return total


def chart_mark(size: int, ascending: bool = True, dots: bool = True) -> Image.Image:
    """The brand mark: 6 rounded bars + trendline with dots, on transparency."""
    s = size / 800  # designed at 800
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(PALETTE)
    bw, gap = 74 * s, 26 * s
    total = n * bw + (n - 1) * gap
    x0 = (size - total) / 2
    base = 660 * s
    heights = [120, 200, 290, 380, 470, 560]
    if not ascending:
        heights = heights[::-1]
    tops = []
    for i, (c, h) in enumerate(zip(PALETTE, heights)):
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, base - h * s, x + bw, base], radius=bw / 2.6, fill=c)
        tops.append((x + bw / 2, base - h * s - 46 * s))
    # soft glow under the trendline, then the line + dots
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).line(tops, fill=TEAL + (160,), width=round(16 * s))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * s)))
    d.line(tops, fill=WHITE, width=round(7 * s))
    if dots:
        r = 15 * s
        for (cx, cy) in tops:
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE,
                      outline=TEAL, width=round(4.5 * s))
    return img


def make_avatar() -> Path:
    S = 800
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    disc = gradient(S, S).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([6, 6, S - 6, S - 6], fill=255)
    img.paste(disc, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, S - 6, S - 6], outline=(8, 10, 24), width=6)
    d.ellipse([16, 16, S - 16, S - 16], outline=TEAL, width=10)
    mark = chart_mark(700)
    img.alpha_composite(mark, ((S - 700) // 2, 60))
    out = BRAND / "channel_avatar_v3.png"
    img.save(out)
    return out


def make_banner() -> Path:
    W, H = 2560, 1440
    img = gradient(W, H).convert("RGBA")
    d = ImageDraw.Draw(img)

    # Ambient muted bars along top and bottom edges (outside every safe area)
    rng = random.Random(7)
    for y_edge, up in [(0, False), (H, True)]:
        x = 20
        while x < W - 40:
            bw = rng.randint(38, 66)
            bh = rng.randint(90, 230)
            col = tuple(rng.choice([(52, 60, 96), (60, 48, 92), (44, 66, 96),
                                    (72, 48, 84), (46, 58, 104)]))
            y0, y1 = (H - bh, H) if up else (0, bh)
            d.rounded_rectangle([x, y0, x + bw, y1], radius=bw / 3,
                                fill=col + (rng.randint(60, 110),))
            x += bw + rng.randint(14, 30)

    cx = W // 2
    band_top = (H - 423) // 2  # 508 — desktop/mobile visible band

    # Pillars line (inside safe band)
    draw_tracked(d, (0, band_top + 48), "WORLD DATA · AI · MONEY · INDIA · SPORTS · ML",
                 font(46, "bold"), TEAL, tracking=6, anchor_center_x=cx)
    # Title
    draw_tracked(d, (0, band_top + 108), "DATA IN MOTION",
                 font(158, "black"), WHITE, tracking=10, anchor_center_x=cx)
    # Teal underline
    d.rounded_rectangle([cx - 190, band_top + 322, cx + 190, band_top + 334],
                        radius=6, fill=TEAL)
    # Tagline
    draw_tracked(d, (0, band_top + 348), "Big ideas, animated in seconds  ·  New video daily",
                 font(52, "regular"), GREY, tracking=1, anchor_center_x=cx)

    # Side marks: rising chart left, falling right (desktop-only flourish)
    left = chart_mark(430, ascending=True)
    right = chart_mark(430, ascending=False)
    img.alpha_composite(left, (95, band_top - 15))
    img.alpha_composite(right, (W - 430 - 95, band_top - 15))

    out = BRAND / "channel_banner_v3.png"
    img.convert("RGB").save(out)
    return out


if __name__ == "__main__":
    for p in (make_avatar(), make_banner()):
        print(p)
