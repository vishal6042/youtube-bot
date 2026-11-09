"""Thumbnail in the documentary look: the night map, one country ringed in
gold, a three-line question and one giant number.

The script's ``thumbnail:`` block says what it shows::

    thumbnail:
      style: doc
      map: east                       # a carto.NIGHT_VIEWS name
      lines:
      - {text: BANGLADESH, box: Bangladesh}   # boxed in that country's colour
      - {text: IS RICHER THAN}
      - {text: INDIA?, country: India}        # set in that country's colour
      big: $2,130
      footnote: per person · 2019
      ring: {country: Bangladesh}
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import carto
from .doc import C, C_DARK, GOLD, IVORY, T, h_scrim, put, surface, rgb1

TW, TH = 1280, 720


def build_doc(ep: dict[str, Any], out_path: Path, settings: dict[str, Any] | None = None) -> Path:
    spec = ep.get("thumbnail") or {}
    m = carto.night(spec.get("map", "east"))
    plate = m.plate().copy()
    plate.alpha_composite(m.lights())
    frame = plate.resize((1920, 1080), Image.LANCZOS)
    frame.alpha_composite(h_scrim(((0, 0.88), (0.36, 0.7), (0.62, 0.0), (1, 0))))
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
    X, y = 92, 60
    d = ImageDraw.Draw(frame)
    for ln in spec.get("lines") or []:
        size = ln.get("size", 132 if ln.get("country") else 118)
        colour = C_DARK.get(ln.get("country"), IVORY)
        sp = T(ln["text"], "num", size, colour, track=-0.01)
        y += size * 0.95
        if ln.get("box"):
            d.rectangle([X - 22, y - size * 0.86, X + sp.w + 22, y + size * 0.16], fill=C[ln["box"]])
        put(frame, sp, X, y)
        y += size * 0.22
    if spec.get("big"):
        y += 250
        put(frame, T(spec["big"], "num", 300, IVORY), X - 10, y)
    if spec.get("footnote"):
        put(frame, T(spec["footnote"], "label", 40, GOLD), X, y + 74)
    frame.convert("RGB").resize((TW, TH), Image.LANCZOS).save(out_path, quality=92)
    return out_path
