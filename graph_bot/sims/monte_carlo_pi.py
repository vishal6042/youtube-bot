"""Can random dots find π? Monte Carlo, live.

Dots land uniformly at random in a square with a circle drawn inside it. The
circle covers π/4 of the square, so 4 × (dots inside ÷ all dots) closes in on π.
It starts with single dots, one at a time, then speeds up to 100,000 so the
circle fills into a glowing gold disc. A live readout shows the estimate (the
digits already matching π turn gold) and a graph shows it settling onto π.

Honest: every dot is a real seeded random draw and every number on screen is
computed from them. The whole run is simulated first; drawing and sound read
that timeline, so every pop and note lines up with a real dot.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import canvas as cv
from . import sound as snd
from .canvas import BG, CYAN, GOLD, MUTED, WHITE, W, mix, scale

FPS = 60
N_DOTS = 100_000
CX, CY = 520, 780          # a little left of centre: YouTube's buttons sit on the right
S = 760                    # square side
R = S / 2                  # circle radius
X0, Y0 = CX - R, CY - R    # square's top-left (140, 400)
M = 14                     # dot-layer margin around the square
RW = S + 2 * M             # dot-layer size (divisible by 4 for the glow)
P = 40                     # line-work margin around the square

# Timing (seconds)
DRAW_ON = (0.15, 1.15)     # square and circle trace themselves
FIRST = np.cumsum([1.55, .5, .42, .36, .31, .27, .24, .21, .19, .17])   # the solo dots
T_END = 22.0               # dots stop arriving (smoothly) here
T_PAY = 22.6               # payoff
TOTAL = 27.8

# Dot size shrinks as the count grows (zooming out), then stays fixed.
S_BIG, S_MIN, S_EXP = 9.0, 1.7, 0.18
N_FINE = int(math.ceil((S_BIG / S_MIN) ** (1 / S_EXP)))
POP = 0.35                 # pop/flash length

READ_Y, FORM_Y = 1250, 1318
GX0, GX1, GY0, GY1 = 140, 900, 1385, 1515   # convergence graph
SPAN = 0.55                                 # graph shows π ± SPAN

TITLE = "Can random dots find π?"
PAYOFF = "Random dots found π"
PAYOFF_SUB = "The real π: 3.14159…"
PI_STR = "3.14159265"



# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def arrival_times(n: int = N_DOTS) -> np.ndarray:
    """Solo dots first, then a rate that grows exponentially and eases to a stop."""
    n0 = len(FIRST)
    t0 = float(FIRST[-1])
    span = T_END - t0
    L = math.log(n / n0)
    a = 0.61                                   # share of steady (log-linear) growth
    u = np.linspace(0, 1, 400_001)
    g = a * (2 * u - u * u) + (1 - a) * (3 * u * u - 2 * u ** 3)
    nt = n0 * np.exp(L * g)
    rest = t0 + span * np.interp(np.arange(n0 + 1, n + 1), nt, u)
    return np.concatenate([FIRST, rest])


def simulate(seed: int = 7, n: int = N_DOTS) -> dict:
    rng = np.random.default_rng(seed)
    xy = rng.random((n, 2)) * S + (X0, Y0)
    inside = np.hypot(xy[:, 0] - CX, xy[:, 1] - CY) <= R
    cum = np.cumsum(inside)
    est = 4.0 * cum / np.arange(1, n + 1)
    return dict(x=xy[:, 0], y=xy[:, 1], inside=inside, cum=cum, est=est,
                t=arrival_times(n))


def dot_size(n: int) -> float:
    return max(S_MIN, S_BIG * max(1, n) ** -S_EXP)


# --------------------------------------------------------------------------- #
# Dots: antialiased splats into two density layers (inside / outside)
# --------------------------------------------------------------------------- #
def _splat(e_in: np.ndarray, e_out: np.ndarray, xs, ys, inside, s) -> None:
    if len(xs) == 0:
        return
    s = np.broadcast_to(np.asarray(s, np.float64), xs.shape)
    k = int(math.ceil(s.max() + 1.5))
    offs = np.arange(-k, k + 1)
    lx, ly = xs - (X0 - M), ys - (Y0 - M)
    gx = np.floor(lx).astype(np.int64)[:, None] + offs
    gy = np.floor(ly).astype(np.int64)[:, None] + offs
    dx = (gx + 0.5 - lx[:, None])[:, None, :]          # (n, 1, K)
    dy = (gy + 0.5 - ly[:, None])[:, :, None]          # (n, K, 1)
    ss = s[:, None, None]
    d2 = dx * dx + dy * dy
    d = np.sqrt(d2)
    cover = np.clip(ss + 0.5 - d, 0, 1)                 # antialiased disc
    shade = 0.75 + 0.25 * np.clip(1 - d2 / (ss * ss), 0, 1)
    gloss = 0.9 * np.exp(-((dx + 0.35 * ss) ** 2 + (dy + 0.4 * ss) ** 2) / (0.32 * ss) ** 2)
    # Each dot a touch brighter or dimmer (fixed per dot): glitter, not flat paint.
    sparkle = (0.72 + 0.28 * ((xs * 7.31 + ys * 3.17) % 1.0))[:, None, None]
    w = cover * (shade + gloss) * sparkle
    gxc = np.clip(gx, 0, RW - 1)[:, None, :]
    gyc = np.clip(gy, 0, RW - 1)[:, :, None]
    idx = (gyc * RW + gxc)
    for layer, sel in ((e_in, inside), (e_out, ~inside)):
        if sel.any():
            layer.ravel()[:] += np.bincount(idx[sel].ravel(), w[sel].ravel(),
                                            minlength=RW * RW).astype(np.float32)


# Colour ramps (value 0..1 -> RGB): dim edges and gaps glow deep amber / deep
# blue, dot centres are gold / cyan, the brightest spots run towards white.
_KNOTS = [0.0, 0.2, 0.45, 0.7, 1.0]
_RAMP_IN = np.array([(0, 0, 0), (110, 42, 8), (232, 140, 40), GOLD, (255, 214, 112)], np.float32)
_RAMP_OUT = np.array([(0, 0, 0), (8, 34, 84), (28, 112, 196), CYAN, (140, 222, 255)], np.float32)


def _ramp(v: np.ndarray, ramp: np.ndarray) -> np.ndarray:
    return np.stack([np.interp(v, _KNOTS, ramp[:, c]) for c in range(3)], axis=-1)


def _fill(e: np.ndarray) -> np.ndarray:
    """Local density, blurred (~8 px): the soft glow between and around dots."""
    small = e.reshape(RW // 4, 4, RW // 4, 4).mean(axis=(1, 3))
    im = Image.fromarray(np.clip(small * 60, 0, 255).astype(np.uint8))
    up = im.filter(ImageFilter.GaussianBlur(2.0)).resize((RW, RW), Image.BILINEAR)
    return np.asarray(up, np.float32) / 60


def _dots_rgb(e_in: np.ndarray, e_out: np.ndarray, boost: float = 1.0) -> np.ndarray:
    """Density -> colour through the ramps; the blurred fill lifts the gaps."""
    out = np.zeros((RW, RW, 3), np.float32)
    for e, ramp, k in ((e_in * boost, _RAMP_IN, 1.0), (e_out, _RAMP_OUT, 0.78)):
        v = 1 - np.exp(-1.7 * e)
        f = 1 - np.exp(-0.55 * _fill(e))
        out += _ramp(1 - (1 - v) * (1 - 0.62 * f), ramp) * k
    return out


def _knee(reg: np.ndarray, knee: float = 175.0) -> np.ndarray:
    """Hue-preserving soft clip: bright crowds stay gold instead of washing to white."""
    m = reg.max(axis=-1, keepdims=True)
    top = 255 - knee
    f = np.where(m > knee, (knee + top * (1 - np.exp(-(m - knee) / top))) / np.maximum(m, 1e-3), 1.0)
    return np.clip(reg * f, 0, 255)


# --------------------------------------------------------------------------- #
# Static pieces
# --------------------------------------------------------------------------- #
LBOX = (int(X0 - P), int(Y0 - P), int(X0 + S + P), int(Y0 + S + P))   # line-work region
DBOX = (int(X0 - M), int(Y0 - M), int(X0 - M + RW), int(Y0 - M + RW))  # dot region
SQ_COL = scale(CYAN, 0.9)
CIRC_COL = mix(GOLD, WHITE, 0.15)


def _linework(p_sq: float, p_circ: float, circle_only: bool = False) -> np.ndarray:
    """Square and circle traced to the given progress, with neon glow (float RGB, region)."""
    ss, size = 3, S + 2 * P
    big = Image.new("RGB", (size * ss, size * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    if not circle_only and p_sq > 0:
        corners = [(P, P), (P + S, P), (P + S, P + S), (P, P + S), (P, P)]
        left = p_sq * 4 * S
        pts = [corners[0]]
        for a, b in zip(corners, corners[1:]):
            seg = min(left, S)
            if seg <= 0:
                break
            f = seg / S
            pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            left -= S
        d.line([(x * ss, y * ss) for x, y in pts], fill=SQ_COL, width=3 * ss, joint="curve")
    if p_circ > 0:
        n = max(2, int(400 * p_circ))
        ang = -math.pi / 2 + np.linspace(0, 2 * math.pi * p_circ, n)
        pts = [((P + R + R * math.cos(a)) * ss, (P + R + R * math.sin(a)) * ss) for a in ang]
        d.line(pts, fill=CIRC_COL, width=3 * ss, joint="curve")
    sharp = big.resize((size, size), Image.LANCZOS)
    glow = sharp.filter(ImageFilter.GaussianBlur(9))
    return np.asarray(sharp, np.float32) + np.asarray(glow, np.float32) * 1.7


def _add(img: Image.Image, box, arr: np.ndarray) -> None:
    reg = np.asarray(img.crop(box), np.float32) + arr
    img.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8)), box[:2])


def _gx(n: float) -> float:
    return GX0 + math.log10(max(1.0, n)) / math.log10(N_DOTS) * (GX1 - GX0)


def _gy(e: float) -> float:
    e = min(math.pi + SPAN, max(math.pi - SPAN, e))
    return GY0 + (math.pi + SPAN - e) / (2 * SPAN) * (GY1 - GY0)


GPAD = 18
GBOX = (GX0 - GPAD, GY0 - GPAD, GX1 + GPAD, GY1 + GPAD)


def _graph_static(alpha: float) -> np.ndarray:
    """Dashed gold line at π and faint frame, for the graph strip."""
    ss = 3
    w, h = GBOX[2] - GBOX[0], GBOX[3] - GBOX[1]
    big = Image.new("RGB", (w * ss, h * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    y = (_gy(math.pi) - GBOX[1]) * ss
    x = 0.0
    while x < GX1 - GX0:
        x2 = min(GX1 - GX0, x + 14)
        d.line([((GX0 - GBOX[0] + x) * ss, y), ((GX0 - GBOX[0] + x2) * ss, y)],
               fill=scale(GOLD, 0.85), width=3 * ss)
        x += 24
    base = (GY1 - GBOX[1] + 6) * ss
    d.line([((GX0 - GBOX[0]) * ss, base), ((GX1 - GBOX[0]) * ss, base)],
           fill=scale(MUTED, 0.45), width=2 * ss)
    sharp = big.resize((w, h), Image.LANCZOS)
    glow = sharp.filter(ImageFilter.GaussianBlur(6))
    return (np.asarray(sharp, np.float32) + np.asarray(glow, np.float32) * 1.0) * alpha


def _graph_line(pts: list[tuple[float, float]]) -> np.ndarray:
    ss = 3
    w, h = GBOX[2] - GBOX[0], GBOX[3] - GBOX[1]
    big = Image.new("RGB", (w * ss, h * ss), (0, 0, 0))
    d = ImageDraw.Draw(big)
    q = [((x - GBOX[0]) * ss, (y - GBOX[1]) * ss) for x, y in pts]
    col = mix(WHITE, CYAN, 0.35)
    if len(q) > 1:
        d.line(q, fill=col, width=3 * ss, joint="curve")
    hx, hy = q[-1]
    r = 6 * ss
    d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=WHITE)
    sharp = big.resize((w, h), Image.LANCZOS)
    glow = sharp.filter(ImageFilter.GaussianBlur(5))
    return np.asarray(sharp, np.float32) + np.asarray(glow, np.float32) * 1.3


def _text_parts(img: Image.Image, cx: float, y: float, parts, fnt, glow: float = 0.0,
                blur: float = 8.0, left: float | None = None) -> None:
    """Multi-coloured text centred on cx (or starting at `left`), with a local glow."""
    widths = [fnt.getlength(s) for s, _ in parts]
    total = sum(widths)
    x0 = left if left is not None else cx - total / 2
    pad = int(blur * 3) + 4
    h = int(fnt.size * 1.5)
    box = (int(x0) - pad, int(y - h / 2) - pad, int(x0 + total) + pad, int(y + h / 2) + pad)
    layer = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = x0 - box[0]
    for (s, c), wdt in zip(parts, widths):
        if s:
            d.text((x, y - box[1]), s, font=fnt, fill=c, anchor="lm")
        x += wdt
    arr = np.asarray(layer, np.float32)
    if glow:
        arr = arr + np.asarray(layer.filter(ImageFilter.GaussianBlur(blur)), np.float32) * glow
    _add(img, box, arr)


def _ring(radius: float, color, alpha: float, width: float = 2.0) -> Image.Image:
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


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def _soundtrack(sim: dict, total: float, path: Path) -> None:
    mixer = snd.Mixer(total)
    rng = np.random.default_rng(1234)
    t, x, y, inside = sim["t"], sim["x"], sim["y"], sim["inside"]
    gap = np.gradient(t)
    rate = 1.0 / np.maximum(gap, 1e-5)
    keep = rng.random(len(t)) < np.minimum(1.0, 55.0 / rate)
    keep[:40] = True
    idx = np.where(keep)[0]
    gains = snd.density_gains(t[idx], base=0.45, window=0.1, calm=1.5)

    notes = [snd.pluck(snd.scale_freq(i), dur=0.55, bright=0.8) for i in range(10, 18)]
    knock = snd.thud(120, 0.14)
    tick = snd.pluck(1500, dur=0.05, bright=0.2)
    knock[: len(tick)] += tick * 0.35
    for i, g in zip(idx, gains):
        pan = float((x[i] - CX) / R * 0.8)
        if inside[i]:
            closeness = 1 - math.hypot(x[i] - CX, y[i] - CY) / R     # nearer the centre: higher
            mixer.add(float(t[i]), notes[min(7, int(closeness * 8))], g * 0.9, pan)
        else:
            mixer.add(float(t[i]), knock, g * 0.75, pan)

    for j, n in enumerate([5, 7, 9, 10, 12, 14]):         # reveal: rising notes, then a chord
        mixer.add(T_PAY + j * 0.2, snd.pluck(snd.scale_freq(n), dur=1.4), 0.9)
    mixer.add(T_PAY + 1.2, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 10)],
                                     dur=total - T_PAY), 1.4)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def _readout_parts(e: float, n: int):
    if n == 0:
        return [("π ≈ ", WHITE), ("?", MUTED)]
    s = f"{e:.5f}"
    k = 0
    while k < len(s) and s[k] == PI_STR[k]:
        k += 1
    return [("π ≈ ", WHITE), (s[:k], GOLD), (s[k:], WHITE)]


def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    sim = simulate(seed)
    xs, ys, inside, times, est, cum = (sim[k] for k in ("x", "y", "inside", "t", "est", "cum"))
    n_frames = int(TOTAL * FPS)

    titled = cv.title(Image.new("RGB", (W, cv.H), BG), TITLE)
    count_f, read_f, form_f = cv.font(50), cv.font(92), cv.font(30, bold=False)
    pay_f, sub_f, pi_f = cv.font(46), cv.font(30, bold=False), cv.font(30)
    read_w = sum(read_f.getlength(s) for s in ("π ≈ ", "0.00000"))
    read_x = CX - read_w / 2

    def board_at(t: float) -> Image.Image:
        p_sq = cv.ease((t - DRAW_ON[0]) / (DRAW_ON[1] - DRAW_ON[0]))
        p_c = cv.ease((t - DRAW_ON[0] - 0.25) / (DRAW_ON[1] - DRAW_ON[0]))
        a = cv.ease((t - DRAW_ON[0]) / 0.8)
        img = titled.copy()
        _add(img, LBOX, _linework(p_sq, p_c))
        _add(img, GBOX, _graph_static(a))
        ImageDraw.Draw(img).text((GX0 - 20, _gy(math.pi)), "π", font=pi_f,
                                 fill=scale(GOLD, a), anchor="mm")
        return img

    static_board = board_at(10.0)
    ring_glow = _linework(0, 1, circle_only=True)
    t_static = DRAW_ON[1] + 0.3

    # Graph samples: every dot count up to ~80, then log-spaced.
    g_ns = np.unique(np.round(np.logspace(0, math.log10(N_DOTS), 900)).astype(int))
    g_pts = [(_gx(n), _gy(est[n - 1])) for n in g_ns]

    e_in = np.zeros((RW, RW), np.float32)
    e_out = np.zeros((RW, RW), np.float32)
    baked = 0                      # dots already in the persistent layers (fine phase)
    fine = False
    halos: dict = {}
    rings: dict = {}

    with tempfile.TemporaryDirectory() as tmp:
        silent = Path(tmp) / "video.mp4"
        enc = cv.Encoder(silent, ffmpeg, fps=FPS)
        for fi in range(n_frames):
            t = fi / FPS
            img = static_board.copy() if t >= t_static else board_at(t)
            n = int(np.searchsorted(times, t, side="right"))

            # ---- dots ----
            if n < N_FINE:
                e_in[:] = 0
                e_out[:] = 0
                if n:
                    age = (t - times[:n]) / POP
                    pop = np.where(age < 1, 1 + 0.9 * (1 - np.clip(age, 0, 1)) ** 3, 1.0)
                    _splat(e_in, e_out, xs[:n], ys[:n], inside[:n], dot_size(n) * pop)
            else:
                if not fine:
                    e_in[:] = 0
                    e_out[:] = 0
                    baked, fine = 0, True
                _splat(e_in, e_out, xs[baked:n], ys[baked:n], inside[baked:n], S_MIN)
                baked = n

            pulse = 0.0
            if t >= T_PAY:
                u = t - T_PAY
                pulse = math.exp(-((u - 0.7) / 0.45) ** 2) + 0.18 * cv.ease(u / 1.5)
            reg = np.asarray(img.crop(DBOX), np.float32) + _dots_rgb(e_in, e_out, 1 + 0.35 * pulse)
            img.paste(Image.fromarray(_knee(reg).astype(np.uint8)), DBOX[:2])
            if pulse > 0.01:
                _add(img, LBOX, ring_glow * (0.9 * pulse))

            # ---- pops: a flash on the newest dots, a ring on the first few ----
            lo = max(0, int(np.searchsorted(times, t - POP)), n - 260)
            s_now = dot_size(n)
            for i in range(lo, n):
                u = (t - times[i]) / POP
                if u >= 1:
                    continue
                col = GOLD if inside[i] else CYAN
                lvl = int((1 - u) ** 2 * 7.99)
                if lvl > 0:
                    rad = int(round(2.4 * s_now + 5))
                    key = (rad, col, lvl)
                    if key not in halos:
                        halos[key] = cv.halo_sprite(rad, mix(col, WHITE, 0.45), lvl / 8 * 0.85)
                    cv.add_rgba(img, halos[key], xs[i], ys[i])
                if i < 24:
                    rr = round(s_now * (1.4 + 3.2 * cv.ease_out(u)))
                    lv = int((1 - u) ** 1.5 * 7.99)
                    if lv > 0:
                        key = (rr, col, lv)
                        if key not in rings:
                            rings[key] = _ring(rr, col, lv / 8)
                        cv.add_rgba(img, rings[key], xs[i], ys[i])

            # ---- convergence graph ----
            if n:
                k = int(np.searchsorted(g_ns, n, side="right"))
                pts = g_pts[:k] + [(_gx(n), _gy(est[n - 1]))]
                _add(img, GBOX, _graph_line(pts))

            # ---- readout ----
            e = float(est[n - 1]) if n else 0.0
            _text_parts(img, CX, READ_Y, _readout_parts(e, n), read_f, glow=0.45, left=read_x if n else None)
            ImageDraw.Draw(img).text((CX, FORM_Y), "4 × (dots in circle ÷ all dots)", font=form_f,
                                     fill=MUTED, anchor="mm")

            # ---- counter hands over to the payoff ----
            a = min(1.0, max(0.0, (t - T_PAY - 1.0) / 0.5))
            if a < 1:
                ins = int(cum[n - 1]) if n else 0
                f = 1 - a
                _text_parts(img, W / 2, cv.LINE_Y,
                            [("dots ", scale(WHITE, f)), (f"{n:,}", scale(WHITE, f)),
                             ("     in circle ", scale(GOLD, f * 0.85)), (f"{ins:,}", scale(GOLD, f))],
                            count_f, glow=0.25 * f)
            if a > 0:
                _text_parts(img, W / 2, cv.LINE_Y, [(PAYOFF, scale(GOLD, a))], pay_f, glow=0.5 * a)
                ImageDraw.Draw(img).text((W / 2, cv.SUB_Y), PAYOFF_SUB, font=sub_f,
                                         fill=scale(MUTED, a), anchor="mm")

            enc.write(np.asarray(img))
            if progress and fi % 60 == 0:
                progress(fi, n_frames)
        enc.close()
        wav = Path(tmp) / "sound.wav"
        _soundtrack(sim, TOTAL, wav)
        cv.mux(silent, wav, Path(out_path), ffmpeg)
    return TOTAL
