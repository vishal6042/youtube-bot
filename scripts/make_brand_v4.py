"""Generate v4 channel brand assets in the Visual Direction v2.0 look.

v4 rationale: the channel moved from neon Shorts to documentary-style data
journalism (charcoal, warm gold, ivory, Newsreader serif + Inter Tight). The
mark is "the overtake": a gold line rising past an ivory one and ending on an
annotated data point, the moment every race video builds to.

    .venv/Scripts/python.exe scripts/make_brand_v4.py

Writes into assets/brand/: channel_avatar_v4.png (800x800, ivory) + _dark,
channel_banner_v4.png (2560x1440), watermark_v4.png (150x150).
Pages are drawn as HTML/SVG and screenshotted with headless Chrome so the
type matches the videos exactly. v1-v3 files are left untouched.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]

CHARCOAL = "#0E1013"
IVORY = "#F2ECE0"
GOLD = "#C9A45C"
GOLD_HI = "#E3C27E"

FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@'
         '0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Inter+Tight:wght@500;600;700;800'
         '&display=block" rel="stylesheet">')

# Shared SVG defs: film grain and a warm key light. Grain keeps flat charcoal
# from looking like a vector default.
DEFS = f"""
<filter id="grain" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"/>
  <feColorMatrix values="0 0 0 0 1  0 0 0 0 0.95  0 0 0 0 0.88  0 0 0 0.55 0"/>
</filter>
<radialGradient id="key" cx="0.42" cy="0.52" r="0.62">
  <stop offset="0" stop-color="#2A241B"/>
  <stop offset="0.55" stop-color="#16171A"/>
  <stop offset="1" stop-color="{CHARCOAL}"/>
</radialGradient>
<linearGradient id="goldline" x1="0" y1="1" x2="1" y2="0">
  <stop offset="0" stop-color="#A9853F"/>
  <stop offset="1" stop-color="{GOLD_HI}"/>
</linearGradient>
"""


def smooth(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom through the points, as an SVG cubic path."""
    p = [points[0], *points, points[-1]]
    d = f"M{p[1][0]:.1f},{p[1][1]:.1f}"
    for i in range(1, len(p) - 2):
        x0, y0 = p[i - 1]; x1, y1 = p[i]; x2, y2 = p[i + 1]; x3, y3 = p[i + 2]
        c1 = (x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6)
        c2 = (x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}"
    return d


def page(w: int, h: int, svg: str, bg: str = CHARCOAL) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}
<style>html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{bg}}}
svg{{display:block}} .serif{{font-family:Newsreader,serif}} .sans{{font-family:'Inter Tight',sans-serif}}</style>
</head><body><svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>{DEFS}</defs>{svg}</svg></body></html>"""


# ---------------------------------------------------------------- avatar
# The data points of the monogram's chart line (800 grid), ending on "now".
LINE = [(342, 520), (372, 478), (420, 494), (470, 392), (520, 352), (566, 300), (620, 238)]


def monogram(light: bool, knock: str) -> str:
    """Serif D crossed by a rising chart line that ends on a ringed data point.
    `knock` is the colour cut around the line so it sits in front of the D."""
    ink = "#16171A" if light else IVORY
    gold = "#A9853F" if light else GOLD
    fill = gold if light else "url(#goldline)"
    dot = gold if light else GOLD_HI
    pts = " ".join(f"{x},{y}" for x, y in LINE)
    ex, ey = LINE[-1]
    return f"""
<text x="384" y="598" text-anchor="middle" class="serif" font-weight="600" font-size="600" fill="{ink}">D</text>
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="{pts}" stroke="{knock}" stroke-width="44"/>
  <polyline points="{pts}" stroke="{fill}" stroke-width="24"/>
  <circle cx="{ex}" cy="{ey}" r="58" stroke="{knock}" stroke-width="22"/>
  <circle cx="{ex}" cy="{ey}" r="58" stroke="{gold}" stroke-width="9"/>
</g>
<circle cx="{ex}" cy="{ey}" r="27" fill="{dot}"/>
"""


def avatar(variant: str = "light") -> str:
    """Profile picture. YouTube masks it to a circle, so keep content inside r~340.
    Ivory is the primary: it stands out on YouTube's dark UI and against the dark banner."""
    light = variant == "light"
    bg = IVORY if light else CHARCOAL
    svg = (f'<rect width="800" height="800" fill="{IVORY if light else "url(#key)"}"/>'
           f'<rect width="800" height="800" filter="url(#grain)" opacity="{0.05 if light else 0.10}"/>'
           + f'<g transform="translate(-22,22)">{monogram(light, bg)}</g>')
    return page(800, 800, svg)


def watermark() -> str:
    # 150px on transparent: the monogram on a soft charcoal disc so it holds on any frame
    svg = (f'<circle cx="75" cy="75" r="73" fill="{CHARCOAL}" fill-opacity="0.78"/>'
           f'<g transform="translate(75,75) scale({138 / 800}) translate(-400,-400)">{monogram(False, CHARCOAL)}</g>')
    return page(150, 150, svg, bg="transparent")


