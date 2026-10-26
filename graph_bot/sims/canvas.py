"""Neon drawing and video encoding for simulated Shorts.

A frame is two layers: a sharp full-size layer and a quarter-size glow layer.
The glow layer is blurred and scaled up, then added on top, which gives the
soft neon halo cheaply (blurring a full 1080x1920 frame every frame is slow).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
GLOW_SCALE = 4
BG = (5, 7, 15)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: tuple[int, int, int], b: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(int(round(x + (y - x) * f)) for x, y in zip(a, b))


def scale(c: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(x * f))) for x in c)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    import matplotlib

    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(matplotlib.get_data_path(), "fonts", "ttf", name), size)


class Frame:
    """One frame: draw sharp shapes on `sharp`, halos on `glow` (same coordinates)."""

    def __init__(self, base: Image.Image | None = None, glow_base: Image.Image | None = None):
        self.img = base.copy() if base is not None else Image.new("RGB", (W, H), BG)
        self.glow_img = (glow_base.copy() if glow_base is not None
                         else Image.new("RGB", (W // GLOW_SCALE, H // GLOW_SCALE), (0, 0, 0)))
        self.sharp = ImageDraw.Draw(self.img)
        self._glow = ImageDraw.Draw(self.glow_img)

    def dot(self, x: float, y: float, r: float, color, glow: float = 0.0, glow_r: float | None = None):
        self.sharp.ellipse((x - r, y - r, x + r, y + r), fill=color)
        if glow > 0:
            self.halo(x, y, glow_r or r * 2.2, scale(color, glow))

    def halo(self, x: float, y: float, r: float, color):
        s = GLOW_SCALE
        self._glow.ellipse(((x - r) / s, (y - r) / s, (x + r) / s, (y + r) / s), fill=color)

    def line(self, pts, color, width: int, glow: float = 0.0):
        self.sharp.line(pts, fill=color, width=width, joint="curve")
        if glow > 0:
            s = GLOW_SCALE
            self._glow.line([(x / s, y / s) for x, y in pts], fill=scale(color, glow),
                            width=max(1, round(width * 2.5 / s)), joint="curve")

    def text(self, x: float, y: float, s: str, fnt, color, anchor: str = "mm", glow: float = 0.0):
        self.sharp.text((x, y), s, font=fnt, fill=color, anchor=anchor)
        if glow > 0:
            g = GLOW_SCALE
            small = font(max(8, round(fnt.size / g)))
            self._glow.text((x / g, y / g), s, font=small, fill=scale(color, glow), anchor=anchor)

    def compose(self, blur: float = 3.0, gain: float = 1.6) -> np.ndarray:
        halo = self.glow_img.filter(ImageFilter.GaussianBlur(blur)).resize((W, H), Image.BILINEAR)
        out = np.asarray(self.img, dtype=np.uint16) + (np.asarray(halo, dtype=np.float32) * gain).astype(np.uint16)
        return np.minimum(out, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# The series look: shared by every episode so they read as one series.
# --------------------------------------------------------------------------- #
CYAN, PINK, GOLD = hex_rgb("#4cc9f0"), hex_rgb("#ff5d8f"), hex_rgb("#ffd166")
WHITE, MUTED = (242, 245, 250), hex_rgb("#8f9bb3")
TITLE_Y, LINE_Y, SUB_Y = 170, 262, 322   # title, counter/payoff line, payoff subline
SAFE_BOTTOM = 1540                        # YouTube's title/channel overlay starts below
SAFE_RIGHT = 920                          # like/comment buttons sit right of this (lower half)


def sphere(color, r: float, ox: float, oy: float, size: int, ss: int = 8) -> Image.Image:
    """A glossy marble, drawn 8x large and shrunk (smooth edges at any sub-pixel offset)."""
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    cx, cy = (size / 2 + ox) * ss, (size / 2 + oy) * ss
    hx, hy = cx - 0.38 * r * ss, cy - 0.42 * r * ss
    steps = 14
    for s in range(steps):
        f = s / (steps - 1)                       # 0 rim .. 1 highlight
        rr = r * ss * (1 - 0.86 * f)
        x, y = cx + (hx - cx) * f, cy + (hy - cy) * f
        col = (mix(scale(color, 0.45), color, f / 0.55) if f < 0.55
               else mix(color, WHITE, (f - 0.55) / 0.45 * 0.8))
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col + (255,))
    return big.resize((size, size), Image.LANCZOS)


class Sprites:
    """Marble images for each colour at 4x4 sub-pixel offsets, pasted centred on (x, y)."""

    def __init__(self, colors, r: float, sub: int = 4):
        self.sub = sub
        self.r = r
        self.size = int(np.ceil(r * 2 + 4)) // 2 * 2 + 2
        self.cache = {c: {(i, k): sphere(c, r, i / sub, k / sub, self.size)
                          for i in range(sub) for k in range(sub)} for c in set(colors)}

    def add(self, color) -> None:
        if color not in self.cache:
            self.cache[color] = {(i, k): sphere(color, self.r, i / self.sub, k / self.sub, self.size)
                                 for i in range(self.sub) for k in range(self.sub)}

    def paste(self, img: Image.Image, color, x: float, y: float) -> None:
        fx, fy = int(np.floor(x)), int(np.floor(y))
        spr = self.cache[color][(int((x - fx) * self.sub), int((y - fy) * self.sub))]
        img.paste(spr, (fx - self.size // 2, fy - self.size // 2), spr)


def halo_sprite(radius: int, color, alpha: float, core: float = 0.0) -> Image.Image:
    """Soft round glow as an RGBA sprite; `core` px around the centre stay at full alpha."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size] - radius
    a = np.exp(-(xx ** 2 + yy ** 2) / (2 * (radius / 2.6) ** 2)) * alpha
    if core:
        a = np.where(np.hypot(xx, yy) <= core + 0.5, np.maximum(a, alpha), a)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


