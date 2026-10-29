"""A thumbnail in the neon look (the episode's `thumbnail:` block with `style: neon`).

1280x720: the headline in big metallic letters over a globe with India lit
up, and a column of glass rank cards on the right. Uses the same kit (fx.py)
as the animated intro and outro, so the thumbnail matches the video.

    thumbnail:
      style: neon
      kicker: WHERE DOES
      headline: [INDIA, RANK?]          # first line saffron metal, second silver
      ranks:
      - {rank: '#1', label: POPULATION, tone: gold}
      - {gap: true}
      - {rank: '#144', label: INCOME PER PERSON, tone: red}
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cairo
from PIL import Image, ImageDraw, ImageFilter

from . import fx

TW, TH = 1280, 720


def _card(w: int, h: int, tone: str) -> Image.Image:
    rgb = fx.TONE_RGB[tone]
    S = 2
    pad = 22
    surf, ctx = fx.canvas_surface((w + pad * 2) * S, (h + pad * 2) * S)
    ctx.scale(S, S)
    x0, y0, x1, y1, r = pad, pad, pad + w, pad + h, h / 2.6
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.arc(x1 - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    ctx.arc(x1 - r, y1 - r, r, 0, 0.5 * math.pi)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()
    g = cairo.LinearGradient(0, y0, 0, y1)
    g.add_color_stop_rgba(0, 0.10, 0.13, 0.26, 0.94)
    g.add_color_stop_rgba(1, 0.03, 0.05, 0.12, 0.94)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 1)
    ctx.set_line_width(3.5)
    ctx.stroke()
    # A sheen across the top.
    ctx.save()
    ctx.rectangle(x0, y0, w, h * 0.45)
    ctx.clip()
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.arc(x1 - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    ctx.arc(x1 - r, y1 - r, r, 0, 0.5 * math.pi)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()
    ctx.set_source_rgba(1, 1, 1, 0.06)
    ctx.fill()
    ctx.restore()
    img = fx.surface_to_image(surf).resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
    return fx.glow(img, 14, 0.85, tint=rgb)


def build_neon(ep: dict[str, Any], out_path: Path, settings: dict[str, Any]) -> Path:
    spec = ep["thumbnail"]
    bg = fx.backdrop(seed=5, map_alpha=0.16).resize((TW, TH), Image.LANCZOS)
    canvas = bg.convert("RGBA")

    # Globe, low on the left, with India lit up and glowing hard.
    gl = fx.globe(400, 80.0, 6.0)
    gx, gy = 300, 640
    fx.paste(canvas, gl["base"], gx, gy)
    for a in (1.0, 0.8):
        fx.paste(canvas, gl["india"], gx, gy, a)
    fx.paste(canvas, fx.flare(130), gx + 255, gy - 330, 0.95)
    ix = gx - gl["size"] / 2 + gl["india_xy"][0]
    iy = gy - gl["size"] / 2 + gl["india_xy"][1]
    # Arcs flying out from India towards the rank cards.
    surf, ctx = fx.canvas_surface(TW, TH)
    for k, (tx, ty) in enumerate([(700, 80), (760, 250), (700, 420), (880, 640)]):
        pts = fx.arc_path((ix, iy), (tx, ty), lift=60 + 30 * k)
        fx.draw_arc(ctx, pts, 1.0, alpha=0.55, pulse=0.7)
    canvas.alpha_composite(fx.surface_to_image(surf))

    # Headline: kicker, then INDIA (saffron metal), then RANK? (silver metal).
    left = 46
    kick = fx.text(spec.get("kicker", ""), 66, fx.FG, "black", glow_r=8, glow_a=0.35)
    fx.paste(canvas, kick, left - 18, 78, anchor="lm")
    lines = spec.get("headline") or []
    tones = ["saffron_bright", "silver"]
    sizes = [196, 150]
    ys = [215, 362]
    for i, line in enumerate(lines[:2]):
        size = sizes[i]
        while size > 60 and fx.font(size, "black").getlength(line) > 600:
            size -= 4
        spr = fx.metal_text(line, size, tones[i], glow_r=size / 7)
        fx.paste(canvas, spr, left - size * 0.35 + 6, ys[i], anchor="lm")

    # Rank cards down the right side.
    rows = spec.get("ranks") or []
    x0, x1 = 700, 1238
    y0, y1 = 34, TH - 40
    n_cards = sum(1 for r in rows if not r.get("gap"))
    gaps = len(rows) - n_cards
    gap_h, spacing = 30, 18
    ch = int((y1 - y0 - gaps * gap_h - spacing * (n_cards - 1)) / max(1, n_cards))
    y = y0
    for r in rows:
        if r.get("gap"):
            d = ImageDraw.Draw(canvas)
            for k in range(3):
                cy = y + 5 + k * 10
                d.ellipse([x0 + 62 - 4, cy - 4, x0 + 62 + 4, cy + 4], fill=(210, 218, 232, 255))
            y += gap_h
            continue
        tone = r.get("tone", "teal")
        card = _card(x1 - x0, ch, tone)
        fx.paste(canvas, card, (x0 + x1) / 2, y + ch / 2)
        rank = str(r.get("rank", ""))
        rsize = int(ch * (0.72 if len(rank) <= 2 else 0.56))
        num = fx.metal_text(rank, rsize, tone, glow_r=rsize / 9)
        num_w = fx.font(rsize, "black").getlength(rank)
        fx.paste(canvas, num, x0 + 24 + num_w / 2, y + ch / 2 + 2)
        label = str(r.get("label", ""))
        lx = x0 + 24 + max(num_w, ch * 1.05) + 22
        lsize = int(ch * 0.36)
        while lsize > 20 and fx.font(lsize, "black").getlength(label) > x1 - lx - 22:
            lsize -= 1
        col = (255, 120, 120) if tone == "red" else fx.FG
        fx.paste(canvas, fx.text(label, lsize, col, "black"), lx - lsize / 3, y + ch / 2, anchor="lm")
        y += ch + spacing

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=93)
    return out_path
