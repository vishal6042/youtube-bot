"""Generate v5 channel brand assets: the rename to "Wonderlapse" (2026-11-14).

v5 rationale: the channel outgrew data charts (Math, Science and Space in Motion
now sit beside the data Shorts), so the mark stops being a chart line. It keeps
v4's look (charcoal, warm gold, ivory, Newsreader serif + Inter Tight, grain)
and its ringed point, but the point now rides an orbit: a serif W circled by a
gold path that passes behind the letter and comes round in front of it.

    .venv/Scripts/python.exe scripts/make_brand_v5.py

Writes into assets/brand/: channel_avatar_v5.png (800x800, ivory) + _dark,
channel_banner_v5.png (2560x1440), watermark_v5.png (150x150).
Shares page()/shoot() and the palette with make_brand_v4.py; v1-v4 files are
left untouched.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_brand_v4 import BRAND, CHARCOAL, GOLD, GOLD_HI, IVORY, page, shoot  # noqa: E402

NAME = "Wonderlapse"


def ellipse_arc(cx: float, cy: float, rx: float, ry: float, tilt: float,
                t0: float, t1: float, n: int = 120) -> tuple[str, list[tuple[float, float]]]:
    """Polyline path along a tilted ellipse from angle t0 to t1 (degrees).
    y grows downward, so t in (0, 180) is the near (lower) side of the orbit."""
    a = math.radians(tilt)
    pts = []
    for i in range(n + 1):
        t = math.radians(t0 + (t1 - t0) * i / n)
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return d, pts


# ---------------------------------------------------------------- avatar
ORBIT = dict(cx=400, cy=432, rx=286, ry=94, tilt=-22)
RING = 50


def monogram(light: bool, knock: str) -> str:
    """Serif W ringed by an orbit: the far side runs behind the letter, the near
    side sweeps in front of it and ends on v4's ringed point."""
    ink = "#16171A" if light else IVORY
    gold = "#A9853F" if light else GOLD
    dot = gold if light else GOLD_HI
    back, _ = ellipse_arc(**ORBIT, t0=180, t1=360)
    _, pts = ellipse_arc(**ORBIT, t0=0, t1=180, n=240)
    ex, ey = pts[0]                      # the ringed point sits on the orbit's right tip
    # the line stops short of the ring, so the point reads as a body, not a keyhole
    near = [p for p in pts if math.dist(p, (ex, ey)) > RING + 26]
    front = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in near)
    return f"""
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="{back}" stroke="{gold}" stroke-opacity="0.55" stroke-width="14"/>
</g>
<text x="400" y="596" text-anchor="middle" class="serif" font-weight="600" font-size="500" fill="{ink}">W</text>
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="{front}" stroke="{knock}" stroke-width="44"/>
  <path d="{front}" stroke="{gold}" stroke-width="24"/>
  <circle cx="{ex}" cy="{ey}" r="{RING}" fill="{knock}" stroke="{knock}" stroke-width="22"/>
  <circle cx="{ex}" cy="{ey}" r="{RING}" stroke="{gold}" stroke-width="9"/>
</g>
<circle cx="{ex}" cy="{ey}" r="24" fill="{dot}"/>
"""


def avatar(variant: str = "light") -> str:
    """Profile picture. YouTube masks it to a circle, so keep content inside r~340."""
    light = variant == "light"
    bg = IVORY if light else CHARCOAL
    svg = (f'<rect width="800" height="800" fill="{IVORY if light else "url(#key)"}"/>'
           f'<rect width="800" height="800" filter="url(#grain)" opacity="{0.05 if light else 0.10}"/>'
           + monogram(light, bg))
    return page(800, 800, svg)


def watermark() -> str:
    svg = (f'<circle cx="75" cy="75" r="73" fill="{CHARCOAL}" fill-opacity="0.78"/>'
           f'<g transform="translate(75,75) scale({138 / 800}) translate(-400,-400)">{monogram(False, CHARCOAL)}</g>')
    return page(150, 150, svg, bg="transparent")


