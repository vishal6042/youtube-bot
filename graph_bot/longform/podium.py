"""The podium recap: a long-form outro that shows what the narrator is listing.

Three pedestals rise one by one (gold, silver, bronze) with metallic numbers,
growing laurels and neon icons, beside a globe with India lit up; then a
"top five" bar and a red "still low" bar; then the closing line, word by word.
Every reveal is timed to a spoken word. In the script:

    chart:
      mode: podium
      globe: {lon0: 80, lat0: 16}
      arcs: {at: money}                         # money flying home to India
      podium:
      - {rank: 1, tone: gold, at: first, icons: [users, coins], label: Population, sub: Money sent home}
      - {rank: 2, tone: silver, at: second, icons: [smartphone, cloud], label: Mobile phones, sub: IT services}
      - {rank: 3, tone: bronze, at: third, icons: [book-open, flask-conical], label: Science papers, sub: Buying power}
      bars:
      - {at: top, tone: teal, icon: trophy, title: TOP 5,
         items: [{icon: plane, rank: '#4', label: Flying}, {icon: lightbulb, rank: '#5', label: Inventions}]}
      - {at: still, tone: red, icon: trending-down, title: STILL LOW,
         items: [{icon: heart-pulse, rank: '#137', label: Life expectancy}, {icon: coins, rank: '#144', label: Income per person}]}
      finale: {at: india, lines: [...], accent: [...], question: {...}, subscribe: {}, share: {}}
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cairo
import numpy as np
from PIL import Image, ImageDraw

from . import fx
from .fx import H, W, FPS, ease_back, ease_out, paste

VERSION = 2   # 2: labels below the plinth ring, gap above the Top 5 bar

# Where things sit (1920x1080).
GLOBE_XY, GLOBE_R = (300, 470), 470
PED_X = [790, 1232, 1672]
PED_TOP = [336, 366, 398]
PED_BOTTOM = 642
BAND_ABOVE_BOTTOM = 122   # the plinth's front ring sits this far above its base
PED_W = 404
BARS_Y = [782, 938]
BAR_H = [130, 140]


def _mix(a, b, f):
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def _pedestal(tone: str, top: int) -> Image.Image:
    """A glossy cylinder plinth; returns the sprite and its top offset."""
    rgb = fx.TONE_RGB[tone]
    w = PED_W
    eh = 56                     # height of the top ellipse
    h = PED_BOTTOM - top
    pad = 40
    S = 2
    sw, shh = (w + pad * 2) * S, (h + eh + pad * 2 + 30) * S
    surf, ctx = fx.canvas_surface(sw, shh)
    ctx.scale(S, S)
    cx, y0 = pad + w / 2, pad + eh / 2
    y1 = y0 + h
    rx, ry = w / 2, eh / 2

    def half_ellipse(y: float, rxx: float, lower: bool = True, reverse: bool = False) -> None:
        ctx.save()
        ctx.translate(cx, y)
        ctx.scale(rxx, ry)
        if reverse:
            ctx.arc_negative(0, 0, 1, math.pi, 0) if not lower else ctx.arc(0, 0, 1, 0, math.pi)
        else:
            ctx.arc(0, 0, 1, 0, math.pi) if lower else ctx.arc_negative(0, 0, 1, 0, math.pi)
        ctx.restore()

    # Base plate, wider than the plinth.
    ctx.save()
    ctx.translate(cx, y1 + 10)
    ctx.scale(rx * 1.16, ry * 0.9)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    g = cairo.LinearGradient(0, y1 - 10, 0, y1 + 40)
    g.add_color_stop_rgb(0, *(v / 255 for v in _mix(rgb, (10, 12, 22), 0.55)))
    g.add_color_stop_rgb(1, 0.02, 0.03, 0.07)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 0.55)
    ctx.set_line_width(2)
    ctx.stroke()

    # Front face: a slightly flared cylinder, shaded across like a curved surface.
    rb = rx * 1.035
    ctx.new_path()
    ctx.move_to(cx - rx, y0)
    ctx.line_to(cx - rb, y1)
    ctx.save()
    ctx.translate(cx, y1)
    ctx.scale(rb, ry)
    ctx.arc_negative(0, 0, 1, math.pi, 0)
    ctx.restore()
    ctx.line_to(cx + rx, y0)
    ctx.save()
    ctx.translate(cx, y0)
    ctx.scale(rx, ry)
    ctx.arc(0, 0, 1, 0, math.pi)
    ctx.restore()
    ctx.close_path()
    body = _mix(rgb, (14, 16, 28), 0.72)
    lit = _mix(rgb, (14, 16, 28), 0.40)
    g = cairo.LinearGradient(cx - rb, 0, cx + rb, 0)
    for p, c in ((0, _mix(body, (0, 0, 0), 0.45)), (0.28, lit), (0.55, body), (1, _mix(body, (0, 0, 0), 0.55))):
        g.add_color_stop_rgb(p, *(v / 255 for v in c))
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 0.85)
    ctx.set_line_width(2.5)
    ctx.stroke()
    # A darker inset band for the labels, with a bright line on top.
    band_y = y1 - BAND_ABOVE_BOTTOM
    ctx.new_path()
    ctx.move_to(cx - rx * 1.01, band_y)
    ctx.line_to(cx - rb, y1)
    ctx.save()
    ctx.translate(cx, y1)
    ctx.scale(rb, ry)
    ctx.arc_negative(0, 0, 1, math.pi, 0)
    ctx.restore()
    ctx.line_to(cx + rx * 1.01, band_y)
    ctx.save()
    ctx.translate(cx, band_y)
    ctx.scale(rx * 1.01, ry * 0.8)
    ctx.arc(0, 0, 1, 0, math.pi)
    ctx.restore()
    ctx.close_path()
    ctx.set_source_rgba(0.02, 0.03, 0.07, 0.55)
    ctx.fill()
    ctx.save()
    ctx.translate(cx, band_y)
    ctx.scale(rx * 1.01, ry * 0.8)
    ctx.arc(0, 0, 1, 0, math.pi)
    ctx.restore()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 0.7)
    ctx.set_line_width(2)
    ctx.stroke()
    # Top surface with a lit rim.
    ctx.save()
    ctx.translate(cx, y0)
    ctx.scale(rx, ry)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    g = cairo.RadialGradient(cx - rx * 0.2, y0 - ry * 0.4, 5, cx, y0, rx)
    g.add_color_stop_rgb(0, *(v / 255 for v in _mix(rgb, (255, 255, 255), 0.25)))
    g.add_color_stop_rgb(1, *(v / 255 for v in _mix(rgb, (20, 20, 30), 0.45)))
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(1, 1, 1, 0.65)
    ctx.set_line_width(2.5)
    ctx.stroke()
    img = fx.surface_to_image(surf).resize((sw // S, shh // S), Image.LANCZOS)
    return fx.glow(img, 10, 0.45, tint=rgb)   # glow pads 25px: the top ellipse centre is 93px down


def _beam(tone: str, top: int) -> Image.Image:
    """A soft spotlight falling on a plinth."""
    rgb = fx.TONE_RGB[tone]
    w, h = 520, top + 40
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    spread = 60 + (w / 2 - 60) * (y / h)
    a = np.clip(1 - np.abs(x - w / 2) / spread, 0, 1) ** 1.6 * (0.25 + 0.75 * y / h) * 0.22
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = _mix(rgb, (255, 255, 255), 0.5)
    img[..., 3] = a * 255
    return Image.fromarray(img.astype(np.uint8), "RGBA")


def _bar(spec: dict[str, Any], width: int, height: int) -> tuple[Image.Image, list[dict[str, Any]]]:
    """A neon-framed strip: title block, then items. Returns the sprite and
    the item sprites (drawn separately so they can animate)."""
    tone = spec.get("tone", "teal")
    rgb = fx.TONE_RGB[tone]
    S = 2
    pad = 30
    surf, ctx = fx.canvas_surface((width + pad * 2) * S, (height + pad * 2) * S)
    ctx.scale(S, S)
    r = 26
    x0, y0, x1, y1 = pad, pad, pad + width, pad + height
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.arc(x1 - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    ctx.arc(x1 - r, y1 - r, r, 0, 0.5 * math.pi)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()
    g = cairo.LinearGradient(0, y0, 0, y1)
    g.add_color_stop_rgba(0, *(v / 255 for v in _mix(rgb, (8, 12, 26), 0.78)), 0.92)
    g.add_color_stop_rgba(1, *(v / 255 for v in _mix(rgb, (4, 6, 14), 0.9)), 0.92)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 1)
    ctx.set_line_width(3)
    ctx.stroke()
    # Dividers between the title and each item.
    n = len(spec.get("items", []))
    title_w = 450
    col_w = (width - title_w) / max(1, n)
    for k in range(n):
        x = x0 + title_w + col_w * k
        ctx.move_to(x, y0 + 26)
        ctx.line_to(x, y1 - 26)
        ctx.set_source_rgba(*(v / 255 for v in rgb), 0.45)
        ctx.set_line_width(2)
        ctx.stroke()
    img = fx.surface_to_image(surf).resize(((width + pad * 2), (height + pad * 2)), Image.LANCZOS)
    img = fx.glow(img, 16, 0.8, tint=rgb)
    off = (img.width - width) / 2       # where the strip's left edge is in the sprite
    title_icon = fx.icon(spec.get("icon", "trophy"), int(height * 0.52), tone)
    title_txt = fx.metal_text(spec.get("title", ""), int(height * 0.36), tone)
    parts = [{"spr": title_icon, "x": off + 70, "kind": "icon"},
             {"spr": title_txt, "x": off + 70 + height * 0.36 + title_txt.width / 2 - 10, "kind": "title"}]
    for k, it in enumerate(spec.get("items", [])):
        cx0 = off + title_w + col_w * k
        ic = fx.icon(it.get("icon", "sparkles"), int(height * 0.56), tone if tone != "teal" else "gold")
        rank = fx.metal_text(str(it.get("rank", "")), int(height * 0.34), tone)
        label = fx.text(str(it.get("label", "")), int(height * 0.24), fx.FG, "bold")
        parts.append({"spr": ic, "x": cx0 + 40 + ic.width / 2 - 20, "kind": "icon", "item": k})
        tx = cx0 + 40 + height * 0.56 + 40
        parts.append({"spr": rank, "x": tx + rank.width / 2 - rank.width * 0.18, "dy": -height * 0.16,
                      "kind": "rank", "item": k})
        parts.append({"spr": label, "x": tx + label.width / 2 - label.width * 0.08, "dy": height * 0.2,
                      "kind": "label", "item": k})
    return img, parts


class Podium:
    """The scene, built once; ``frame(t)`` draws any moment of it."""

    def __init__(self, chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
                 footer: str = "Data in Motion", source: str = "World Bank"):
        self._build(chart, cues, offset, total, footer, source)

    def _build(self, chart, cues, offset, total, footer, source) -> None:
        tl = fx.Timeline(cues, offset)
        bg = fx.backdrop()
        gspec = chart.get("globe") or {}
        gl = fx.globe(GLOBE_R, float(gspec.get("lon0", 80)), float(gspec.get("lat0", 16)))
        flare = fx.flare(170)
        motes = fx.particles()

        arcs_t = None
        tiers = []
        fallback = 0.5
        for i, spec in enumerate((chart.get("podium") or [])[:3]):
            tone = spec.get("tone", ["gold", "silver", "bronze"][i])
            t0 = tl.find(spec.get("at", ""), fallback)
            fallback = t0 + 1.5
            if i == 0 and chart.get("arcs"):
                arcs_t = tl.find(chart["arcs"].get("at", "money"), t0 + 0.8)
            top = PED_TOP[i]
            ped = _pedestal(tone, top)
            rank = str(spec.get("rank", i + 1))
            nsize, hsize = (250, 112) if i == 0 else (215, 98)
            num = fx.metal_text(rank, nsize, tone)
            hsh = fx.metal_text("#", hsize, tone)
            gw = fx.font(nsize, "black").getlength(rank)
            hw = fx.font(hsize, "black").getlength("#")
            lh = 250 if i == 0 else 220
            laurels = {side: [fx.laurel(lh, tone, side, k) for k in range(11)] for side in (-1, 1)}
            icons = [fx.icon(n, 86, tone if tone != "silver" else "teal") for n in spec.get("icons", [])[:2]]
            label = fx.text(spec.get("label", ""), 46, fx.FG, "bold")
            sub = fx.text(spec.get("sub", ""), 34, (220, 226, 238), "semibold")
            tiers.append({"t": t0, "tone": tone, "x": PED_X[i], "top": top, "ped": ped, "num": num, "hash": hsh,
                          "laurels": laurels, "icons": icons, "gw": gw, "hw": hw, "label": label, "sub": sub, "beam": _beam(tone, top)})

        bars = []
        widths = [1580, 1660]
        for j, spec in enumerate((chart.get("bars") or [])[:2]):
            t0 = tl.find(spec.get("at", ""), fallback)
            fallback = t0 + 1.2
            spr, parts = _bar(spec, widths[j], BAR_H[j])
            bars.append({"t": t0, "spr": spr, "parts": parts, "y": BARS_Y[j], "tone": spec.get("tone", "teal"),
                         "w": widths[j]})

        finale = fx.Finale(chart.get("finale") or {}, tl, total)
        foot = fx.text(footer, 22, (70, 84, 120), "bold", shadow=False)
        src = fx.text(f"Source: {source}", 22, (150, 160, 180), "regular", shadow=False)

        # Remittance arcs: from the world's money centres into India.
        gx0, gy0 = GLOBE_XY[0] - gl["size"] / 2, GLOBE_XY[1] - gl["size"] / 2
        india = (gx0 + gl["india_xy"][0], gy0 + gl["india_xy"][1])
        sources = [(W * 0.98, 120), (W * 0.62, 40), (W * 0.30, 30), (40, 160), (W * 0.99, 560)]
        arcs = [fx.arc_path(p, india, lift=180 + 60 * k) for k, p in enumerate(sources)]
        self.finale = finale
        self.bg = bg
        self.gl = gl
        self.flare = flare
        self.motes = motes
        self.arcs_t = arcs_t
        self.arcs = arcs
        self.tiers = tiers
        self.bars = bars
        self.foot = foot
        self.src = src

    def frame(self, t: float) -> Image.Image:
        finale = self.finale
        bg = self.bg
        gl = self.gl
        flare = self.flare
        motes = self.motes
        arcs_t = self.arcs_t
        arcs = self.arcs
        tiers = self.tiers
        bars = self.bars
        foot = self.foot
        src = self.src
        fade = finale.fade(t)
        frame = bg.copy()
        # Globe: eases in, breathes very slightly; India pulses.
        gin = ease_out(t / 0.9)
        breathe = 1 + 0.006 * math.sin(t * 0.8)
        paste(frame, gl["base"], GLOBE_XY[0] - 40 * (1 - gin), GLOBE_XY[1], gin * fade, breathe)
        paste(frame, gl["india"], GLOBE_XY[0] - 40 * (1 - gin) + (gl["india_xy"][0] - gl["size"] / 2) * (breathe - 1),
              GLOBE_XY[1], (0.55 + 0.35 * math.sin(t * 2.2)) * gin * fade, breathe)
        paste(frame, flare, GLOBE_XY[0] + 250, GLOBE_XY[1] - 405, (0.75 + 0.2 * math.sin(t * 1.7)) * gin * fade)

        surf, ctx = fx.canvas_surface(W, H)
        fx.draw_particles(ctx, motes, t, fade)
        if arcs_t is not None and t >= arcs_t:
            for k, pts in enumerate(arcs):
                u = (t - arcs_t - 0.18 * k) / 1.1
                if u > 0:
                    pulse = ((t - arcs_t - 0.18 * k) / 2.2) % 1.0 if u > 1 else None
                    fx.draw_arc(ctx, pts, ease_out(u), alpha=0.85 * fade, pulse=pulse)
        frame.alpha_composite(fx.surface_to_image(surf))

        for tr in tiers:
            dt = t - tr["t"]
            if dt <= 0:
                continue
            x, top = tr["x"], tr["top"]
            rise = ease_out(dt / 0.65)
            paste(frame, tr["beam"], x, (top + 40) / 2 - 40, 0.9 * rise * fade)
            ped = tr["ped"]
            paste(frame, ped, x, top - 93 + (1 - rise) * 160, rise * fade, anchor="mt")
            # Numbers drop in with a bounce, then catch the light.
            v = ease_back((dt - 0.22) / 0.55, 1.5)
            if dt > 0.22:
                ny = top - 140 - (1 - v) * 120
                num = tr["num"]
                su = (dt - 0.85) % 5.0 / 0.9
                if 0 < su < 1:
                    num = fx.shine(num, su)
                a = min(1.0, (dt - 0.22) / 0.25) * fade
                left = x - (tr["hw"] + tr["gw"]) / 2
                sc = 1 + 0.25 * (1 - v)
                paste(frame, num, left + tr["hw"] + tr["gw"] / 2, ny, a, sc)
                paste(frame, tr["hash"], left + tr["hw"] / 2 + 4, ny + 26, a, sc)
            k = int(round(10 * ease_out((dt - 0.4) / 0.7)))
            if k > 0:
                span = (tr["hw"] + tr["gw"]) / 2 + tr["laurels"][1][10].width * 0.32
                for side in (-1, 1):
                    sp = tr["laurels"][side][k]
                    paste(frame, sp, x + 10 + side * span, top - 150, fade)
            for j, ic in enumerate(tr["icons"]):
                s = ease_back((dt - 0.45 - 0.12 * j) / 0.45)
                if s > 0:
                    ix = x - 70 + 140 * j if len(tr["icons"]) > 1 else x
                    # Centred between the top surface and the front ring.
                    iy = (top + 28 + PED_BOTTOM - BAND_ABOVE_BOTTOM) / 2
                    paste(frame, ic, ix, iy, min(1, s * 1.5) * fade, max(0.2, s))
            u = ease_out((dt - 0.6) / 0.45)
            if u > 0:
                paste(frame, tr["label"], x, PED_BOTTOM - 70 + (1 - u) * 16, u * fade)
                paste(frame, tr["sub"], x, PED_BOTTOM - 28 + (1 - u) * 16, u * fade)

        for b in bars:
            dt = t - b["t"]
            if dt <= 0:
                continue
            u = ease_out(dt / 0.55)
            bx = W / 2 - (1 - u) * 260 if b["tone"] != "red" else W / 2
            by = b["y"] + ((1 - u) * 90 if b["tone"] == "red" else 0)
            if b["tone"] == "red" and 0.3 < dt < 1.0:
                k2 = (dt - 0.3) / 0.7
                bx += math.sin(k2 * math.pi * 6) * 10 * (1 - k2)
            glow_pulse = 1.0
            if b["tone"] == "red" and dt > 0.5:
                glow_pulse = 0.85 + 0.15 * math.sin(dt * 4)
            paste(frame, b["spr"], bx, by, u * fade * glow_pulse)
            left = bx - b["spr"].width / 2
            for pi_, p in enumerate(b["parts"]):
                d0 = 0.2 + 0.08 * pi_
                v = (dt - d0) / 0.4
                if v <= 0:
                    continue
                dy = p.get("dy", 0)
                s = ease_back(v) if p["kind"] == "icon" else 1.0
                paste(frame, p["spr"], left + p["x"] - (1 - ease_out(v)) * 30, by + dy,
                      ease_out(v) * fade, max(0.3, s) if p["kind"] == "icon" else 1.0)

        paste(frame, foot, 96 + foot.width / 2 - 8, H - 26, 0.9 * fade)
        paste(frame, src, W - 96 - src.width / 2 + 8, H - 26, 0.9 * fade)
        finale.draw(frame, t)
        return frame


def render_podium(chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
                  out_path: Path, ffmpeg: str, footer: str = "Data in Motion", source: str = "World Bank",
                  encode_args: list[str] | None = None) -> float:
    scene = Podium(chart, cues, offset, total, footer, source)
    enc = fx.Encoder(out_path, ffmpeg, encode_args)
    n_frames = int(round(total * FPS))
    try:
        for f in range(n_frames):
            enc.write(scene.frame(f / FPS))
    finally:
        enc.close()
    return n_frames / FPS
