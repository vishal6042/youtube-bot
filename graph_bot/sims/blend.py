"""Blender-rendered sims: the 3D picture comes from Blender (Cycles on the GPU),
the text, counters and sound from Python.

How an episode uses this:
1. the sim builds its plan (voice timings, random draws, camera keys) and a
   `job` dict that holds everything the Blender scene needs;
2. `render_frames` runs Blender headless on the episode's scene script
   (scripts/blender/<name>.py) and writes one PNG per video frame into a cache
   folder named by a hash of the job and the scripts, so a re-render with
   nothing changed costs nothing and a changed plan never reuses old frames;
3. the sim's frame(t) loads that PNG, grades it and draws the text on top.

The scene script is called as
    blender -b --factory-startup -P <script> -- <job.json> <out_dir> <frame list file>
and prints "FRAME <n>" after writing <out_dir>/<n:05d>.png.

Also here: the 1440-wide text helpers (sprites with soft shadows, sub-pixel
blits), the grade, and small sound helpers, so these episodes don't import the
GPU ocean module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import PROJECT_ROOT
from . import sound as snd

OUT_W, OUT_H = 1440, 2560
K = OUT_W / 1080.0                    # sizes below are given for a 1080-wide frame
FPS = 60
CACHE = PROJECT_ROOT / "data" / "cache" / "blender"
SCRIPTS = PROJECT_ROOT / "scripts" / "blender"


def px(v: float) -> int:
    return int(round(v * K))


def find_blender() -> str:
    cands = [os.environ.get("BLENDER", "")]
    cands += [str(p) for p in sorted(Path("E:/tools/blender").glob("blender-*/blender.exe"), reverse=True)]
    cands += [shutil.which("blender") or ""]
    for c in cands:
        if c and Path(c).exists():
            return c
    raise RuntimeError("Blender not found: set BLENDER to blender.exe")


# --------------------------------------------------------------------------- #
# Rendering the 3D layer
# --------------------------------------------------------------------------- #
def job_dir(name: str, job: dict, extra_files=()) -> Path:
    """The cache folder for this exact job (and versions of the scripts it runs)."""
    h = hashlib.sha1(json.dumps(job, sort_keys=True, default=float).encode())
    for f in [SCRIPTS / f"{name}.py", *extra_files]:
        h.update(Path(f).read_bytes())
    return CACHE / name / h.hexdigest()[:14]


def render_frames(name: str, job: dict, frames: list[int], extra_files=(), progress=None,
                  procs: int = 2, sample: dict | None = None) -> Path:
    """Render the listed frame numbers with scripts/blender/<name>.py; returns the folder.

    Frames already in the cache are skipped. `procs` Blender processes share the
    one GPU (while one syncs the scene on the CPU, the other keeps the GPU busy).
    `sample` (optional) overrides job settings, e.g. {"samples": 16} for quick looks;
    those frames go to their own folder."""
    if sample:
        job = dict(job, **sample)
    out = job_dir(name, job, extra_files)
    out.mkdir(parents=True, exist_ok=True)
    (out / "job.json").write_text(json.dumps(job, default=float), encoding="utf-8")
    todo = [f for f in frames if not (out / f"{f:05d}.png").exists()]
    total = len(frames)
    done = [total - len(todo)]
    if progress:
        progress(done[0], total)
    if not todo:
        return out
    procs = max(1, min(procs, len(todo)))
    chunks = [todo[i * len(todo) // procs:(i + 1) * len(todo) // procs] for i in range(procs)]
    blender = find_blender()
    lock = threading.Lock()
    errors: list[str] = []

    def run(i: int, chunk: list[int]) -> None:
        lst = out / f"todo_{i}.txt"
        lst.write_text(" ".join(map(str, chunk)), encoding="utf-8")
        cmd = [blender, "-b", "--factory-startup", "-noaudio", "-P", str(SCRIPTS / f"{name}.py"), "--",
               str(out / "job.json"), str(out), str(lst)]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        tail: list[str] = []
        for line in p.stdout:
            if line.startswith("FRAME "):
                with lock:
                    done[0] += 1
                    if progress:
                        progress(done[0], total)
            else:
                tail = (tail + [line.rstrip()])[-40:]
        if p.wait() != 0:
            errors.append(f"Blender ({name}, part {i}) failed:\n" + "\n".join(tail))

    threads = [threading.Thread(target=run, args=(i, c), daemon=True) for i, c in enumerate(chunks)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise RuntimeError("\n\n".join(errors))
    missing = [f for f in frames if not (out / f"{f:05d}.png").exists()]
    if missing:
        raise RuntimeError(f"Blender ({name}) left {len(missing)} frames unrendered, e.g. {missing[:5]}")
    return out


def load_frame(folder: Path, fi: int) -> np.ndarray:
    return np.asarray(Image.open(folder / f"{fi:05d}.png").convert("RGB"), np.float32)


def split_progress(progress, share: float):
    """Two progress callbacks: the Blender part fills `share` of the bar, encoding the rest."""
    if progress is None:
        return None, None
    return (lambda d, n: progress(int(1000 * share * d / max(1, n)), 1000),
            lambda d, n: progress(int(1000 * (share + (1 - share) * d / max(1, n))), 1000))


# --------------------------------------------------------------------------- #
# Grade and text at the output size
# --------------------------------------------------------------------------- #
_DITHER = None


def grade(arr: np.ndarray, sharp: float = 0.45, contrast: float = 1.06, pivot: float = 60.0) -> np.ndarray:
    """A light unsharp mask for crisp detail and a touch more contrast."""
    from scipy.ndimage import gaussian_filter

    out = arr + sharp * (arr - gaussian_filter(arr, (1.2 * K, 1.2 * K, 0)))
    return np.clip(pivot + (out - pivot) * contrast, 0, 255)


def to_image(arr: np.ndarray) -> Image.Image:
    global _DITHER
    if _DITHER is None or _DITHER.shape[:2] != arr.shape[:2]:
        _DITHER = (np.random.default_rng(99).random((arr.shape[0], arr.shape[1], 1), np.float32) - 0.5) * 1.4
    return Image.fromarray(np.clip(arr + _DITHER, 0, 255).astype(np.uint8))


def shade_top(arr: np.ndarray, y0: float, y1: float, amount: float) -> np.ndarray:
    """Darken the frame above y1 (fully below y0..y1 ramp) so text over it reads."""
    h = arr.shape[0]
    y = np.arange(h, dtype=np.float32)[:, None, None]
    u = np.clip((y1 - y) / max(1.0, y1 - y0), 0, 1)
    return arr * (1 - amount * u * u * (3 - 2 * u))


def blit(img: Image.Image, rgba: Image.Image, x: float, y: float, alpha: float = 1.0) -> None:
    """Paste an RGBA sprite with its top-left at float (x, y): text never snaps to whole pixels."""
    if alpha <= 0.004:
        return
    tw, th = rgba.size[0] + 2, rgba.size[1] + 2
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    x0, y0 = max(0, ix), max(0, iy)
    x1, y1 = min(img.size[0], ix + tw), min(img.size[1], iy + th)
    if x1 <= x0 or y1 <= y0:
        return
    t = rgba.transform((tw, th), Image.AFFINE, (1, 0, -fx, 0, 1, -fy), resample=Image.BICUBIC)
    a = np.asarray(t, np.float32)[y0 - iy:y1 - iy, x0 - ix:x1 - ix]
    m = a[..., 3:4] / 255 * alpha
    reg = np.asarray(img.crop((x0, y0, x1, y1)), np.float32)
    img.paste(Image.fromarray(np.clip(reg * (1 - m) + a[..., :3] * m, 0, 255).astype(np.uint8)), (x0, y0))


def blit_center(img: Image.Image, rgba: Image.Image, cx: float, cy: float, alpha: float = 1.0) -> None:
    blit(img, rgba, cx - rgba.size[0] / 2, cy - rgba.size[1] / 2, alpha)


def row_sprite(parts, font, shadow: float = 0.85) -> Image.Image:
    """One line of text in several colours, with a soft shadow. parts: [(text, colour)] or
    [(text, colour, font)] to mix fonts on one line."""
    pad = px(22)
    parts = [p if len(p) == 3 else (p[0], p[1], font) for p in parts]
    widths = [f.getlength(t) for t, _, f in parts]
    hmax = max(f.size for _, _, f in parts)
    wd, hd = int(sum(widths)) + pad * 2, int(hmax * 1.3) + pad * 2
    mask = Image.new("L", (wd, hd), 0)
    colr = Image.new("RGB", (wd, hd), (0, 0, 0))
    dm, dc = ImageDraw.Draw(mask), ImageDraw.Draw(colr)
    x = float(pad)
    for (t, c, f), w_ in zip(parts, widths):
        dm.text((x, hd / 2), t, font=f, fill=255, anchor="lm")
        dc.rectangle((x - 1, 0, x + w_ + 1, hd), fill=tuple(int(v) for v in c))
        x += w_
    m = np.asarray(mask, np.float32) / 255
    sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(px(6))), np.float32) / 255
    sh = np.clip(np.roll(sh, px(3), axis=0) * 1.6, 0, 1) * shadow
    a = m + sh * (1 - m)
    rgb = np.asarray(colr, np.float32) * (m / np.maximum(a, 1e-4))[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8), "RGBA")


class Hook:
    """The hook question, words rising in one by one (kit.hook, at the output size)."""

    def __init__(self, lines, font, ys, t0: float = -0.45, stagger: float = 0.075, dur: float = 0.42):
        self.words = []
        self.t0, self.stagger, self.dur = t0, stagger, dur
        k = 0
        for line, y in zip(lines, ys):
            words = [(w + (" " if i < len(line) - 1 else ""), c) for i, (w, c) in enumerate(line)]
            widths = [font.getlength(w) for w, _ in words]
            x = OUT_W / 2 - sum(widths) / 2
            for (w, c), wd in zip(words, widths):
                spr = row_sprite([(w, c)], font)
                self.words.append((spr, x - px(22), y * K - spr.size[1] / 2, k))
                x += wd
                k += 1

    def draw(self, img: Image.Image, t: float, alpha: float = 1.0) -> None:
        for spr, x, y, k in self.words:
            u = min(1.0, max(0.0, (t - self.t0 - k * self.stagger) / self.dur))
            u = 1 - (1 - u) ** 3
            if u > 0:
                blit(img, spr, x, y + px(26) * (1 - u), u * alpha)


class Captions:
    """Word-timed captions (kit.captions), drawn as cached sprites."""

    def __init__(self, caps, font, y: float):
        from . import kit
        self.caps, self.y = caps, y
        self.sprites = {txt: row_sprite(kit.caption_parts(txt, 1.0), font) for _, _, txt, _ in caps}

    def draw(self, img: Image.Image, t: float) -> None:
        for c0, c1, txt, last in self.caps:
            if c0 <= t < c1 + (0.2 if last else 0):
                f = smooth((t - c0) / 0.1)
                if last:
                    f = min(f, smooth((c1 + 0.2 - t) / 0.2))
                spr = self.sprites[txt]
                blit(img, spr, OUT_W / 2 - spr.size[0] / 2, self.y * K - spr.size[1] / 2, f)
                return


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def smoother(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


# --------------------------------------------------------------------------- #
# Camera projection (matches a Blender camera aimed with to_track_quat('-Z', 'Y'),
# sensor fit AUTO, 36 mm sensor on the frame's long side)
# --------------------------------------------------------------------------- #
def project(pos, target, lens: float, pts) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pos, target = np.asarray(pos, float), np.asarray(target, float)
    f = target - pos
    f /= np.linalg.norm(f)
    r = np.cross(f, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = np.atleast_2d(np.asarray(pts, float)) - pos
    xc, yc, zc = d @ r, d @ u, d @ f
    s = lens / 18.0 * OUT_H / 2                      # pixels per unit of x/z at the long side
    zs = np.where(zc > 1e-6, zc, 1e-6)
    return OUT_W / 2 + s * xc / zs, OUT_H / 2 - s * yc / zs, zc


# --------------------------------------------------------------------------- #
# Sound helpers
# --------------------------------------------------------------------------- #
def noise(dur: float, seed: int, cutoff: float, high: bool = False) -> np.ndarray:
    from scipy.signal import butter, lfilter

    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, int(snd.SR * dur)).astype(np.float32)
    b, a = butter(2, cutoff / (snd.SR / 2), btype="high" if high else "low")
    y = lfilter(b, a, x).astype(np.float32)
    return y / (np.abs(y).max() + 1e-6)


def whoosh(dur: float, f0: float, f1: float, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(snd.SR * dur)) / snd.SR
    u = t / dur
    out = np.zeros_like(t)
    for _ in range(12):
        f = f0 * (f1 / f0) ** u * rng.uniform(0.8, 1.25)
        out += np.sin(2 * np.pi * np.cumsum(f) / snd.SR + rng.uniform(0, 6.3)) * rng.uniform(0.4, 1.0)
    return (out / 12 * np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6).astype(np.float32)


def pad(total: float, root: float = 55.0, gain: float = 1.0) -> np.ndarray:
    """A soft low drone that fades in and out: the bed under the voice."""
    t = np.arange(int(snd.SR * total)) / snd.SR
    p = (np.sin(2 * np.pi * root * t) + 0.5 * np.sin(2 * np.pi * root * 1.5 * t + 0.4)
         + 0.3 * np.sin(2 * np.pi * root * 2.006 * t + 1.1))
    return (p * np.clip(t / 2.0, 0, 1) * np.clip((total - t) / 1.5, 0, 1) / 1.8 * gain).astype(np.float32)
