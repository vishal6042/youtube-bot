"""Galton board: 500 marbles fall through 12 rows of pegs and pile into a bell curve.

Motion: marbles move under real gravity and bounce off each peg in a natural
arc. At every peg a fair coin decides left or right, and the bounce is sized so
the marble arcs onto a peg of the next row: exactly the "12 coin flips" a real
board approximates, so the piles follow the binomial (bell) curve honestly.
In the bins each marble settles into the next free place of a packed pile.

The whole run is simulated first; drawing and sound read that timeline, so
every peg flash and note lines up with a real bounce. 60 fps, no per-ball glow
(a crowd of halos flickers); the neon lives on the board, the marbles are glossy.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import canvas as cv
from . import sound as snd
from .canvas import H, W, hex_rgb, mix, scale

FPS = 60
SUB = 4                    # physics steps per frame
N_BALLS = 500
ROWS = 12
CX = 520                   # a little left of centre: YouTube's buttons sit on the right
DX, DY = 64, 46            # peg spacing
PEG_Y0 = 560
PEG_R, BALL_R = 5.0, 7.0
ENTRY_Y = 470              # mouth of the funnel
BIN_TOP = PEG_Y0 + (ROWS - 1) * DY + 40
FLOOR = 1520               # clear of YouTube's title and channel overlay
HALF = (ROWS + 1) / 2 * DX  # half-width of the bins

GRAVITY = 2200.0           # px/s^2: ~0.25 s per row, ~3 s top to bottom
BOUNCE = 0.18              # share of the falling speed returned upward at a peg
SPREAD = 0.05              # random variation in the sideways speed of a bounce
ROW_H = BALL_R * 2 * math.sin(math.pi / 3)   # packed pile row height
PER_ROW = 3.5              # average marbles per pile row (4 and 3 alternating)

FIRST = [0.9, 2.6, 4.2]    # the three solo marbles
STREAM = (5.6, 21.0)       # the rest, speeding up, between these times

TITLE = "Where will 500 balls land?"
PAYOFF = "Pure chance makes a bell curve"
PAYOFF_SUB = "Every bounce: left or right, 50/50"

BG = (5, 7, 15)
CYAN, PINK, GOLD = hex_rgb("#4cc9f0"), hex_rgb("#ff5d8f"), hex_rgb("#ffd166")
WHITE, MUTED = (242, 245, 250), hex_rgb("#8f9bb3")


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def _bin_x(b: int) -> float:
    return CX + (b - ROWS / 2) * DX


def _slots(b: int, count: int) -> list[tuple[float, float]]:
    """Packed pile in bin b: rows of 4 and 3 marbles, alternating."""
    out: list[tuple[float, float]] = []
    row = 0
    while len(out) < count:
        n = 4 if row % 2 == 0 else 3
        for c in range(n):
            out.append((_bin_x(b) + (c - (n - 1) / 2) * BALL_R * 2,
                        FLOOR - 3 - BALL_R - row * ROW_H))
        row += 1
    return out[:count]


def release_times(n_balls: int = N_BALLS) -> np.ndarray:
    n = n_balls - len(FIRST)
    u = np.arange(1, n + 1) / n
    return np.concatenate([FIRST, STREAM[0] + (STREAM[1] - STREAM[0]) * u ** (1 / 1.7)])


def peg_positions() -> np.ndarray:
    return np.array([(CX + (c - r / 2) * DX, PEG_Y0 + r * DY)
                     for r in range(ROWS) for c in range(r + 1)])


def simulate(seed: int = 7, n_balls: int = N_BALLS) -> dict:
    """Step the board until every marble rests; positions are kept per frame."""
    rng = np.random.default_rng(seed)
    release = release_times(n_balls)
    dt = 1.0 / (FPS * SUB)
    pos = np.zeros((n_balls, 2))
    vel = np.zeros((n_balls, 2))
    state = np.zeros(n_balls, int)        # 0 waiting, 1 falling, 2 settling in bin, 3 resting
    row_next = np.zeros(n_balls, int)     # next peg row each marble will meet
    binof = np.full(n_balls, -1)
    slot = np.zeros((n_balls, 2))
    filled = [0] * (ROWS + 1)
    tables = [_slots(b, n_balls) for b in range(ROWS + 1)]
    land_t = np.full(n_balls, np.inf)
    hits: list[tuple[float, float, float, int]] = []   # time, x, impact speed, peg index
    frames_pos: list[np.ndarray] = []
    frames_state: list[np.ndarray] = []
    pegs = peg_positions()
    row_start = [r * (r + 1) // 2 for r in range(ROWS)]
    contact = PEG_R + BALL_R

    step = 0
    while True:
        t = step * dt
        if step % SUB == 0:
            frames_pos.append(pos.astype(np.float32))
            frames_state.append(state.astype(np.int8))
            if (state == 3).all():
                break
        new = np.where((state == 0) & (release <= t))[0]
        for j in new:
            pos[j] = (CX + rng.normal(0, 0.4), ENTRY_Y)
            vel[j] = (0.0, 40.0)
            state[j] = 1

        for j in np.where(state == 1)[0]:
            vel[j, 1] += GRAVITY * dt
            pos[j] += vel[j] * dt
            r = row_next[j]
            if r < ROWS:
                # The peg of row r under this marble: nearest by x.
                c = int(np.clip(round((pos[j, 0] - CX) / DX + r / 2), 0, r))
                px, py = pegs[row_start[r] + c]
                if pos[j, 1] >= py - contact and vel[j, 1] > 0:
                    # Bounce: rest on the peg's top, kick up a little, coin-flip a side,
                    # and pick the sideways speed that lands on the next row's peg.
                    vin = vel[j, 1]
                    pos[j, 1] = py - contact
                    vy = -BOUNCE * vin
                    drop = DY if r < ROWS - 1 else (BIN_TOP - (py - contact)) * 0.6
                    tt = (-vy + math.sqrt(vy * vy + 2 * GRAVITY * drop)) / GRAVITY
                    side = 1 if rng.random() < 0.5 else -1
                    vel[j] = (side * (DX / 2) / tt * (1 + rng.normal(0, SPREAD)), vy)
                    hits.append((t, float(px), float(vin), row_start[r] + c))
                    row_next[j] = r + 1
            elif pos[j, 1] > BIN_TOP:
                b = int(np.clip(round((pos[j, 0] - CX) / DX + ROWS / 2), 0, ROWS))
                binof[j] = b
                slot[j] = tables[b][filled[b]]
                filled[b] += 1
                state[j] = 2

        for j in np.where(state == 2)[0]:
            vel[j, 1] += GRAVITY * dt
            pos[j, 1] += vel[j, 1] * dt
            pos[j, 0] += (slot[j, 0] - pos[j, 0]) * min(1.0, 14.0 * dt)
            if pos[j, 1] >= slot[j, 1]:
                if vel[j, 1] > 160:                      # a small bounce on landing
                    pos[j, 1] = slot[j, 1]
                    vel[j, 1] *= -0.2
                else:
                    pos[j], vel[j] = slot[j], 0
                    state[j] = 3
                    land_t[j] = t
        step += 1
        if t > 90:
            raise RuntimeError("Galton simulation did not settle")

    return dict(release=release, frames=np.array(frames_pos), states=np.array(frames_state),
                bins=binof, slot=slot, land=land_t, hits=hits, pegs=pegs,
                counts=np.array(filled))


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def _ball_color(b: int) -> tuple[int, int, int]:
    """Gold in the middle bins, through pink, to cyan at the edges."""
    f = abs(b - ROWS / 2) / (ROWS / 2)
    return mix(GOLD, PINK, f * 2) if f < 0.5 else mix(PINK, CYAN, (f - 0.5) * 2)


Sprites = cv.Sprites        # glossy marbles, shared by every episode


def _halo(radius: int, color, alpha: float) -> Image.Image:
    """Soft round glow (for a lit peg)."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size] - radius
    a = np.exp(-(xx ** 2 + yy ** 2) / (2 * (radius / 2.6) ** 2)) * alpha
    core = np.hypot(xx, yy) <= PEG_R + 0.5
    a = np.where(core, np.maximum(a, alpha), a)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _board(pegs: np.ndarray) -> Image.Image:
    """Walls, floor, funnel, pegs and title: drawn 3x large, shrunk, then given a neon glow."""
    ss = 3
    big = Image.new("RGB", (W * ss, H * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)

    def line(pts, col, w):
        d.line([(x * ss, y * ss) for x, y in pts], fill=col, width=int(w * ss), joint="curve")

    for j in range(ROWS + 2):
        x = CX + (j - ROWS / 2 - 0.5) * DX
        line([(x, BIN_TOP), (x, FLOOR)], scale(CYAN, 0.55), 2.2)
    line([(CX - HALF - 4, FLOOR + 2), (CX + HALF + 4, FLOOR + 2)], CYAN, 3.5)
    line([(CX - 100, ENTRY_Y - 66), (CX - 15, ENTRY_Y - 8)], CYAN, 3.5)
    line([(CX + 100, ENTRY_Y - 66), (CX + 15, ENTRY_Y - 8)], CYAN, 3.5)
    for px, py in pegs:
        r = PEG_R * ss
        d.ellipse((px * ss - r, py * ss - r, px * ss + r, py * ss + r), fill=mix(CYAN, WHITE, 0.25))
    sharp = big.resize((W, H), Image.LANCZOS)

    glow = sharp.filter(ImageFilter.GaussianBlur(9))
    arr = (np.asarray(sharp, np.float32) + np.asarray(glow, np.float32) * 1.8
           + np.array(BG, np.float32))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # Title with a faint glow.
    tf = cv.font(58)
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(layer).text((W / 2, 170), TITLE, font=tf, fill=WHITE, anchor="mm")
    halo = layer.filter(ImageFilter.GaussianBlur(10))
    arr = np.asarray(img, np.float32) + np.asarray(layer, np.float32) + np.asarray(halo, np.float32) * 0.5
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _curve_layer(counts_total: int) -> tuple[Image.Image, tuple[int, int]]:
    """The expected pile outline (normal approximation), glowing, on a transparent strip."""
    mu, sd = ROWS / 2, math.sqrt(ROWS) / 2
    pts = []
    for xb in np.linspace(-0.7, ROWS + 0.7, 200):
        expected = counts_total * math.exp(-((xb - mu) ** 2) / (2 * sd * sd)) / (sd * math.sqrt(2 * math.pi))
        pts.append((CX + (xb - mu) * DX, FLOOR - 3 - expected / PER_ROW * ROW_H - BALL_R))
    x0, y0 = int(min(p[0] for p in pts)) - 30, int(min(p[1] for p in pts)) - 30
    w, h = int(max(p[0] for p in pts)) - x0 + 30, FLOOR + 30 - y0
    ss = 3
    big = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(big).line([((x - x0) * ss, (y - y0) * ss) for x, y in pts], fill=255,
                             width=6 * ss, joint="curve")
    a = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255
    g = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10)),
                   np.float32) / 255
    alpha = np.clip(a + g * 1.4, 0, 1)
    color = np.zeros((h, w, 3), np.float32) + np.array(GOLD, np.float32)
    color = color * (1 - a[..., None] * 0.35) + np.array(WHITE, np.float32) * a[..., None] * 0.35
    rgba = np.dstack([color, alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), (x0, y0)


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def _soundtrack(sim: dict, t_reveal: float, total: float, path: Path) -> None:
    mixer = snd.Mixer(total)
    notes = {i: snd.pluck(snd.scale_freq(i + 5), dur=0.6, bright=0.7) for i in range(16)}
    hits = np.array([(t, x, v) for t, x, v, _ in sim["hits"]])
    gains = snd.density_gains(hits[:, 0], base=0.42, window=0.1, calm=1.5)
    for (t, x, v), g in zip(hits, gains):
        u = (x - (CX - HALF)) / (2 * HALF)                  # 0 left .. 1 right
        mixer.add(t, notes[int(round(u * 14))], g * min(1.0, v / 450), (u - 0.5) * 1.4)
    click = snd.thud(140, 0.12)                              # marble settling: soft knock...
    tick = snd.pluck(2200, dur=0.06, bright=0.2)
    click[: len(tick)] += tick * 0.5                         # ...with a glassy tick on top
    lands = sim["land"]
    for t, g, b in zip(lands, snd.density_gains(lands, base=0.22, calm=1.2), sim["bins"]):
        mixer.add(t, click, g, (b - ROWS / 2) / (ROWS / 2 + 1))
    for j, n in enumerate([5, 7, 9, 10, 12, 14]):         # reveal: rising notes, then a chord
        mixer.add(t_reveal + j * 0.2, snd.pluck(snd.scale_freq(n), dur=1.4), 0.9)
    mixer.add(t_reveal + 1.2, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 10)],
                                        dur=total - t_reveal), 1.4)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    sim = simulate(seed)
    t_reveal = float(sim["land"].max()) + 0.6
    total = t_reveal + 4.5
    n_frames = int(total * FPS)
    frames, states = sim["frames"], sim["states"]

    board = _board(sim["pegs"])
    colors = [_ball_color(int(b)) for b in sim["bins"]]
    sprites = Sprites(colors, BALL_R)
    halos = [_halo(16, mix(CYAN, WHITE, 0.6), a) for a in np.linspace(0.12, 0.95, 8)]
    curve, curve_xy = _curve_layer(N_BALLS)
    count_f, pay_f, sub_f = cv.font(56), cv.font(46), cv.font(30, bold=False)

    hit_t = np.array([h[0] for h in sim["hits"]])
    hit_peg = np.array([h[3] for h in sim["hits"]])
    hit_v = np.array([min(1.0, h[2] / 450) for h in sim["hits"]])
    landed = np.zeros(N_BALLS, bool)

    with tempfile.TemporaryDirectory() as tmp:
        silent = Path(tmp) / "video.mp4"
        enc = cv.Encoder(silent, ffmpeg, fps=FPS)
        for fi in range(n_frames):
            t = fi / FPS
            k = min(fi, len(frames) - 1)
            pos, st = frames[k], states[k]
            # Marbles that came to rest become part of the board.
            for j in np.where((st == 3) & ~landed)[0]:
                sprites.paste(board, colors[j], *sim["slot"][j])
                landed[j] = True
            img = board.copy()

            # Pegs glow when struck, fading over ~0.2 s.
            lo, hi = np.searchsorted(hit_t, t - 0.7), np.searchsorted(hit_t, t)
            if hi > lo:
                lvl = np.zeros(len(sim["pegs"]))
                np.maximum.at(lvl, hit_peg[lo:hi], hit_v[lo:hi] * np.exp(-(t - hit_t[lo:hi]) / 0.2))
                for pi in np.where(lvl > 0.06)[0]:
                    h = halos[min(7, int(lvl[pi] * 8))]
                    px, py = sim["pegs"][pi]
                    img.paste(h, (int(px) - 16, int(py) - 16), h)

            for j in np.where((st == 1) | (st == 2))[0]:
                sprites.paste(img, colors[j], float(pos[j, 0]), float(pos[j, 1]))

            d = ImageDraw.Draw(img)
            a = min(1.0, max(0.0, (t - t_reveal - 1.0) / 0.5))   # counter hands over to the payoff
            if a < 1:
                n = int(np.searchsorted(sim["release"], t, side="right"))
                label, num = "balls: ", f"{n:,}"
                lw, nw = count_f.getlength(label), count_f.getlength(num)
                x0 = W / 2 - (lw + nw) / 2
                d.text((x0, 262), label, font=count_f, fill=scale(WHITE, 1 - a), anchor="lm")
                d.text((x0 + lw, 262), num, font=count_f, fill=scale(GOLD, 1 - a), anchor="lm")
            if t >= t_reveal:
                wipe = min(1.0, (t - t_reveal) / 1.2)
                part = curve.crop((0, 0, max(1, int(curve.width * wipe)), curve.height))
                img.paste(part, curve_xy, part)
                if a > 0:
                    d.text((W / 2, 262), PAYOFF, font=pay_f, fill=scale(GOLD, a), anchor="mm")
                    d.text((W / 2, 322), PAYOFF_SUB, font=sub_f, fill=scale(MUTED, a), anchor="mm")
            enc.write(np.asarray(img))
            if progress and fi % 60 == 0:
                progress(fi, n_frames)
        enc.close()
        wav = Path(tmp) / "sound.wav"
        _soundtrack(sim, t_reveal, total, wav)
        cv.mux(silent, wav, Path(out_path), ffmpeg)
    return total
