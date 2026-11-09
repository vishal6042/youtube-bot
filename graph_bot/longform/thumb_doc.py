"""Thumbnail in the documentary look: the night map, one country ringed in
gold, a few short lines and one giant number.

The script's ``thumbnail:`` block says what it shows::

    thumbnail:
      style: doc
      map: east                       # a carto.NIGHT_VIEWS name, or {s, cx, cy, ox, oy}
      flags: 0.9                      # fill the countries with their flags (0 = off)
      lights: 0.5                     # city lights over the map (default 1)
      kicker: India · Pakistan · Bangladesh     # small gold label above the lines
      lines:
      - {text: BANGLADESH, box: Bangladesh}   # boxed in that country's colour
      - {text: IS RICHER THAN}
      - {text: INDIA?, country: India}        # set in that country's colour
      big: $2,130
      footnote: per person · 2019
      ring: {country: Bangladesh}
      tags:                           # value cards pinned on the map
      - {country: India, text: $2,702, sub: India}
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import carto, fx
from .doc import C, C_DARK, GOLD, IVORY, T, h_scrim, halo, put, surface, rgb1

TW, TH = 1280, 720
FLAGS = ("India", "Pakistan", "Bangladesh")


def _map(spec: dict[str, Any]) -> carto.NightMap:
    view = spec.get("map", "east")
    return carto.NightMap(**view) if isinstance(view, dict) else carto.night(view)


def _tag(frame: Image.Image, x: float, y: float, text: str, sub: str | None, country: str | None) -> None:
    """A dark value card with a gold rule and a pin, centred over (x, y)."""
    big = T(text, "num", 92, IVORY)
    small = T(sub.upper(), "label", 26, C_DARK.get(country, GOLD)) if sub else None
    w = max(big.w, small.w if small else 0) + 64
    h = 92 + (40 if small else 0) + 30
    # the card stays inside the frame; its pin still points at (x, y)
    x0, y0 = min(max(x - w / 2, 40), 1880 - w), y - h - 26
    cx = x0 + w / 2
    s, c = surface()
    # soft shadow, card, gold top rule, pin stem
    for k, a in ((14, 0.10), (8, 0.14), (3, 0.18)):
        c.rectangle(x0 - k + 6, y0 - k + 10, w + 2 * k, h + 2 * k)
        c.set_source_rgba(0, 0, 0, a)
        c.fill()
    c.rectangle(x0, y0, w, h)
    c.set_source_rgba(14 / 255, 15 / 255, 18 / 255, 0.9)
    c.fill()
    c.rectangle(x0, y0, w, 6)
    c.set_source_rgba(*rgb1(GOLD))
    c.fill()
    px = min(max(x, x0 + 24), x0 + w - 24)
    c.move_to(px - 13, y0 + h)
    c.line_to(px + 13, y0 + h)
    c.line_to(x, y - 6)
    c.close_path()
    c.set_source_rgba(14 / 255, 15 / 255, 18 / 255, 0.9)
    c.fill()
    c.arc(x, y, 9, 0, 2 * math.pi)
    c.set_source_rgba(*rgb1(GOLD))
    c.fill()
    frame.alpha_composite(carto.to_img(s))
    yy = y0 + 22
    if small:
        put(frame, small, cx, yy + 26, "c")
        yy += 40
    put(frame, big, cx, yy + 84, "c")


def build_doc(ep: dict[str, Any], out_path: Path, settings: dict[str, Any] | None = None) -> Path:
    spec = ep.get("thumbnail") or {}
    m = _map(spec)
    plate = m.plate().copy()
    fa = float(spec.get("flags", 0) or 0)
    if fa > 0:
        for n in spec.get("flag_countries") or FLAGS:
            plate.alpha_composite(fx.with_alpha(m.flag_of(n), fa))
    la = float(spec.get("lights", 1.0))
    if la > 0:
        plate.alpha_composite(fx.with_alpha(m.lights(), la))
    frame = plate.resize((1920, 1080), Image.LANCZOS)
    frame.alpha_composite(h_scrim(tuple(tuple(s) for s in spec.get("scrim", ((0, 0.88), (0.36, 0.7), (0.62, 0.0), (1, 0))))))
    ring = spec.get("ring")
    if ring:
        lon, lat = carto.COUNTRY_POINTS[ring["country"]]
        x, y = m.proj(lon, lat)
        s, c = surface()
        c.arc(x, y, ring.get("r", 120), 0, 2 * math.pi)
        c.set_source_rgba(*rgb1(GOLD, 0.95))
        c.set_line_width(7)
        c.stroke()
        frame.alpha_composite(carto.to_img(s))
    for tg in spec.get("tags") or []:
        lon, lat = tg.get("at") or carto.COUNTRY_POINTS[tg["country"]]
        x, y = m.proj(lon, lat)
        _tag(frame, x, y, str(tg["text"]), tg.get("sub"), tg.get("country"))
    X, y = int(spec.get("x", 92)), int(spec.get("y", 60))
    d = ImageDraw.Draw(frame)
    if spec.get("kicker"):
        y += 44
        put(frame, T(spec["kicker"], "label", 38, GOLD), X, y)
        y += 20
    for ln in spec.get("lines") or []:
        size = ln.get("size", 132 if ln.get("country") else 118)
        colour = C_DARK.get(ln.get("country"), IVORY)
        sp = T(ln["text"], "num", size, colour, track=-0.01)
        y += size * 0.95
        if ln.get("box"):
            d.rectangle([X - 22, y - size * 0.86, X + sp.w + 22, y + size * 0.16], fill=C[ln["box"]])
        elif fa > 0:
            put(frame, halo(sp, r=14.0), X, y, "l", 0.8)
        put(frame, sp, X, y)
        y += size * 0.22
    if spec.get("big"):
        y += 250
        put(frame, T(spec["big"], "num", 300, IVORY), X - 10, y)
    if spec.get("footnote"):
        put(frame, T(spec["footnote"], "label", 40, GOLD), X, y + 74)
    frame.convert("RGB").resize((TW, TH), Image.LANCZOS).save(out_path, quality=92)
    return out_path
