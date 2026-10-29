"""The cold-open hook: a fast, narrated opening that makes people stay.

As the narrator speaks: the globe pushes in on a glowing India; three stat
cards slam in (#1, #3, #144) with a flash and a jolt; arcs tie them back to
India; then ten rank chips fly in, a worst-to-best arrow sweeps under them,
and it ends on a mystery: two #1s, one of them still a question mark.

    chart:
      mode: hook
      globe: {lon0: 80, lat0: 16}
      cards:
      - {at: people, rank: '#1', tone: gold, icon: users, label: MOST PEOPLE ON EARTH, value: 1.46 billion}
      - {at: third, rank: '#3', tone: bronze, icon: coins, label: ECONOMY BY BUYING POWER, value: $17.2 trillion}
      - {at: hundred, rank: '#144', tone: red, icon: trending-down, label: INCOME PER PERSON, value: $2,702 a year}
      link: {at: three}
      ranks: {at: ten, title: 10 WORLD RANKINGS, chips: ['#144', '#137', '#5', '#4', '#3', '#3', '#2', '#2', '#1', '#1']}
      sweep: {at: worst, from: WORST, to: BEST}
      reveal: {at: number, known: PEOPLE, mystery: '?'}
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cairo
import numpy as np
from PIL import Image

from . import fx
from .fx import FPS, H, W, ease_back, ease_in_out, ease_out, paste

VERSION = 1

GLOBE_R = 560
CARD_W, CARD_H = 860, 220
CARD_X = 1425
CARD_Y = [250, 520, 790]


def _fit(s: str, size: int, max_w: float, weight: str = "bold") -> int:
    while size > 22 and fx.font(size, weight).getlength(s) > max_w:
        size -= 1
    return size


def _tone_for(rank: str) -> str:
    try:
        n = int(rank.strip("#"))
    except ValueError:
        return "gold"
    return {1: "gold", 2: "silver", 3: "bronze"}.get(n, "teal" if n <= 5 else "red")


def _glass(w: int, h: int, tone: str, radius: int = 30) -> Image.Image:
    rgb = fx.TONE_RGB[tone]
    S = 2
    pad = 24
    surf, ctx = fx.canvas_surface((w + pad * 2) * S, (h + pad * 2) * S)
    ctx.scale(S, S)
    x0, y0, x1, y1 = pad, pad, pad + w, pad + h
    r = radius
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.arc(x1 - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    ctx.arc(x1 - r, y1 - r, r, 0, 0.5 * math.pi)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()
    g = cairo.LinearGradient(0, y0, 0, y1)
    g.add_color_stop_rgba(0, 0.09, 0.12, 0.24, 0.92)
    g.add_color_stop_rgba(1, 0.03, 0.05, 0.12, 0.92)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 0.95)
    ctx.set_line_width(3)
    ctx.stroke()
    # Tone accent strip down the left edge.
    ctx.new_path()
    ctx.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    ctx.line_to(x0 + 14, y0)
    ctx.line_to(x0 + 14, y1)
    ctx.arc(x0 + r, y1 - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()
    ctx.set_source_rgba(*(v / 255 for v in rgb), 0.9)
    ctx.fill()
    img = fx.surface_to_image(surf).resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
    return fx.glow(img, 18, 0.7, tint=rgb)


class Hook:
    def __init__(self, chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
                 footer: str = "Data in Motion", source: str = "World Bank"):
        tl = fx.Timeline(cues, offset)
        self.total = total
        self.bg = fx.backdrop(map_alpha=0.12)
        gs = chart.get("globe") or {}
        self.gl = fx.globe(GLOBE_R, float(gs.get("lon0", 80)), float(gs.get("lat0", 16)))
        self.flare = fx.flare(190)
        self.motes = fx.particles(70)
        self.india_t = tl.find("india", 0.3)

        self.cards = []
        fb = 1.0
        for i, c in enumerate((chart.get("cards") or [])[:3]):
            tone = c.get("tone") or _tone_for(str(c.get("rank", "")))
            t0 = tl.find(c.get("at", ""), fb)
            fb = t0 + 1.5
            rank = fx.metal_text(str(c.get("rank", "")), 132 if len(str(c.get("rank", ""))) < 4 else 104, tone)
            self.cards.append({
                "t": t0, "tone": tone, "y": CARD_Y[i], "glass": _glass(CARD_W, CARD_H, tone), "rank": rank,
                "icon": fx.icon(c.get("icon", "sparkles"), 70, tone),
                "label": fx.text(str(c.get("label", "")), _fit(str(c.get("label", "")), 38, CARD_W - 420),
                                 (220, 228, 242), "bold"),
                "value": fx.text(str(c.get("value", "")), 64, fx.FG, "black", glow_r=6, glow_a=0.3),
            })
        self.link_t = tl.find((chart.get("link") or {}).get("at", "three"), total + 1)

        rk = chart.get("ranks") or {}
        self.ranks_t = tl.find(rk.get("at", "ten"), total + 1)
        self.title = fx.metal_text(rk.get("title", "10 WORLD RANKINGS"), 96, "gold")
        self.chips = []
        labels = rk.get("chips") or []
        n = len(labels)
        gap = 168
        x0 = W / 2 - gap * (n - 1) / 2
        rng = np.random.default_rng(4)
        for k, lab in enumerate(labels):
            tone = _tone_for(lab)
            size = 70 if len(lab) <= 2 else 54 if len(lab) == 3 else 46
            self.chips.append({"x": x0 + gap * k, "y": 540, "tone": tone,
                               "glass": _glass(140, 140, tone, radius=26), "num": fx.metal_text(lab, size, tone),
                               "from": (rng.uniform(-1, 1) * 900, rng.choice([-1, 1]) * rng.uniform(500, 800)),
                               "spin": rng.uniform(-200, 200), "delay": 0.07 * k, "label": lab})
        sw = chart.get("sweep") or {}
        self.sweep_t = tl.find(sw.get("at", "worst"), total + 1)
        self.worst = fx.text(sw.get("from", "WORST"), 40, (255, 110, 110), "black", glow_r=8, glow_a=0.5)
        self.best = fx.text(sw.get("to", "BEST"), 40, (255, 214, 90), "black", glow_r=8, glow_a=0.5)
        rv = chart.get("reveal") or {}
        self.reveal_t = tl.find(rv.get("at", "number"), total + 1)
        self.known = fx.text(rv.get("known", "PEOPLE"), 44, fx.FG, "black", glow_r=6, glow_a=0.3)
        self.mystery = fx.metal_text(rv.get("mystery", "?"), 120, "gold")
        self.foot = fx.text(footer, 22, (70, 84, 120), "bold", shadow=False)
        self.src = fx.text(f"Source: {source}", 22, (150, 160, 180), "regular", shadow=False)

    # ------------------------------------------------------------------ #
    def _shake(self, t: float) -> tuple[float, float, float]:
        """Camera jolt and white flash when a card lands."""
        dx = dy = flash = 0.0
        for c in self.cards:
            d = t - c["t"] - 0.18
            if 0 <= d < 0.45:
                k = 1 - d / 0.45
                amp = 16 if c["tone"] == "red" else 10
                dx += math.sin(d * 70) * amp * k
                dy += math.cos(d * 55) * amp * 0.6 * k
                flash = max(flash, (0.35 if c["tone"] == "red" else 0.22) * k ** 2)
        return dx, dy, flash

    def frame(self, t: float) -> Image.Image:
        frame = self.bg.copy()
        dx, dy, flash = self._shake(t)
        # Act one (globe + cards) gives way to act two (the ranks) at "ten".
        act1 = 1 - ease_out((t - self.ranks_t + 0.1) / 0.6)
        # The camera pushes in towards India all through act one.
        push = 1.0 + 0.16 * ease_in_out(t / max(1.0, self.ranks_t)) + 0.25 * (1 - act1)
        gx, gy = 560 + dx, 560 + dy
        gin = ease_out(t / 0.8)
        if act1 > 0.01:
            a = gin * act1
            paste(frame, self.gl["base"], gx, gy, a, push * (0.92 + 0.08 * gin))
            ix = gx + (self.gl["india_xy"][0] - self.gl["size"] / 2) * push
            iy = gy + (self.gl["india_xy"][1] - self.gl["size"] / 2) * push
            pulse = 0.55 + 0.35 * math.sin(t * 2.4)
            paste(frame, self.gl["india"], gx, gy, pulse * a, push * (0.92 + 0.08 * gin))
            paste(frame, self.flare, gx + 330 * push, gy - 470 * push, 0.8 * a)
            surf, ctx = fx.canvas_surface(W, H)
            # A shockwave ring from India when it is named.
            d = t - self.india_t
            if 0 < d < 1.4:
                r = 30 + 520 * ease_out(d / 1.4)
                ctx.arc(ix, iy, r, 0, 2 * math.pi)
                ctx.set_source_rgba(1.0, 0.7, 0.3, 0.8 * (1 - d / 1.4))
                ctx.set_line_width(6 * (1 - d / 1.4) + 1)
                ctx.stroke()
            fx.draw_particles(ctx, self.motes, t, a)
            # "All three are true": arcs from India to each card.
            if t > self.link_t:
                for k, c in enumerate(self.cards):
                    u = (t - self.link_t - 0.12 * k) / 0.7
                    if u > 0:
                        end = (CARD_X - CARD_W / 2 + dx - 6, c["y"] + dy)
                        pts = fx.arc_path((ix, iy), end, lift=60 + 40 * k)
                        col = tuple(v / 255 for v in fx.TONE_RGB[c["tone"]])
                        fx.draw_arc(ctx, pts, ease_out(u), colour=col, alpha=a,
                                    pulse=((t - self.link_t) / 1.4) % 1 if u > 1 else None)
            frame.alpha_composite(fx.surface_to_image(surf))
            for c in self.cards:
                d = t - c["t"]
                if d <= 0:
                    continue
                s = 1 + 0.6 * (1 - ease_back(d / 0.38, 1.3))      # slams down from big
                al = min(1.0, d / 0.15) * act1
                beat = 1.0
                if t > self.link_t:
                    beat = 1 + 0.025 * max(0.0, math.sin((t - self.link_t) * 6)) * (1 - ease_out((t - self.link_t) / 2))
                cx, cy = CARD_X + dx, c["y"] + dy
                paste(frame, c["glass"], cx, cy, al, s * beat)
                left = cx - CARD_W / 2 * s * beat
                paste(frame, c["rank"], left + 150 * s, cy, al, s * beat)
                v = ease_out((d - 0.25) / 0.35)
                if v > 0:
                    paste(frame, c["icon"], left + 330, cy - 40, v * act1)
                    paste(frame, c["label"], left + 390, cy - 40, v * act1, anchor="lm")
                    paste(frame, c["value"], left + 300 + (1 - v) * 30, cy + 42, v * act1, anchor="lm")

        # Act two: the ten rankings, worst to best.
        if t > self.ranks_t - 0.1:
            d = t - self.ranks_t
            focus = ease_out((t - self.reveal_t) / 0.7)
            u = ease_out(d / 0.5)
            paste(frame, self.title, W / 2, 300 - (1 - u) * 40, u * (1 - focus))
            surf, ctx = fx.canvas_surface(W, H)
            if t > self.sweep_t:
                sweep = ease_in_out((t - self.sweep_t) / 1.2)
                x0, x1 = self.chips[0]["x"] - 80, self.chips[-1]["x"] + 80
                xe = x0 + (x1 - x0) * sweep
                g = cairo.LinearGradient(x0, 0, x1, 0)
                g.add_color_stop_rgb(0, 1.0, 0.3, 0.3)
                g.add_color_stop_rgb(0.5, 0.35, 0.9, 0.8)
                g.add_color_stop_rgb(1, 1.0, 0.82, 0.3)
                for wdt, al in ((18, 0.12), (10, 0.3), (5, 1.0)):
                    ctx.move_to(x0, 690)
                    ctx.line_to(xe, 690)
                    ctx.set_line_width(wdt)
                    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                    ctx.push_group()
                    ctx.set_source(g)
                    ctx.stroke()
                    ctx.pop_group_to_source()
                    ctx.paint_with_alpha(al * (1 - focus))
                if sweep > 0.02:   # arrowhead
                    ctx.move_to(xe + 26, 690)
                    ctx.line_to(xe - 6, 672)
                    ctx.line_to(xe - 6, 708)
                    ctx.close_path()
                    ctx.set_source_rgba(1.0, 0.82, 0.3, 1 - focus)
                    ctx.fill()
            frame.alpha_composite(fx.surface_to_image(surf))
            if t > self.sweep_t:
                paste(frame, self.worst, self.chips[0]["x"], 750, ease_out((t - self.sweep_t) / 0.4) * (1 - focus))
                paste(frame, self.best, self.chips[-1]["x"], 750,
                      ease_out((t - self.sweep_t - 0.9) / 0.4) * (1 - focus))
            for k, ch in enumerate(self.chips):
                v = ease_out((d - ch["delay"]) / 0.55)
                if v <= 0:
                    continue
                fx_, fy_ = ch["from"]
                x = ch["x"] + fx_ * (1 - v)
                y = ch["y"] + fy_ * (1 - v)
                lift = 1.0
                if t > self.sweep_t:   # each chip pops as the arrow passes it
                    pass_t = self.sweep_t + 1.2 * (k + 0.5) / len(self.chips)
                    q = (t - pass_t) / 0.35
                    if 0 < q < 1:
                        lift = 1 + 0.18 * math.sin(q * math.pi)
                is_one = ch["label"] == "#1"
                last_one = k == len(self.chips) - 1
                a = v * (1 - focus * (0.0 if is_one else 0.88))
                s = lift
                if is_one and focus > 0:
                    # The two #1s come forward to the middle.
                    first_one = next(i for i, c in enumerate(self.chips) if c["label"] == "#1")
                    tx = W / 2 + (-200 if k == first_one else 200)
                    x = x + (tx - x) * focus
                    y = y + (500 - y) * focus
                    s = lift * (1 + 1.1 * focus)
                spr_g, spr_n = ch["glass"], ch["num"]
                if abs(ch["spin"]) > 1 and v < 1:
                    ang = ch["spin"] * (1 - v)
                    spr_g = spr_g.rotate(ang, Image.BICUBIC, expand=True)
                    spr_n = spr_n.rotate(ang, Image.BICUBIC, expand=True)
                paste(frame, spr_g, x, y, a, s)
                if is_one and last_one and focus > 0.4:
                    # The second #1 is still a secret.
                    pulse = 1 + 0.05 * math.sin((t - self.reveal_t) * 6)
                    paste(frame, spr_n, x, y - 22 * focus, a * (1 - ease_out((focus - 0.4) / 0.3)), s)
                    paste(frame, self.mystery, x, y + 6, ease_out((focus - 0.4) / 0.4), s * 0.55 * pulse)
                else:
                    paste(frame, fx.shine(spr_n, ((t - self.ranks_t - 0.7 - 0.05 * k) / 0.8))
                          if 0 < t - self.ranks_t - 0.7 - 0.05 * k < 0.8 else spr_n, x, y, a, s)
                if is_one and not last_one and focus > 0.5:
                    paste(frame, self.known, x, y + 175, ease_out((focus - 0.5) / 0.4))
            if focus > 0.5:
                q = fx.text("?", 44, (255, 214, 90), "black", glow_r=8, glow_a=0.6)
                paste(frame, q, W / 2 + 200, 675, ease_out((focus - 0.5) / 0.4))

        if flash > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 240, 220, int(255 * flash))))
        paste(frame, self.foot, 96 + self.foot.width / 2 - 8, H - 26, 0.9)
        paste(frame, self.src, W - 96 - self.src.width / 2 + 8, H - 26, 0.9)
        return frame


def render_hook(chart: dict[str, Any], cues: list[dict[str, Any]], offset: float, total: float,
                out_path: Path, ffmpeg: str, footer: str = "Data in Motion", source: str = "World Bank",
                encode_args: list[str] | None = None) -> float:
    scene = Hook(chart, cues, offset, total, footer, source)
    enc = fx.Encoder(out_path, ffmpeg, encode_args)
    n_frames = int(round(total * FPS))
    try:
        for f in range(n_frames):
            enc.write(scene.frame(f / FPS))
    finally:
        enc.close()
    return n_frames / FPS
