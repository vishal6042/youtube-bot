"""Shared building blocks for the newer Math in Motion episodes (from ep 5 on).

What's here:
- type: an editorial serif for the hook, a heavy sans for numbers (Georgia and
  Segoe UI, both on Windows; DejaVu if missing);
- a warm backdrop instead of flat black (charcoal with soft light behind the board);
- the animated hook title: words rise into place one by one, key words in gold;
- word-timed captions for the voice-over (same as the pi episode);
- small drawing helpers (additive paste, multi-coloured text, rings).

The hook rule for every episode: the first frame already shows the finished,
most beautiful image with the question over it, spoken aloud. Then the scene
rewinds and builds back up, so the payoff is earned.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import canvas as cv
from . import voice
from .canvas import GOLD, WHITE, H, W, mix, scale

_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


@lru_cache(maxsize=64)
def _ttf(names: tuple[str, ...], size: int, fallback_bold: bool) -> ImageFont.FreeTypeFont:
    for n in names:
        p = os.path.join(_WIN, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return cv.font(size, fallback_bold)


def serif(size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Editorial serif for hooks and payoff headlines."""
    return _ttf(("georgiaz.ttf",) if italic else ("georgiab.ttf",), size, True)


def serif_figures(size: int) -> ImageFont.FreeTypeFont:
    """Serif with full-height (lining) numbers: Georgia's old-style 137.5 looks small."""
    return _ttf(("cambriab.ttf", "georgiab.ttf"), size, True)