# ---------------------------------------------------------------- banner
# YouTube: 2560x1440 image; TV shows all of it, desktop the 2560x423 middle
# band, phones only the centred 1546x423 safe area (x 507-2053, y 508-931).
SAFE = (507, 508, 2053, 931)


def banner() -> str:
    W, H = 2560, 1440
    gold_pts = [(-40, 1075), (180, 1060), (380, 1082), (600, 1040), (820, 1058), (1040, 1016),
                (1240, 1030), (1440, 1000), (1600, 990), (1720, 940), (1810, 850), (1880, 760), (1930, 690),
                (1966, 640)]
    ivory_pts = [(-40, 955), (260, 972), (520, 948), (780, 975), (1040, 952), (1300, 978),
                 (1560, 958), (1820, 984), (2080, 962), (2340, 985), (2600, 966)]
    gold = smooth(gold_pts)
    ivory = smooth(ivory_pts)
    ex, ey = gold_pts[-1]
    # dashed projection beyond "now", for the wide desktop/TV crop
    proj = smooth([(ex, ey), (2060, 600), (2240, 572), (2420, 548), (2620, 530)])

    grid = "".join(f'<line x1="0" x2="{W}" y1="{y}" y2="{y}" stroke="{IVORY}" stroke-opacity="0.05" stroke-width="2"/>'
                   for y in range(420, 1180, 110))
    years = "".join(
        f'<line x1="{x}" x2="{x}" y1="1150" y2="1166" stroke="{IVORY}" stroke-opacity="0.25" stroke-width="2"/>'
        f'<text x="{x}" y="1200" text-anchor="middle" class="sans" font-weight="600" font-size="22" '
        f'letter-spacing="3" fill="{IVORY}" fill-opacity="0.28">{yr}</text>'
        for x, yr in ((300, 1960), (860, 1980), (1420, 2000), (1966, 2025)))

    L = 600  # left text column
    svg = f"""
<radialGradient id="bkey" cx="0.40" cy="0.50" r="0.55">
  <stop offset="0" stop-color="#2B241A"/><stop offset="0.6" stop-color="#16171A"/><stop offset="1" stop-color="{CHARCOAL}"/>
</radialGradient>
<rect width="{W}" height="{H}" fill="url(#bkey)"/>
<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.07"/>
{grid}
<line x1="0" x2="{W}" y1="1150" y2="1150" stroke="{IVORY}" stroke-opacity="0.18" stroke-width="2"/>
{years}
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path d="{ivory}" stroke="{IVORY}" stroke-opacity="0.38" stroke-width="7"/>
  <path d="{gold}" stroke="{CHARCOAL}" stroke-width="22"/>
  <path d="{gold}" stroke="url(#goldline)" stroke-width="9"/>
  <path d="{proj}" stroke="{GOLD}" stroke-opacity="0.45" stroke-width="5" stroke-dasharray="2 16"/>
  <circle cx="{ex}" cy="{ey}" r="38" stroke="{GOLD}" stroke-width="4"/>
</g>
<circle cx="{ex}" cy="{ey}" r="13" fill="{GOLD_HI}"/>
<!-- left column -->
<text x="{L + 2}" y="580" class="sans" font-weight="700" font-size="27" letter-spacing="6" fill="{GOLD}">SHORTS EVERY DAY · DOCUMENTARIES EVERY WEEK</text>
<text x="{L - 8}" y="752" class="serif" font-weight="600" font-size="164" letter-spacing="-2" fill="{IVORY}">Data in Motion</text>
<text x="{L}" y="836" class="serif" font-style="italic" font-weight="400" font-size="60" fill="{IVORY}" fill-opacity="0.82">The world's numbers, told as stories.</text>
<text x="{L}" y="906" class="sans" font-weight="600" font-size="26" letter-spacing="6" fill="{IVORY}" fill-opacity="0.55">WORLD · ECONOMIES · INDIA · AI · SPORTS · MATH</text>
"""
    return page(W, H, svg)


# ---------------------------------------------------------------- render
def shoot(html: str, out: Path, w: int, h: int, transparent: bool = False) -> None:
    chrome = next((c for c in CHROME if Path(c).exists()), None)
    if not chrome:
        sys.exit("Chrome/Edge not found")
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "page.html"
        src.write_text(html, encoding="utf-8")
        args = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", f"--window-size={w},{h}",
                "--virtual-time-budget=10000", f"--user-data-dir={td}/prof",
                f"--screenshot={out}", src.as_uri()]
        if transparent:
            args.insert(2, "--default-background-color=00000000")
        subprocess.run(args, check=True, capture_output=True, timeout=120)
    print("wrote", out.relative_to(ROOT))


def main() -> None:
    shoot(avatar("light"), BRAND / "channel_avatar_v4.png", 800, 800)
    shoot(avatar("dark"), BRAND / "channel_avatar_v4_dark.png", 800, 800)
    shoot(banner(), BRAND / "channel_banner_v4.png", 2560, 1440)
    shoot(watermark(), BRAND / "watermark_v4.png", 150, 150, transparent=True)


if __name__ == "__main__":
    main()