# ---------------------------------------------------------------- banner
# YouTube: 2560x1440 image; TV shows all of it, desktop the 2560x423 middle
# band, phones only the centred 1546x423 safe area (x 507-2053, y 508-931).
def phyllotaxis(cx: float, cy: float, n: int, scale: float) -> str:
    """Golden-angle sunflower: the Math in Motion motif, faint, off to the right."""
    golden = math.pi * (3 - math.sqrt(5))
    out = []
    for k in range(1, n + 1):
        r = scale * math.sqrt(k)
        x, y = cx + r * math.cos(k * golden), cy + r * math.sin(k * golden)
        size = 2.2 + 3.2 * (1 - k / n)
        op = 0.08 + 0.22 * (1 - k / n)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size:.1f}" fill="{IVORY}" fill-opacity="{op:.2f}"/>')
    return "".join(out)


def stars(seed: int = 7, n: int = 70) -> str:
    """A sparse, faint star field for the Space side; kept out of the text column."""
    import random

    rnd = random.Random(seed)
    out = []
    while len(out) < n:
        x, y = rnd.uniform(0, 2560), rnd.uniform(40, 1400)
        if 560 < x < 1700 and 520 < y < 940:
            continue
        r = rnd.choice((1.2, 1.4, 1.8, 2.4))
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{IVORY}" fill-opacity="{rnd.uniform(0.12, 0.38):.2f}"/>')
    return "".join(out)


def banner() -> str:
    W, H = 2560, 1440
    orbit = dict(cx=1300, cy=820, rx=1150, ry=220, tilt=-4)
    ring_full, ring = ellipse_arc(**orbit, t0=0, t1=360, n=720)
    # the gold path rides the near side of the orbit, round the right-hand tip,
    # and stops on the far side at "now", inside the phone-safe band
    k_end = min(range(len(ring)), key=lambda i: (ring[i][0] - 1990) ** 2 + (ring[i][1] - 600) ** 2
                if ring[i][1] < 820 else 1e12)
    t_end = 360 * k_end / 720 - 360
    path, pts = ellipse_arc(**orbit, t0=165, t1=t_end, n=240)
    ex, ey = pts[-1]

    L = 600  # left text column
    svg = f"""
<radialGradient id="bkey" cx="0.40" cy="0.50" r="0.55">
  <stop offset="0" stop-color="#2B241A"/><stop offset="0.6" stop-color="#16171A"/><stop offset="1" stop-color="{CHARCOAL}"/>
</radialGradient>
<rect width="{W}" height="{H}" fill="url(#bkey)"/>
<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.07"/>
<filter id="soft" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
<mask id="clear" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
  <rect width="{W}" height="{H}" fill="white"/>
  <rect x="560" y="520" width="1460" height="420" rx="60" fill="black" filter="url(#soft)"/>
</mask>
{stars()}
{phyllotaxis(2330, 720, 260, 15.5)}
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="{ring_full}" stroke="{IVORY}" stroke-opacity="0.16" stroke-width="4" mask="url(#clear)"/>
  <path d="{path}" stroke="{CHARCOAL}" stroke-width="22"/>
  <path d="{path}" stroke="url(#goldline)" stroke-width="9"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="38" stroke="{GOLD}" stroke-width="4"/>
</g>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="13" fill="{GOLD_HI}"/>
<!-- left column -->
<text x="{L + 2}" y="562" class="sans" font-weight="700" font-size="27" letter-spacing="6" fill="{GOLD}">SHORTS EVERY DAY · DOCUMENTARIES EVERY WEEK</text>
<text x="{L - 8}" y="738" class="serif" font-weight="600" font-size="172" letter-spacing="-3" fill="{IVORY}">{NAME}</text>
<text x="{L}" y="842" class="serif" font-style="italic" font-weight="400" font-size="58" fill="{IVORY}" fill-opacity="0.82">The universe, one big idea at a time.</text>
<text x="{L}" y="908" class="sans" font-weight="600" font-size="26" letter-spacing="6" fill="{IVORY}" fill-opacity="0.55">MATH · SCIENCE · SPACE · WORLD DATA · INDIA · SPORTS</text>
"""
    return page(W, H, svg)


def main() -> None:
    shoot(avatar("light"), BRAND / "channel_avatar_v5.png", 800, 800)
    shoot(avatar("dark"), BRAND / "channel_avatar_v5_dark.png", 800, 800)
    shoot(banner(), BRAND / "channel_banner_v5.png", 2560, 1440)
    shoot(watermark(), BRAND / "watermark_v5.png", 150, 150, transparent=True)


if __name__ == "__main__":
    main()