def sans(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    """Clean sans: 'regular', 'semi', 'bold' or 'black' (big numbers)."""
    files = {"regular": ("segoeui.ttf",), "semi": ("seguisb.ttf", "segoeuib.ttf"),
             "bold": ("segoeuib.ttf",), "black": ("seguibl.ttf", "segoeuib.ttf")}[weight]
    return _ttf(files, size, weight != "regular")


# --------------------------------------------------------------------------- #
# Layout shared by the new episodes (1080 x 1920)
# --------------------------------------------------------------------------- #
HOOK_Y = (178, 262)        # the two hook lines
CAP_Y = 362                # captions sit under the hook
INK = (12, 13, 20)         # backdrop base: deep charcoal, a touch blue


def backdrop(cx: float = W / 2, cy: float = 880, warm=(70, 48, 22), rad: float = 820,
             cool=(16, 22, 40)) -> Image.Image:
    """Charcoal with warm light pooled behind the board and a soft vignette.
    Dark, but not black: the frame reads as lit, not empty."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot(xx - cx, (yy - cy) * 0.82) / rad
    warm_a = np.exp(-d * d * 1.6)[..., None]
    top = np.clip(1 - yy / (H * 0.55), 0, 1)[..., None] ** 2          # cool light from the top
    vig = (1 - 0.55 * np.clip(np.hypot((xx - W / 2) / W, (yy - H / 2) / H) * 1.6 - 0.35, 0, 1) ** 1.5)[..., None]
    img = (np.array(INK, np.float32) + np.array(warm, np.float32) * warm_a * 0.55
           + np.array(cool, np.float32) * top * 0.6) * vig
    # A whisper of grain so the gradient never bands on YouTube's encoder.
    rng = np.random.default_rng(3)
    img += rng.normal(0, 1.1, img.shape[:2])[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def add(img: Image.Image, box, arr: np.ndarray) -> None:
    """Additively blend a float RGB array onto img inside box (x0, y0, x1, y1)."""
    reg = np.asarray(img.crop(box), np.float32) + arr
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), box[:2])


def darken(img: Image.Image, box, amount: float, feather: float = 40) -> None:
    """Soft dark plate behind text that sits over a busy image (multiplicative)."""
    if amount <= 0:
        return
    x0, y0, x1, y1 = [int(v) for v in box]
    pad = int(feather * 2)
    bx = (max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad))
    m = Image.new("L", (bx[2] - bx[0], bx[3] - bx[1]), 0)
    ImageDraw.Draw(m).rounded_rectangle((x0 - bx[0], y0 - bx[1], x1 - bx[0], y1 - bx[1]),
                                        radius=feather, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(feather / 1.6))
    k = 1 - amount * np.asarray(m, np.float32)[..., None] / 255
    reg = np.asarray(img.crop(bx), np.float32) * k
    img.paste(Image.fromarray(reg.astype(np.uint8)), bx[:2])


def text_parts(img: Image.Image, cx: float, y: float, parts, fnt, glow: float = 0.0,
               blur: float = 8.0, left: float | None = None, dy: float = 0.0) -> None:
    """Multi-coloured text centred on cx (or from `left`), additive with a local glow.
    parts: [(text, rgb)], colours already faded by the caller."""
    widths = [fnt.getlength(s) for s, _ in parts]
    total = sum(widths)
    x0 = left if left is not None else cx - total / 2
    y = y + dy
    pad = int(blur * 3) + 6
    h = int(fnt.size * 1.6)
    box = (max(0, int(x0) - pad), max(0, int(y - h / 2) - pad),
           min(W, int(x0 + total) + pad), min(H, int(y + h / 2) + pad))
    layer = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = x0 - box[0]
    for (s, c), wdt in zip(parts, widths):
        if s:
            d.text((x, y - box[1]), s, font=fnt, fill=tuple(int(v) for v in c), anchor="lm")
        x += wdt
    arr = np.asarray(layer, np.float32)
    if glow:
        arr = arr + np.asarray(layer.filter(ImageFilter.GaussianBlur(blur)), np.float32) * glow
    add(img, box, arr)


def solid_text(img: Image.Image, cx: float, y: float, parts, fnt, alpha: float = 1.0,
               shadow: float = 0.7, left: float | None = None) -> None:
    """Opaque text (not additive) with a soft drop shadow: reads over bright images."""
    if alpha <= 0:
        return
    widths = [fnt.getlength(s) for s, _ in parts]
    total = sum(widths)
    x0 = left if left is not None else cx - total / 2
    pad = 30
    h = int(fnt.size * 1.7)
    box = (max(0, int(x0) - pad), max(0, int(y - h / 2) - pad),
           min(W, int(x0 + total) + pad), min(H, int(y + h / 2) + pad))
    bw, bh = box[2] - box[0], box[3] - box[1]
    mask = Image.new("L", (bw, bh), 0)
    col = Image.new("RGB", (bw, bh), (0, 0, 0))
    dm, dc = ImageDraw.Draw(mask), ImageDraw.Draw(col)
    x = x0 - box[0]
    for (s, c), wdt in zip(parts, widths):
        if s:
            dm.text((x, y - box[1]), s, font=fnt, fill=255, anchor="lm")
            dc.text((x, y - box[1]), s, font=fnt, fill=tuple(int(v) for v in c), anchor="lm")
        x += wdt
    reg = np.asarray(img.crop(box), np.float32)
    if shadow:
        sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(7)), np.float32)[..., None] / 255
        sh = np.roll(sh, 3, axis=0)
        reg = reg * (1 - shadow * alpha * np.clip(sh * 1.4, 0, 1))
    m = np.asarray(mask, np.float32)[..., None] / 255 * alpha
    reg = reg * (1 - m) + np.asarray(col, np.float32) * m
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), box[:2])


# --------------------------------------------------------------------------- #
# The hook
# --------------------------------------------------------------------------- #
def hook(img: Image.Image, lines, t: float, t0: float = 0.12, size: int = 70,
         stagger: float = 0.075, rise: float = 26, dur: float = 0.42, ys=HOOK_Y,
         alpha: float = 1.0) -> None:
    """The episode's question, words rising into place one by one.

    lines: [[(word, colour), ...], ...] (one inner list per line; a word's
    trailing space is added here). Gold the one or two words that matter."""
    fnt, fig = serif(size), serif_figures(round(size * 1.04))
    k = 0
    for line, y in zip(lines, ys):
        words = [(w + (" " if i < len(line) - 1 else ""), c) for i, (w, c) in enumerate(line)]
        fonts = [fig if any(ch.isdigit() for ch in w) else fnt for w, _ in words]
        widths = [f.getlength(w) for (w, _), f in zip(words, fonts)]
        x = W / 2 - sum(widths) / 2
        for (w, c), wd, f in zip(words, widths, fonts):
            u = cv.ease_out((t - t0 - k * stagger) / dur)
            if u > 0:
                solid_text(img, 0, y + rise * (1 - u), [(w, c)], f, alpha=u * alpha,
                           shadow=0.75, left=x)
            x += wd
            k += 1


def hook_done(lines, t0: float = 0.12, stagger: float = 0.075, dur: float = 0.42) -> float:
    """When the last word of the hook has settled."""
    return t0 + (sum(len(l) for l in lines) - 1) * stagger + dur


# --------------------------------------------------------------------------- #
# Captions (voice-over, timed to the words)
# --------------------------------------------------------------------------- #
def captions(at: float, line: voice.Line, chunks) -> list[tuple[float, float, str, bool]]:
    """(start, end, text, is_last) for each caption chunk of a spoken line.
    chunks: [(text shown, number of spoken words it covers)]."""
    counts = [c for _, c in chunks]
    if len(line.words) == sum(counts):
        starts = [float(line.words[sum(counts[:i])]["start"]) for i in range(len(chunks))]
        last = float(line.words[-1]["end"])
    else:
        starts = [line.secs * sum(counts[:i]) / sum(counts) for i in range(len(chunks))]
        last = line.secs
    ends = starts[1:] + [last + 0.35]
    n = len(chunks)
    return [(at + s, at + e, txt, i == n - 1)
            for i, (s, e, (txt, _)) in enumerate(zip(starts, ends, chunks))]


def caption_parts(text: str, f: float, gold: str = "0123456789°π×/%"):
    """Numbers and symbols in gold, the rest white, faded by f. Wrap a phrase in
    *stars* to gold it too."""
    parts: list[tuple[str, tuple]] = []
    hot = False
    for ch in text:
        if ch == "*":
            hot = not hot
            continue
        col = GOLD if (hot or ch in gold) else WHITE
        if parts and parts[-1][1] == col:
            parts[-1] = (parts[-1][0] + ch, col)
        else:
            parts.append((ch, col))
    return [(s, scale(c, f)) for s, c in parts]


def draw_captions(img: Image.Image, caps, t: float, y: float = CAP_Y, size: int = 48) -> None:
    fnt = sans(size, "bold")
    for c0, c1, txt, last in caps:
        if c0 <= t < c1 + (0.2 if last else 0):
            f = cv.ease((t - c0) / 0.1)
            if last:
                f = min(f, cv.ease((c1 + 0.2 - t) / 0.2))
            parts = [(s, c) for s, c in caption_parts(txt, 1.0)]
            solid_text(img, W / 2, y, parts, fnt, alpha=f, shadow=0.8)
            return


VOICE = "en-GB-SoniaNeural"     # British Sonia, as in the pi episode and long-form
RATE = "+10%"                   # a touch quicker than long-form: Shorts pace


def spoken(script, ffmpeg: str, voice_name: str = VOICE, rate: str = RATE):
    """script: {name: (text, chunks)} -> {name: Line}."""
    return {k: voice.say(v[0], ffmpeg, voice=voice_name, rate=rate) for k, v in script.items()}


# --------------------------------------------------------------------------- #
# Small sprites
# --------------------------------------------------------------------------- #
def ring(radius: float, color, alpha: float, width: float = 2.0) -> Image.Image:
    ss = 4
    size = int(math.ceil(radius + width + 3)) * 2 + 1
    big = Image.new("L", (size * ss, size * ss), 0)
    c = size * ss / 2
    r = radius * ss
    ImageDraw.Draw(big).ellipse((c - r, c - r, c + r, c + r), outline=255, width=max(1, int(width * ss)))
    a = np.asarray(big.resize((size, size), Image.LANCZOS), np.float32) / 255 * alpha
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def glow_of(sharp: np.ndarray, blur: float, gain: float) -> np.ndarray:
    """sharp (float RGB on black) + its blurred copy: soft light, not neon tubes."""
    im = Image.fromarray(np.clip(sharp, 0, 255).astype(np.uint8))
    return sharp + np.asarray(im.filter(ImageFilter.GaussianBlur(blur)), np.float32) * gain


def flash(t: float, at: float, width: float = 0.45) -> float:
    """A soft pulse 0..1..0 centred on `at`."""
    return math.exp(-((t - at) / width) ** 2)


def lerp(a, b, f):
    return a + (b - a) * f


def mixc(a, b, f):
    return mix(a, b, max(0.0, min(1.0, f)))


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def workers() -> int:
    """How many processes draw frames at once (env MIM_WORKERS overrides)."""
    env = os.environ.get("MIM_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(16, (os.cpu_count() or 2) - 4))


def encode(out_path, ffmpeg: str, total: float, frame, sound, fps: int = 60, progress=None,
           module: str | None = None, build_kw: dict | None = None) -> float:
    """Draw every frame, make the sound with sound(wav), mux. Returns seconds.

    With `module` (the sim's module name, whose build(ffmpeg, **build_kw) gives
    the same frames), the frames are split into contiguous slices drawn by
    separate processes at once, one video piece each, then joined without
    re-encoding. Without it (or with one worker) frames are drawn here, in order."""
    import tempfile
    from pathlib import Path

    n_frames = int(total * fps)
    n_work = workers() if module else 1
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        silent = tmp / "video.mp4"
        if n_work <= 1:
            _encode_serial(silent, ffmpeg, n_frames, frame, fps, progress)
            sound(tmp / "sound.wav")
        else:
            _encode_parallel(silent, ffmpeg, n_frames, fps, progress, module, build_kw or {}, n_work, tmp,
                             lambda: sound(tmp / "sound.wav"))
        cv.mux(silent, tmp / "sound.wav", Path(out_path), ffmpeg)
    return total


def _encode_serial(silent, ffmpeg, n_frames, frame, fps, progress) -> None:
    enc = cv.Encoder(silent, ffmpeg, fps=fps)
    try:
        for fi in range(n_frames):
            enc.write(np.asarray(frame(fi / fps)))
            if progress and fi % 60 == 0:
                progress(fi, n_frames)
    except BaseException:
        # Stop ffmpeg first, or Windows keeps the temp file locked and the
        # clean-up error hides the real one.
        enc.proc.kill()
        enc.proc.wait()
        raise
    enc.close()


def _encode_parallel(silent, ffmpeg, n_frames, fps, progress, module, build_kw, n_work, tmp, make_sound) -> None:
    import json
    import subprocess
    import sys
    import threading

    edges = np.linspace(0, n_frames, n_work + 1).astype(int)
    env = dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    done = [0] * n_work
    procs, parts, errs = [], [], []
    for w in range(n_work):
        part = tmp / f"part{w:02d}.mp4"
        parts.append(part)
        p = subprocess.Popen([sys.executable, "-m", "graph_bot.sims._chunk", module, str(edges[w]),
                              str(edges[w + 1]), str(fps), str(part), ffmpeg, json.dumps(build_kw)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        procs.append(p)

    def read(w, p):
        for line in p.stdout:
            if line.startswith("p "):
                done[w] = int(line.split()[1])
    readers = [threading.Thread(target=read, args=(w, p), daemon=True) for w, p in enumerate(procs)]
    for r in readers:
        r.start()
    try:
        make_sound()                               # the sound is built while the frames draw
        while any(p.poll() is None for p in procs):
            if progress:
                progress(sum(done), n_frames)
            if any(p.poll() not in (None, 0) for p in procs):
                break
            threading.Event().wait(0.5)
        for w, p in enumerate(procs):
            if p.wait() != 0:
                errs.append(f"slice {w}: " + (p.stderr.read() or "")[-1500:])
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
    if errs:
        raise RuntimeError("Frame workers failed:\n" + "\n".join(errs))
    if progress:
        progress(n_frames, n_frames)
    lst = tmp / "parts.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(silent)], check=True)


def contact_sheet(frames, path, cols: int = 4, width: int = 360) -> None:
    """Save (label, Image) pairs as one labelled grid (for checking stills by eye)."""
    ims = [im.resize((width, int(im.height * width / im.width)), Image.LANCZOS) for _, im in frames]
    h = ims[0].height + 28
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * h), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, ((lab, _), im) in enumerate(zip(frames, ims)):
        x, y = (i % cols) * width, (i // cols) * h
        sheet.paste(im, (x, y + 28))
        d.text((x + 6, y + 6), str(lab), fill=(255, 255, 255), font=cv.font(16))
    sheet.save(path)