class Big:
    """Draw neon line-work 3x large (smooth antialiasing once shrunk)."""

    def __init__(self, ss: int = 3):
        self.ss = ss
        self.img = Image.new("RGB", (W * ss, H * ss), (0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def line(self, pts, col, w: float) -> None:
        s = self.ss
        self.d.line([(x * s, y * s) for x, y in pts], fill=col, width=max(1, int(w * s)), joint="curve")

    def circle(self, x: float, y: float, r: float, outline=None, fill=None, w: float = 2) -> None:
        s = self.ss
        self.d.ellipse((x * s - r * s, y * s - r * s, x * s + r * s, y * s + r * s),
                       outline=outline, fill=fill, width=max(1, int(w * s)))

    def rrect(self, box, radius: float, outline=None, fill=None, w: float = 2) -> None:
        s = self.ss
        self.d.rounded_rectangle([v * s for v in box], radius=radius * s, outline=outline,
                                 fill=fill, width=max(1, int(w * s)))

    def text(self, x: float, y: float, s: str, size: int, col, anchor: str = "mm", bold: bool = True) -> None:
        self.d.text((x * self.ss, y * self.ss), s, font=font(size * self.ss, bold), fill=col, anchor=anchor)

    def shrink(self) -> Image.Image:
        return self.img.resize((W, H), Image.LANCZOS)


def neon(sharp: Image.Image, blur: float = 9, gain: float = 1.8, bg=BG) -> Image.Image:
    """Line-work on black -> the same lines on the background with a soft neon glow."""
    glow = sharp.filter(ImageFilter.GaussianBlur(blur))
    arr = np.asarray(sharp, np.float32) + np.asarray(glow, np.float32) * gain + np.array(bg, np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def glow_text(img: Image.Image, x: float, y: float, s: str, fnt, color, glow: float = 0.5,
              blur: float = 10, anchor: str = "mm") -> Image.Image:
    """Text with a faint halo, composited additively (returns a new image)."""
    layer = Image.new("RGB", img.size, (0, 0, 0))
    ImageDraw.Draw(layer).text((x, y), s, font=fnt, fill=color, anchor=anchor)
    arr = np.asarray(img, np.float32) + np.asarray(layer, np.float32)
    if glow:
        arr += np.asarray(layer.filter(ImageFilter.GaussianBlur(blur)), np.float32) * glow
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def title(img: Image.Image, text: str) -> Image.Image:
    """The episode's hook question, top centre, the same on every episode."""
    return glow_text(img, W / 2, TITLE_Y, text, font(58), WHITE)


def ease(u: float) -> float:
    """Smooth 0..1 (ease in-out), clamped."""
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ease_out(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def add_rgba(img: Image.Image, spr: Image.Image, x: float, y: float) -> None:
    """Paste an RGBA sprite centred on (x, y)."""
    img.paste(spr, (int(round(x - spr.width / 2)), int(round(y - spr.height / 2))), spr)


class Encoder:
    """Pipe raw RGB frames straight into ffmpeg (no frames on disk)."""

    def __init__(self, path: Path, ffmpeg: str, fps: int = FPS):
        self.path = Path(path)
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
             str(self.path)],
            stdin=subprocess.PIPE,
        )

    def write(self, rgb: np.ndarray) -> None:
        self.proc.stdin.write(rgb.tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {self.path}")


def mux(video: Path, audio: Path, out: Path, ffmpeg: str) -> None:
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
                   check=True)
