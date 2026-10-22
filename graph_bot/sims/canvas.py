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
