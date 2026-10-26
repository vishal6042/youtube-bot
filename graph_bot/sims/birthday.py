"""Birthday paradox: people walk into a room until two share a birthday, 500 times.

A calendar ring holds the 365 days. In each room people arrive one by one, each
a marble flying from the centre to their birthday (a fair draw over 365 days);
the moment one lands on a day that is already taken, the room has its match.
The first rooms play slowly, then they speed up to dozens a second. Every room
drops a bead into a histogram of "people needed for a match", so the piles show
the real distribution, and the payoff marks 23, where half the rooms are done.

The whole run is simulated first; drawing and sound read that timeline, so
every light, burst and note lines up with a real arrival. 60 fps.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import canvas as cv
from . import sound as snd
from . import voice
from .canvas import BG, CYAN, GOLD, H, MUTED, PINK, WHITE, W, mix, scale

FPS = 60
N_ROOMS = 500
DAYS = 365
CX, CY, R = 520, 740, 300          # calendar ring (a little left of centre)
MARBLE_R = 7.0
LAND_R = R - 24                    # where a person's marble rests, just inside its day
PAIR_STEP = 15                     # the matching marble rests this much further in
SPOUT = (CX, CY + R + 40)          # beads leave the ring here
FLOOR = 1500
NMIN, NMAX = 2, 68                 # histogram columns: people needed for a match
SP = 11.0                          # column spacing
BR = 5.3                           # bead radius
X0 = CX - (NMAX - NMIN) / 2 * SP
GRAVITY = 2200.0
BEAD_T = 0.65                      # bead flight time, spout to pile
BOUNCE_T = 0.22
START = 1.25                       # first arrival, after the ring has drawn on
DRAW_ON = (0.15, 1.1)

TITLE1, TITLE2 = "How many people until", "two share a birthday?"
TITLE_YS = (112, 180)               # two lines, clear of the counter at LINE_Y
LAUNCH_R = 62                      # marbles appear just outside the centre number
MONTHS = "JFMAMJJASOND"
MONTH_LEN = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_START = np.cumsum([0] + MONTH_LEN[:-1])

# The rooms played one by one: first gap, gap decay, smallest gap, flight, hold, fade (s).
SHOWN = [
    (0.40, 0.88, 0.15, 0.55, 1.50, 0.40),
    (0.14, 0.92, 0.065, 0.36, 0.75, 0.28),
    (0.055, 1.0, 0.055, 0.30, 0.50, 0.22),
    (0.032, 1.0, 0.032, 0.24, 0.34, 0.16),
    (0.022, 1.0, 0.022, 0.22, 0.30, 0.15),
]
FAST_SPAN = 8.6                    # seconds for the remaining rooms, speeding up
SNAP_EVERY = 0.22                  # the ring shows one real room this often when fast

# Voice-over: the question as room 1 fills, the reason at the payoff. Nothing else.
SAY_ASK = "People walk in. How many until two share a birthday?"
SAY_WHY = "Usually just twenty-three. Twenty-three people make two hundred fifty-three pairs."
ASK_AT = 0.9


# --------------------------------------------------------------------------- #
# Geometry and colour
# --------------------------------------------------------------------------- #
def _theta(d: float) -> float:
    """Angle of day d: 1 January at the top, clockwise like a clock."""
    return -math.pi / 2 + 2 * math.pi * (d + 0.5) / DAYS


def _at(d: float, r: float) -> tuple[float, float]:
    a = _theta(d)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def _month(d: int) -> int:
    return int(np.searchsorted(MONTH_START, d, side="right") - 1)


_PAL = [CYAN, PINK, GOLD]


def _day_color(d: float) -> tuple[int, int, int]:
    """The ring cycles cyan -> pink -> gold -> cyan through the year (quantised)."""
    q = round(d / DAYS * 36) % 36
    f = q / 36 * 3
    i = int(f)
    return mix(_PAL[i % 3], _PAL[(i + 1) % 3], f - i)


def _col_x(n: int) -> float:
    return X0 + (min(max(n, NMIN), NMAX) - NMIN) * SP


def _bead_color(n: int) -> tuple[int, int, int]:
    """Gold near 23, through pink, to cyan for the long rooms."""
    f = min(1.0, abs(n - 23) / 26)
    return mix(GOLD, PINK, f * 2) if f < 0.5 else mix(PINK, CYAN, (f - 0.5) * 2)


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def simulate(seed: int = 11, n_rooms: int = N_ROOMS) -> dict:
    rng = np.random.default_rng(seed)
    rooms = []
    for _ in range(n_rooms):
        seen: dict[int, int] = {}
        days: list[int] = []
        while True:
            d = int(rng.integers(DAYS))
            if d in seen:
                days.append(d)
                rooms.append({"days": days, "first": seen[d], "k": len(days)})
                break
            seen[d] = len(days)
            days.append(d)

    t = START
    for i, room in enumerate(rooms[:len(SHOWN)]):
        g0, dec, gmin, fl, hold, fade = SHOWN[i]
        launches = []
        for j in range(room["k"]):
            launches.append(t)
            if j < room["k"] - 1:
                t += max(gmin, g0 * dec ** j)
        m = launches[-1] + fl
        room.update(shown=True, launch=np.array(launches), land=np.array(launches) + fl,
                    flight=fl, match_t=m, bead_t=m + 0.3, fade_t=m + hold, fade=fade,
                    end=m + hold + fade)
        t = m + hold + fade + 0.12

    fast = rooms[len(SHOWN):]
    f0 = t
    u = np.arange(1, len(fast) + 1) / max(1, len(fast))
    for room, tt in zip(fast, f0 + FAST_SPAN * u ** (1 / 1.7)):
        room.update(shown=False, match_t=float(tt), bead_t=float(tt))

    # Beads: one per room, into the column for its size, stacked single file.
    filled: dict[int, int] = {}
    for room in rooms:
        c = min(max(room["k"], NMIN), NMAX)
        s = filled.get(c, 0)
        filled[c] = s + 1
        room["col"] = c
        room["slot_y"] = FLOOR - 3 - BR - s * 2 * BR

    # The ring shows one real room every SNAP_EVERY seconds while rooms fly by.
    snaps = []
    if fast:
        times = np.array([r["match_t"] for r in fast])
        ts = f0 + 0.05
        while ts <= times[-1] + 0.01:
            j = int(np.searchsorted(times, ts, side="right")) - 1
            if j >= 0 and (not snaps or snaps[-1][1] != j + len(SHOWN)):
                snaps.append((ts, j + len(SHOWN)))
            ts += SNAP_EVERY
    ks = np.array([r["k"] for r in rooms])
    return {"rooms": rooms, "snaps": snaps, "ks": ks,
            "share23": float((ks <= 23).mean())}


def expected_counts(n_rooms: int = N_ROOMS) -> dict[int, float]:
    """Exact chance that the first match comes with person n, scaled to n_rooms."""
    out, none_yet = {}, 1.0
    for n in range(2, NMAX + 1):
        p = none_yet * (n - 1) / DAYS
        out[n] = n_rooms * p
        none_yet *= 1 - (n - 1) / DAYS
    return out


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def _lines() -> Image.Image:
    """Ring, month arcs, histogram floor and labels on black (neon added later)."""
    b = cv.Big()
    s = b.ss
    for d in range(DAYS):
        x, y = _at(d, R)
        b.circle(x, y, 1.6, fill=scale(_day_color(d), 0.55))
    ra = R + 17
    for m in range(12):
        a0 = math.degrees(_theta(MONTH_START[m] - 0.5)) + 1.0
        a1 = math.degrees(_theta(MONTH_START[m] + MONTH_LEN[m] - 0.5)) - 1.0
        col = scale(_day_color(MONTH_START[m] + MONTH_LEN[m] / 2), 0.85)
        b.d.arc([(CX - ra) * s, (CY - ra) * s, (CX + ra) * s, (CY + ra) * s], a0, a1,
                fill=col, width=int(3 * s))
        x, y = _at(MONTH_START[m] + MONTH_LEN[m] / 2, R + 46)
        b.text(x, y, MONTHS[m], 24, scale(MUTED, 0.95))
    b.circle(*SPOUT, 9, outline=scale(CYAN, 0.7), w=2)
    x1 = _col_x(NMAX)
    b.line([(X0 - 14, FLOOR + 2), (x1 + 14, FLOOR + 2)], CYAN, 3.2)
    for n in range(10, NMAX + 1, 10):
        x = _col_x(n)
        b.line([(x, FLOOR + 8), (x, FLOOR + 15)], scale(MUTED, 0.8), 2)
        b.text(x, FLOOR + 30, str(n), 22, scale(MUTED, 0.9), bold=False)
    return b.shrink()


def _base(lines: Image.Image) -> tuple[Image.Image, Image.Image]:
    """(full board, background-only board): both carry the title."""
    full = cv.neon(lines, blur=8, gain=1.5)
    empty = Image.new("RGB", (W, H), BG)
    tf = cv.font(58)
    full = cv.glow_text(cv.glow_text(full, W / 2, TITLE_YS[0], TITLE1, tf, WHITE), W / 2, TITLE_YS[1], TITLE2, tf, WHITE)
    empty = cv.glow_text(cv.glow_text(empty, W / 2, TITLE_YS[0], TITLE1, tf, WHITE),
                         W / 2, TITLE_YS[1], TITLE2, tf, WHITE)
    ImageDraw.Draw(full).text((_col_x(NMAX) + 8, 1296), "people until a match",
                              font=cv.font(24, bold=False), fill=scale(MUTED, 0.95), anchor="rm")
    return full, empty


def _ring_sprite(radius: int, color, width: float = 3.0) -> Image.Image:
    """A thin glowing circle (the match burst), supersampled."""
    pad = 14
    size = (radius + pad) * 2
    ss = 4
    big = Image.new("L", (size * ss, size * ss), 0)
    c = size * ss / 2
    ImageDraw.Draw(big).ellipse((c - radius * ss, c - radius * ss, c + radius * ss, c + radius * ss),
                                outline=255, width=int(width * ss))
    a = np.asarray(big.resize((size, size), Image.LANCZOS), np.float32) / 255
    g = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5)),
                   np.float32) / 255
    alpha = np.clip(a + g * 1.3, 0, 1)
    rgb = np.zeros((size, size, 3), np.float32) + np.array(color, np.float32)
    rgb = rgb * (1 - a[..., None] * 0.4) + np.array(WHITE, np.float32) * a[..., None] * 0.4
    return Image.fromarray(np.dstack([rgb, alpha * 255]).astype(np.uint8), "RGBA")


def _curve_layer(expected: dict[int, float]) -> tuple[Image.Image, tuple[int, int]]:
    """The expected bead piles (exact probabilities), as a glowing gold line."""
    ns = np.linspace(NMIN, NMAX, 400)
    ys = np.interp(ns, list(expected), list(expected.values()))
    pts = [(X0 + (n - NMIN) * SP, FLOOR - 3 - y * 2 * BR) for n, y in zip(ns, ys)]
    x0, y0 = int(min(p[0] for p in pts)) - 30, int(min(p[1] for p in pts)) - 30
    w, h = int(max(p[0] for p in pts)) - x0 + 30, FLOOR + 30 - y0
    ss = 3
    big = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(big).line([((x - x0) * ss, (y - y0) * ss) for x, y in pts], fill=255,
                             width=5 * ss, joint="curve")
    a = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255
    g = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9)),
                   np.float32) / 255
    alpha = np.clip(a + g * 1.3, 0, 1) * 0.9
    color = np.zeros((h, w, 3), np.float32) + np.array(GOLD, np.float32)
    color = color * (1 - a[..., None] * 0.35) + np.array(WHITE, np.float32) * a[..., None] * 0.35
    return Image.fromarray(np.dstack([color, alpha * 255]).astype(np.uint8), "RGBA"), (x0, y0)


def _marker_layer() -> tuple[Image.Image, tuple[int, int]]:
    """Dashed gold line up from the floor at 23, glowing."""
    x = _col_x(23)
    top, bot = 1250, FLOOR - 1
    w, h = 60, bot - top + 40
    ox, oy = int(x) - w // 2, top - 20
    ss = 3
    big = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(big)
    y = top
    while y < bot:
        y2 = min(bot, y + 12)
        d.line([((x - ox) * ss, (y - oy) * ss), ((x - ox) * ss, (y2 - oy) * ss)], fill=255, width=3 * ss)
        y += 20
    a = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255
    g = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)),
                   np.float32) / 255
    alpha = np.clip(a + g * 1.2, 0, 1)
    rgb = np.zeros((h, w, 3), np.float32) + np.array(GOLD, np.float32)
    return Image.fromarray(np.dstack([rgb, alpha * 255]).astype(np.uint8), "RGBA"), (ox, oy)


def _paste(img: Image.Image, spr: Image.Image, x: float, y: float, a: float = 1.0,
           xy: tuple[int, int] | None = None) -> None:
    """Paste an RGBA sprite centred on (x, y) (or at top-left xy), faded by a."""
    if a <= 0.01:
        return
    pos = xy or (int(round(x - spr.width / 2)), int(round(y - spr.height / 2)))
    if a >= 0.99:
        img.paste(spr, pos, spr)
    else:
        img.paste(spr, pos, spr.getchannel("A").point(lambda v, a=a: int(v * a)))


def _marble(img: Image.Image, sprites: cv.Sprites, color, x: float, y: float, a: float = 1.0) -> None:
    fx, fy = math.floor(x), math.floor(y)
    spr = sprites.cache[color][(int((x - fx) * sprites.sub), int((y - fy) * sprites.sub))]
    _paste(img, spr, 0, 0, a, xy=(fx - sprites.size // 2, fy - sprites.size // 2))


class Look:
    """Every sprite and font the frames need, made once."""

    def __init__(self, sim: dict):
        cols = {_day_color(d) for d in range(DAYS)}
        self.marbles = cv.Sprites(list(cols), MARBLE_R)
        self.beads = cv.Sprites([_bead_color(n) for n in range(NMIN, NMAX + 1)], BR)
        self.lights = {c: [cv.halo_sprite(11, c, a, core=2.6) for a in np.linspace(0.15, 1.0, 8)]
                       for c in cols}
        self.pink_halo = [cv.halo_sprite(30, PINK, a) for a in np.linspace(0.1, 0.9, 8)]
        self.bursts = [_ring_sprite(r, PINK) for r in range(10, 96, 4)]
        self.num_f, self.ppl_f, self.match_f = cv.font(124), cv.font(30, bold=False), cv.font(46)
        self.count_f, self.pay_f, self.sub_f = cv.font(56), cv.font(46), cv.font(30, bold=False)
        self.label_f = cv.font(40)

    def light(self, c, a: float) -> Image.Image:
        return self.lights[c][min(7, max(0, int(a * 8 - 0.01)))]


def _draw_room(img: Image.Image, look: Look, room: dict, t: float) -> tuple[int | None, float, bool]:
    """A room played person by person. Returns (count to show, its alpha, matched)."""
    a_room = 1.0 - min(1.0, max(0.0, (t - room["fade_t"]) / room["fade"]))
    if a_room <= 0:
        return None, 0.0, False
    days, k = room["days"], room["k"]
    landed = int(np.searchsorted(room["land"], t, side="right"))
    matched = t >= room["match_t"]
    md = days[-1]
    # Lights first (under the marbles), then the marbles.
    for j in range(landed):
        c = _day_color(days[j])
        _paste(img, look.light(c, 1.0), *_at(days[j], R), a_room)
    if matched:
        dt = t - room["match_t"]
        pulse = 0.55 + 0.45 * math.exp(-dt / 0.35)
        lvl = min(7, int(pulse * 8))
        for j in (room["first"], k - 1):
            _paste(img, look.pink_halo[lvl], *_at(days[j], LAND_R - (PAIR_STEP if j == k - 1 else 0)), a_room)
        if dt < 0.75:
            u = dt / 0.75
            spr = look.bursts[min(len(look.bursts) - 1, int(cv.ease_out(u) * len(look.bursts)))]
            _paste(img, spr, *_at(md, LAND_R - PAIR_STEP / 2), a_room * (1 - u) ** 1.3)
    for j in range(k):
        t0 = room["launch"][j]
        if t < t0:
            break
        r_end = LAND_R - (PAIR_STEP if j == k - 1 else 0)
        u = min(1.0, (t - t0) / room["flight"])
        p = cv.ease_out(u)
        ex, ey = _at(days[j], r_end)
        sx, sy = _at(days[j], LAUNCH_R)
        x, y = sx + (ex - sx) * p, sy + (ey - sy) * p
        fade_in = min(1.0, u * 4)
        _marble(img, look.marbles, _day_color(days[j]), x, y, a_room * fade_in)
    return landed, a_room, matched


def _draw_snap(img: Image.Image, look: Look, room: dict, a: float) -> None:
    """A fast room shown whole: its lit days and the pink match."""
    days, k = room["days"], room["k"]
    for j in range(k - 1):
        _paste(img, look.light(_day_color(days[j]), a), *_at(days[j], R), 1.0)
    lvl = min(7, int(a * 8 * 0.8))
    _paste(img, look.pink_halo[lvl], *_at(days[-1], R - 6), 1.0)


def _snap_alpha(t: float, ts: float) -> float:
    if t < ts:
        return 0.0
    u = t - ts
    if u < 0.05:
        return u / 0.05
    if u < 0.14:
        return 1.0
    return max(0.0, 1 - (u - 0.14) / 0.24)


def _bead_pos(room: dict, t: float) -> tuple[float, float, bool]:
    u = t - room["bead_t"]
    tx, ty = _col_x(room["col"]), room["slot_y"]
    sx, sy = SPOUT
    if u < BEAD_T:
        vy0 = (ty - sy - GRAVITY * BEAD_T ** 2 / 2) / BEAD_T
        return sx + (tx - sx) * u / BEAD_T, sy + vy0 * u + GRAVITY * u * u / 2, False
    v = (u - BEAD_T) / BOUNCE_T
    return tx, ty - 6 * (1 - v) * abs(math.sin(math.pi * 2 * v)), True


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def _soundtrack(sim: dict, t_reveal: float, total: float, path: Path, clips: list | None = None) -> None:
    mixer = snd.Mixer(total)
    notes = {m: snd.pluck(snd.scale_freq(5 + m), dur=0.55, bright=0.7) for m in range(18)}
    ev = []
    for room in sim["rooms"]:
        if not room.get("shown"):
            continue
        for j, d in enumerate(room["days"]):
            x, _ = _at(d, R)
            ev.append((room["land"][j], _month(d), (x - CX) / R * 0.8))
    ev_t = np.array([e[0] for e in ev])
    for (t, m, pan), g in zip(ev, snd.density_gains(ev_t, base=0.36, window=0.1, calm=1.6)):
        mixer.add(t, notes[m], g, pan)

    bell = snd.pluck(snd.scale_freq(17), dur=1.8, bright=1.0)
    for i, room in enumerate(r for r in sim["rooms"] if r.get("shown")):
        g = [1.0, 0.7, 0.55, 0.45, 0.4][min(i, 4)]
        x, _ = _at(room["days"][-1], R)
        mixer.add(room["match_t"], bell, 0.75 * g, (x - CX) / R * 0.6)
        mixer.add(room["match_t"] + 0.02, snd.chord([snd.scale_freq(n) for n in (10, 12, 14)],
                                                   dur=1.6), 0.9 * g)
    for ts, ri in sim["snaps"]:
        m = _month(sim["rooms"][ri]["days"][-1])
        mixer.add(ts, notes[min(17, 9 + m % 6)], 0.13)

    click = snd.thud(140, 0.12)
    tick = snd.pluck(2200, dur=0.06, bright=0.2)
    click[: len(tick)] += tick * 0.5
    lands = np.array([r["bead_t"] + BEAD_T for r in sim["rooms"]])
    cols = np.array([r["col"] for r in sim["rooms"]])
    for t, g, c in zip(lands, snd.density_gains(lands, base=0.24, calm=1.2), cols):
        mixer.add(t, click, g, (_col_x(c) - CX) / 420)

    for j, n in enumerate([5, 7, 9, 10, 12, 14]):
        mixer.add(t_reveal + j * 0.2, snd.pluck(snd.scale_freq(n), dur=1.4), 0.9)
    mixer.add(t_reveal + 1.2, snd.chord([snd.scale_freq(i) for i in (5, 7, 9, 10)],
                                        dur=total - t_reveal), 1.4)
    if clips:
        voice.voice_over(mixer, clips)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(out_path: Path, ffmpeg: str, seed: int = 11, progress=None) -> float:
    sim = simulate(seed)
    rooms = sim["rooms"]
    t_reveal = max(r["bead_t"] for r in rooms) + BEAD_T + BOUNCE_T + 0.5
    ask, why = voice.say(SAY_ASK, ffmpeg), voice.say(SAY_WHY, ffmpeg)
    why_at = t_reveal + 0.5
    total = max(t_reveal + 4.6, why_at + why.secs + 1.1)
    clips = [(ASK_AT, ask), (why_at, why)]
    n_frames = int(total * FPS)

    lines = _lines()
    board, empty = _base(lines)
    look = Look(sim)
    curve, curve_xy = _curve_layer(expected_counts(N_ROOMS))
    marker, marker_xy = _marker_layer()
    pct = round(sim["share23"] * 100)

    # Draw-on masks: the ring sweeps round from 1 January; the histogram wipes in.
    yy, xx = np.mgrid[0:H, 0:W]
    ang = (np.arctan2(yy - CY, xx - CX) + math.pi / 2) % (2 * math.pi)
    ring_zone = np.hypot(xx - CX, yy - CY) < R + 75
    hist_zone = yy > 1180
    board_arr = np.asarray(board)
    empty_arr = np.asarray(empty)

    bead_t = np.array([r["bead_t"] for r in rooms])
    perm = 0
    shown = [r for r in rooms if r.get("shown")]
    snaps = sim["snaps"]
    snap_t = np.array([s[0] for s in snaps]) if snaps else np.array([])

    with tempfile.TemporaryDirectory() as tmp:
        silent = Path(tmp) / "video.mp4"
        enc = cv.Encoder(silent, ffmpeg, fps=FPS)
        for fi in range(n_frames):
            t = fi / FPS
            # Beads that finished bouncing become part of the board.
            while perm < len(rooms) and bead_t[perm] + BEAD_T + BOUNCE_T <= t:
                r = rooms[perm]
                _marble(board, look.beads, _bead_color(r["col"]), _col_x(r["col"]), r["slot_y"])
                perm += 1

            if t < DRAW_ON[1] + 0.05:
                u = cv.ease((t - DRAW_ON[0]) / (DRAW_ON[1] - DRAW_ON[0]))
                mask = (ring_zone & (ang <= u * 2 * math.pi)) | (hist_zone & (xx <= X0 - 20 + u * 800))
                mask |= ~(ring_zone | hist_zone)
                img = Image.fromarray(np.where(mask[..., None], board_arr, empty_arr))
            else:
                img = board.copy()

            reveal_a = cv.ease((t - t_reveal) / 0.8)
            count, count_a, matched = None, 0.0, False
            for room in shown:
                if room["launch"][0] <= t < room["end"]:
                    count, count_a, matched = _draw_room(img, look, room, t)
            if len(snap_t):
                lo = int(np.searchsorted(snap_t, t - 0.45))
                hi = int(np.searchsorted(snap_t, t, side="right"))
                for si in range(lo, hi):
                    a = _snap_alpha(t, snap_t[si]) * (1 - reveal_a)
                    if a > 0.02:
                        _draw_snap(img, look, rooms[snaps[si][1]], a)
                if hi > lo and count is None and reveal_a < 1:
                    si = hi - 1
                    count, count_a = rooms[snaps[si][1]]["k"], 0.85 * (1 - reveal_a)
                    matched = False

            # Beads in flight.
            lo = int(np.searchsorted(bead_t, t - BEAD_T - BOUNCE_T))
            hi = int(np.searchsorted(bead_t, t, side="right"))
            for i in range(max(lo, perm), hi):
                r = rooms[i]
                x, y, _ = _bead_pos(r, t)
                _marble(img, look.beads, _bead_color(r["col"]), x, y)

            d = ImageDraw.Draw(img)
            # Centre: people in the room (or 23 at the payoff).
            if reveal_a > 0:
                d.text((CX, CY - 8), "23", font=look.num_f, fill=scale(GOLD, reveal_a), anchor="mm")
                d.text((CX, CY + 70), "people", font=look.ppl_f, fill=scale(MUTED, reveal_a), anchor="mm")
            elif count is not None and count_a > 0:
                col = WHITE if not matched else mix(WHITE, PINK, 0.25)
                d.text((CX, CY - 8), str(count), font=look.num_f, fill=scale(col, count_a), anchor="mm")
                d.text((CX, CY + 70), "people", font=look.ppl_f, fill=scale(MUTED, count_a), anchor="mm")
            if matched and count_a > 0:
                d.text((CX, CY - 112), "Match!", font=look.match_f, fill=scale(PINK, count_a), anchor="mm")

            # Counter, handing over to the payoff.
            a = min(1.0, max(0.0, (t - t_reveal - 1.0) / 0.5))
            if a < 1:
                n = int(np.searchsorted(bead_t, t, side="right"))
                label, num = "rooms: ", f"{n:,}"
                lw, nw = look.count_f.getlength(label), look.count_f.getlength(num)
                x0 = W / 2 - (lw + nw) / 2
                d.text((x0, cv.LINE_Y), label, font=look.count_f, fill=scale(WHITE, 1 - a), anchor="lm")
                d.text((x0 + lw, cv.LINE_Y), num, font=look.count_f, fill=scale(GOLD, 1 - a), anchor="lm")
            if t >= t_reveal:
                wipe = min(1.0, (t - t_reveal) / 1.2)
                part = curve.crop((0, 0, max(1, int(curve.width * wipe)), curve.height))
                img.paste(part, curve_xy, part)
                ma = cv.ease((t - t_reveal - 0.6) / 0.6)
                _paste(img, marker, 0, 0, ma, xy=marker_xy)
                if ma > 0:
                    d.text((_col_x(23), 1222), "23", font=look.label_f, fill=scale(GOLD, ma), anchor="mm")
                if a > 0:
                    d.text((W / 2, cv.LINE_Y), "Half the time: just 23 people", font=look.pay_f,
                           fill=scale(GOLD, a), anchor="mm")
                    d.text((W / 2, cv.SUB_Y), f"{pct}% of these {N_ROOMS} rooms matched by 23",
                           font=look.sub_f, fill=scale(MUTED, a), anchor="mm")
            enc.write(np.asarray(img))
            if progress and fi % 60 == 0:
                progress(fi, n_frames)
        enc.close()
        wav = Path(tmp) / "sound.wav"
        _soundtrack(sim, t_reveal, total, wav, clips)
        cv.mux(silent, wav, Path(out_path), ffmpeg)
    return total
