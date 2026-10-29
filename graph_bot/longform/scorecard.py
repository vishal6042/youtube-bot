"""An animated scorecard for a long-form chapter, timed to the narration.

A recap chapter ("first in people, second in phones ...") reads badly over an
unrelated data chart. This draws the recap itself: a pyramid of medal rows that
slide in as the narrator names them, then a closing line lit word by word as
it is spoken, then subscribe/share buttons. The script says what to show and
which spoken word triggers each part:

    chart:
      mode: scorecard
      subtitle: India's place in 10 world rankings
      tiers:
      - {badge: "#1", tone: gold, at: first, items: [Population, Money sent home]}
      - {badge: "#2", tone: silver, at: second, items: [Mobile phones, IT services]}
      - {badge: "#3", tone: bronze, at: third, items: [Science papers, Buying power]}
      - {badge: TOP 5, tone: teal, at: top, items: ["#4 Flying", "#5 Inventions"]}
      - {badge: LOW, tone: red, at: still, items: ["#137 Life expectancy", "#144 Income per person"]}
      finale:
        at: india                     # first spoken word of the closing line
        lines: [INDIA IS A GIANT, STILL GETTING RICH, one person at a time]
        accent: [INDIA, GIANT]        # words drawn in saffron
      question: {at: which, text: Which ranking surprised you most?}
      subscribe: {at: subscribe}
      share: {at: share}

Trigger words are matched in order against the narration's word timings, so
"still" means the first "still" after the previous trigger.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..sims.canvas import font, hex_rgb

W, H, FPS = 1920, 1080, 30
VERSION = 3   # bump when the drawing changes, so cached scorecard chapters re-render
SS = 2  # sprites are drawn at 2x and shrunk, which antialiases every edge

FG = (242, 245, 250)
MUTED = (154, 164, 178)
ACCENT = (94, 224, 200)
SAFFRON = (255, 179, 71)      # the long-form highlight colour (render.HIGHLIGHT)
BG_TOP, BG_BOTTOM = hex_rgb("#182140"), hex_rgb("#0a0e1c")
CARD = (20, 27, 50)

TONES = {   # badge fill, badge text
    "gold": ((255, 207, 63), (42, 29, 0)),
    "silver": ((223, 230, 240), (27, 34, 48)),
    "bronze": ((229, 154, 91), (43, 22, 7)),
    "teal": ((94, 224, 200), (6, 38, 33)),
    "red": ((255, 77, 77), (255, 255, 255)),
}


# --------------------------------------------------------------------------- #
# Timing
# --------------------------------------------------------------------------- #
def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


class Timeline:
    """Finds when trigger words are spoken, in order."""

    def __init__(self, cues: list[dict[str, Any]], offset: float):
        self.words = [(_norm(c["text"]), c["start"] + offset, c["end"] + offset) for c in cues]
        self.pos = 0

    def find(self, word: str, default: float) -> float:
        want = _norm(word)
        for i in range(self.pos, len(self.words)):
            if self.words[i][0] == want:
                self.pos = i + 1
                return self.words[i][1]
        return default

    def run(self, words: list[str]) -> list[float]:
        """Start time of each of ``words`` spoken one after another from here."""
        out, last = [], None
        for w in words:
            t = self.find(w, -1.0)
            if t < 0:
                t = (last or 0.0) + 0.25 if last is not None else -1.0
            out.append(t)
            last = t
        return out


# --------------------------------------------------------------------------- #
# Easing
# --------------------------------------------------------------------------- #
def _clamp(u: float) -> float:
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_out(u: float) -> float:
    u = _clamp(u)
    return 1 - (1 - u) ** 3


def ease_back(u: float, s: float = 1.9) -> float:
    """Overshoots a little and settles: the 'pop' of a medal."""
    u = _clamp(u)
    u -= 1
    return u * u * ((s + 1) * u + s) + 1


# --------------------------------------------------------------------------- #
# Sprites
# --------------------------------------------------------------------------- #
def _shrink(img: Image.Image) -> Image.Image:
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def _card(w: int, h: int, tone: tuple[int, int, int]) -> Image.Image:
    """Row card: dark glass with a coloured rim and a faint top sheen."""
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    r = 28 * SS
    d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r, fill=(*CARD, 238),
                        outline=(*tone, 170), width=3 * SS)
    sheen = Image.new("RGBA", big.size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle([3 * SS, 3 * SS, w * SS - 3 * SS, h * SS // 2], radius=r,
                                            fill=(255, 255, 255, 10))
    big.alpha_composite(sheen)
    return _shrink(big)


def _shadow(w: int, h: int) -> Image.Image:
    pad = 40
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([pad, pad + 10, pad + w, pad + h + 10], radius=28,
                                          fill=(0, 0, 0, 160))
    return img.filter(ImageFilter.GaussianBlur(14))


def _badge(text: str, tone: str, h: int) -> Image.Image:
    """A medal (round, with a ribbon notch and inner ring) or a pill for words."""
    fill, ink = TONES.get(tone, TONES["teal"])
    medal = tone in ("gold", "silver", "bronze")
    f = font(int(h * (0.42 if medal else 0.30)) * SS)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = probe.textlength(text, font=f) / SS
    w = h if medal else int(tw + h * 0.7)
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if medal:
        d.ellipse([0, 0, h * SS - 1, h * SS - 1], fill=fill)
        light = tuple(min(255, int(c * 1.12 + 12)) for c in fill)
        dark = tuple(int(c * 0.78) for c in fill)
        inset = int(h * 0.11) * SS
        d.ellipse([inset, inset, h * SS - inset, h * SS - inset], outline=dark, width=3 * SS)
        d.pieslice([inset, inset, h * SS - inset, h * SS - inset], 200, 290, fill=light)
        d.ellipse([inset + 3 * SS, inset + 3 * SS, h * SS - inset - 3 * SS, h * SS - inset - 3 * SS],
                  fill=fill)
    else:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=h * SS // 2, fill=fill)
    d.text((w * SS / 2, h * SS / 2 + SS), text, font=f, fill=ink, anchor="mm")
    return _shrink(big)


def _text(s: str, size: int, colour, glow: float = 0.0) -> Image.Image:
    """Text on a sprite sized from the font's metrics, not the glyphs' ink.

    Every sprite of one size is the same height with the baseline in the same
    place, so words pasted at the same centre line sit on one baseline, and the
    sprite is exactly ``pad`` wider than the text's advance on each side.
    """
    f = font(size * SS)
    ascent, descent = f.getmetrics()
    pad = size * SS // 2
    adv = int(round(f.getlength(s)))
    big = Image.new("RGBA", (adv + pad * 2, ascent + descent + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((pad, pad + ascent), s, font=f, fill=colour, anchor="ls")
    if glow:
        halo = big.filter(ImageFilter.GaussianBlur(size * SS * 0.18))
        a = np.asarray(halo).astype(np.float32)
        a[..., 3] *= glow
        halo = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        halo.alpha_composite(big)
        big = halo
    return _shrink(big)


def _with_alpha(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def _paste(canvas: Image.Image, spr: Image.Image, x: float, y: float, a: float = 1.0,
           s: float = 1.0) -> None:
    """Composite ``spr`` centred on (x, y), faded to ``a`` and scaled by ``s``."""
    if a <= 0.003:
        return
    if abs(s - 1) > 0.004:
        spr = spr.resize((max(1, int(spr.width * s)), max(1, int(spr.height * s))), Image.BICUBIC)
    spr = _with_alpha(spr, a)
    canvas.alpha_composite(spr, (int(round(x - spr.width / 2)), int(round(y - spr.height / 2))))


def _background(subtitle: str, title: str, source: str, footer: str) -> Image.Image:
    """The same frame every chart chapter has: gradient, title block, footer."""
    t = np.linspace(0, 1, H)[:, None, None]
    grad = np.array(BG_TOP)[None, None, :] * (1 - t) + np.array(BG_BOTTOM)[None, None, :] * t
    img = np.broadcast_to(grad, (H, W, 3)).astype(np.float32).copy()
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    glow = np.exp(-(((x - W * 0.5) / (W * 0.38)) ** 2 + ((y - H * 0.55) / (H * 0.5)) ** 2))
    img += glow[..., None] * np.array([30, 22, 8], np.float32)   # a warm haze behind the pyramid
    bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(bg)
    d.text((96, 48), title, font=font(61), fill=FG, anchor="la")
    d.line([(96, 138), (250, 138)], fill=ACCENT, width=5)
    if subtitle:
        d.text((278, 138), subtitle, font=font(31, bold=False), fill=MUTED, anchor="lm")
    d.text((W - 96, H - 32), f"Source: {source}", font=font(21, bold=False), fill=MUTED, anchor="rs")
    if footer:
        d.text((96, H - 32), footer, font=font(21), fill=(52, 62, 90), anchor="ls")
    return bg


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render_scorecard(chart: dict[str, Any], heading: str, cues: list[dict[str, Any]], offset: float,
                     total: float, out_path: Path, ffmpeg: str, footer: str = "Data in Motion",
                     encode_args: list[str] | None = None) -> float:
    """Write the scorecard video (silent, ``total`` seconds) and return its length."""
    import subprocess

    tl = Timeline(cues, offset)
    tiers = chart.get("tiers") or []
    n = len(tiers)
    row_h, gap = 112, 20
    top = 196
    span_h = n * row_h + (n - 1) * gap
    top += max(0, (H - 70 - top - span_h) // 2)
    widths = [int(1000 + (1500 - 1000) * (i / max(1, n - 1))) for i in range(n)]   # a pyramid

    rows = []
    fallback = 0.6
    for i, tier in enumerate(tiers):
        tone = tier.get("tone", "teal")
        fill = TONES.get(tone, TONES["teal"])[0]
        w = widths[i]
        t0 = tl.find(tier.get("at", ""), fallback)
        fallback = t0 + 1.2
        badge = _badge(str(tier.get("badge", "")), tone, row_h - 24)
        labels = [str(s) for s in tier.get("items", [])]
        col_w = (w - 18 - badge.width - 48) / max(1, len(labels))
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        size = 42
        while size > 24 and max((probe.textlength(s, font=font(size)) for s in labels), default=0) > col_w - 24:
            size -= 2
        items = [_text(s, size, (255, 120, 120) if tone == "red" else FG) for s in labels]
        rows.append({"y": top + i * (row_h + gap) + row_h / 2, "w": w, "t": t0, "tone": tone,
                     "card": _card(w, row_h, fill), "shadow": _shadow(w, row_h), "badge": badge,
                     "items": items})

    fin = chart.get("finale") or {}
    fin_words: list[dict[str, Any]] = []
    fin_t = total + 1
    if fin.get("lines"):
        accent = {_norm(a) for a in fin.get("accent", [])}
        tl.find(fin.get("at", ""), -1)      # move to the start of the line
        tl.pos = max(0, tl.pos - 1)
        sizes = [96, 96, 52]
        ys = [H * 0.40, H * 0.40 + 112, H * 0.40 + 200]
        for li, line in enumerate(fin["lines"]):
            size = sizes[min(li, 2)]
            words = line.split()
            times = tl.run(words)
            sprites = []
            for word in words:
                on = SAFFRON if _norm(word) in accent else FG
                sprites.append((_text(word, size, on, glow=0.55 if _norm(word) in accent else 0.25),
                                _text(word, size, (70, 80, 104))))
            space = font(size).getlength(" ")
            widths_w = [s[0].width - 2 * (size * SS // 2) // SS for s in sprites]   # strip the side padding
            line_w = sum(widths_w) + space * (len(words) - 1)
            x = W / 2 - line_w / 2
            for (lit, dim), ww, t in zip(sprites, widths_w, times):
                fin_words.append({"x": x + ww / 2, "y": ys[min(li, 2)], "t": t, "lit": lit, "dim": dim})
                x += ww + space
        valid = [w["t"] for w in fin_words if w["t"] >= 0]
        fin_t = (min(valid) - 0.35) if valid else total + 1
        for w in fin_words:
            if w["t"] < 0:
                w["t"] = fin_t + 0.4

    q = chart.get("question") or {}
    q_t = tl.find(q.get("at", ""), total + 1) if q else total + 1
    q_spr = _text(q.get("text", ""), 44, ACCENT) if q else None
    sub = chart.get("subscribe")
    sub_t = tl.find(sub.get("at", "subscribe"), total + 1) if sub else total + 1
    share = chart.get("share")
    share_t = tl.find(share.get("at", "share"), total + 1) if share else total + 1
    sub_spr = None
    if sub:
        big = Image.new("RGBA", (360 * SS, 96 * SS), (0, 0, 0, 0))
        dd = ImageDraw.Draw(big)
        dd.rounded_rectangle([0, 0, 360 * SS - 1, 96 * SS - 1], radius=48 * SS, fill=(255, 64, 64))
        dd.text((180 * SS, 48 * SS + SS), "SUBSCRIBE", font=font(30 * SS), fill=(255, 255, 255), anchor="mm")
        sub_spr = _shrink(big)
    share_spr = None
    if share:
        big = Image.new("RGBA", (360 * SS, 96 * SS), (0, 0, 0, 0))
        dd = ImageDraw.Draw(big)
        dd.rounded_rectangle([0, 0, 360 * SS - 1, 96 * SS - 1], radius=48 * SS, outline=FG, width=4 * SS,
                             fill=(20, 27, 50, 220))
        dd.text((180 * SS, 48 * SS + SS), "SHARE", font=font(30 * SS), fill=FG, anchor="mm")
        share_spr = _shrink(big)

    bg = _background(chart.get("subtitle", ""), heading, chart.get("source", "World Bank"), footer)
    scrim = Image.new("RGBA", (W, H), (6, 9, 20, 255))
    n_frames = int(round(total * FPS))
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", *(encode_args or ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]),
           "-pix_fmt", "yuv420p", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for f in range(n_frames):
            t = f / FPS
            frame = bg.copy()
            # The pyramid fades back once the closing line begins.
            fade = 1 - 0.96 * ease_out((t - fin_t) / 0.7)
            for r in rows:
                u = (t - r["t"]) / 0.5
                if u <= 0:
                    continue
                a = ease_out(u) * fade
                dy = (1 - ease_out(u)) * 46
                dx = 0.0
                if r["tone"] == "red" and 0 < t - r["t"] < 0.7:      # a short shake: the bad news
                    k = (t - r["t"]) / 0.7
                    dx = math.sin(k * math.pi * 6) * 9 * (1 - k)
                cx, cy = W / 2 + dx, r["y"] + dy
                _paste(frame, r["shadow"], cx, cy, a * 0.9)
                _paste(frame, r["card"], cx, cy, a)
                left = cx - r["w"] / 2
                bs = ease_back((t - r["t"] - 0.08) / 0.45)
                if bs > 0:
                    _paste(frame, r["badge"], left + 18 + r["badge"].width / 2, cy, min(1, bs) * fade,
                           0.35 + 0.65 * bs)
                # Items share the space right of the badge, in equal columns.
                x0 = left + 18 + r["badge"].width + 24
                col_w = (cx + r["w"] / 2 - 24 - x0) / max(1, len(r["items"]))
                for j, it in enumerate(r["items"]):
                    v = ease_out((t - r["t"] - 0.18 - 0.14 * j) / 0.4)
                    if v > 0:
                        _paste(frame, it, x0 + col_w * (j + 0.5) - (1 - v) * 30, cy, v * fade)
            if t >= fin_t:
                frame.alpha_composite(_with_alpha(scrim, 0.7 * ease_out((t - fin_t) / 0.7)))
                for w in fin_words:
                    _paste(frame, w["dim"], w["x"], w["y"], ease_out((t - fin_t) / 0.5))
                    v = ease_out((t - w["t"]) / 0.25)
                    if v > 0:
                        _paste(frame, w["lit"], w["x"], w["y"], v, 1 + 0.06 * (1 - ease_back((t - w["t"]) / 0.35)))
            if q_spr is not None and t >= q_t:
                _paste(frame, q_spr, W / 2, H * 0.40 + 300 - (1 - ease_out((t - q_t) / 0.4)) * 24,
                       ease_out((t - q_t) / 0.4))
            if sub_spr is not None and t >= sub_t:
                s = ease_back((t - sub_t) / 0.45)
                pulse = 1 + 0.04 * math.sin((t - sub_t) * 5.0) if t - sub_t > 0.45 else 1.0
                _paste(frame, sub_spr, W / 2 - (200 if share_spr else 0), H * 0.40 + 420,
                       min(1, s * 1.4), max(0.3, s) * pulse)
            if share_spr is not None and t >= share_t:
                s = ease_back((t - share_t) / 0.45)
                _paste(frame, share_spr, W / 2 + 200, H * 0.40 + 420, min(1, s * 1.4), max(0.3, s))
            proc.stdin.write(np.asarray(frame.convert("RGB")).tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed writing the scorecard")
    return n_frames / FPS
