"""Monty Hall: 1,000 games, two players, one rule each. Should you switch doors?

Each game: a prize hides behind one of three doors. Both players pick the same
door; the host, who knows where the prize is, opens another door that is
empty. The STAY player (cyan) keeps the first pick, the SWITCH player (pink)
moves to the last closed door. Whoever ends on the prize wins, and their marble
drops into their glass tube. Exactly one of them wins every game, so the two
tubes together hold one marble per game, and their heights race toward 1/3 and
2/3.

Every game is really played (seeded random prize and pick; the host opens a
random empty door when he has a choice). The first three are shown slowly, then
the games speed up; once they are too fast to show, the doors show a sample of
real games while every game still sends its marble to a tube.
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
from .canvas import CYAN, GOLD, H, MUTED, PINK, WHITE, W, mix, scale

FPS = 60
N_GAMES = 1000
CX = 520                         # a little left of centre: YouTube's buttons sit on the right

DOOR_W, DOOR_H = 180, 270
DOOR_Y0 = 450
DOOR_STEP = DOOR_W + 55
DOOR_X = [CX + (i - 1) * DOOR_STEP for i in range(3)]      # door centres
MARK_Y, MARK_R, MARK_DX = 772, 12.0, 27

TUBE_TOP, FLOOR, TUBE_W = 1050, 1500, 262
TUBE_X = {"stay": CX - 185, "switch": CX + 185}
BALL_R = 6.0
ROW_H = BALL_R * 2 * math.sin(math.pi / 3)
PER_ROW = 20.5                   # rows of 21 and 20 marbles, alternating

GRAVITY = 2400.0
LAUNCH_VY = -330.0               # the winner hops up before it falls

# Game timing: the first three slowly, the rest speeding up. Game 1 is timed
# to the voice-over instead (see schedule).
SLOW = [5.0, 2.2, 1.4]
START = 0.8
STREAM_LEN = 9.5                 # seconds for the remaining 997 games
STREAM_POW = 2.2
MIN_SHOWN_GAP = 0.6              # doors show at most one game per this long

TITLE = "Should you switch doors?"
CAPTIONS = [(0.00, 0.12, "You pick a door"),
            (0.12, 0.48, "The host opens an empty one"),
            (0.48, 0.80, "Stay… or switch?")]
COL = {"stay": CYAN, "switch": PINK}

# Voice-over: the rules over game 1, the reason at the payoff. Nothing else.
SAY_PICK = "Pick a door."
SAY_HOST = "The host knows where the prize is, and opens an empty one."
SAY_ASK = "Stay, or switch?"
SAY_WHY = "Switching wins two in three, because your first pick is wrong two times out of three."

# A game's steps as fractions of its length: marbles appear (0), host's door
# opens (0.24-0.34), the switch marble moves (0.48-0.60), the last doors open
# (0.68-0.78), the winner launches (0.80), doors close (0.90-1.0). Game 1 maps
# these onto the voice instead of spacing them evenly.
KNOT_U = [0.0, 0.12, 0.24, 0.34, 0.48, 0.60, 0.68, 0.78, 0.80, 0.90, 1.0]


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def _slots(cx: float, count: int) -> list[tuple[float, float]]:
    out = []
    row = 0
    while len(out) < count:
        n = 21 if row % 2 == 0 else 20
        for c in range(n):
            out.append((cx + (c - (n - 1) / 2) * BALL_R * 2, FLOOR - 4 - BALL_R - row * ROW_H))
        row += 1
    return out


def play(seed: int) -> list[dict]:
    """The games themselves: prize door, first pick, host's door, the switch door."""
    rng = np.random.default_rng(seed)
    games = []
    for _ in range(N_GAMES):
        prize, pick = int(rng.integers(3)), int(rng.integers(3))
        empty = [d for d in range(3) if d != pick and d != prize]
        host = int(empty[rng.integers(len(empty))])
        switch = 3 - pick - host
        games.append(dict(prize=prize, pick=pick, host=host, switch=switch,
                          winner="stay" if pick == prize else "switch"))
    return games


def voice_knots(lines: dict) -> tuple[list[float], dict[str, float]]:
    """Game 1's step times, set by the voice: the host's door opens on "opens",
    the switch marble moves as "Stay, or switch?" is asked. Returns the knot
    times (matching KNOT_U) and when each line starts."""
    s = START
    at = {"pick": s + 0.15}
    at["host"] = at["pick"] + lines["pick"].secs + 0.15
    k = [s, at["host"]]
    k.append(at["host"] + lines["host"].word_at("opens") - 0.05)       # 0.24: door starts opening
    k.append(k[-1] + 0.5)                                              # 0.34
    at["ask"] = max(at["host"] + lines["host"].secs + 0.2, k[-1] + 0.2)
    k.append(at["ask"])                                                # 0.48: switch marble moves
    k.append(k[-1] + 0.7)                                              # 0.60
    k.append(max(at["ask"] + lines["ask"].secs + 0.3, k[-1] + 0.15))   # 0.68: prize revealed
    k.append(k[-1] + 0.5)                                              # 0.78
    k.append(k[-1] + 0.15)                                             # 0.80: winner launches
    k.append(k[-1] + 0.9)                                              # 0.90
    k.append(k[-1] + 0.4)                                              # 1.0
    return k, at


def schedule(games: list[dict], knots: list[float] | None = None) -> None:
    """Give each game its moment (when its winner launches) and, if shown, its animation."""
    t = START
    for n, (g, dur) in enumerate(zip(games[:3], SLOW)):
        if n == 0 and knots:
            dur = knots[-1] - knots[0]
            g["knots"] = knots
        g.update(start=t, dur=dur, shown=True)
        g["launch"] = time_at(g, 0.8)
        t += dur
    n = len(games) - 3
    u = np.arange(1, n + 1) / n
    stream = t + 0.4 + STREAM_LEN * u ** (1 / STREAM_POW)
    last = games[2]
    for g, tl in zip(games[3:], stream):
        g.update(launch=float(tl), shown=False)
        prev_end = last["start"] + last["dur"]
        if tl - last["launch"] >= MIN_SHOWN_GAP:
            dur = min(1.2, (tl - prev_end) / 0.8)
            if dur >= 0.45:
                g.update(start=tl - 0.8 * dur, dur=dur, shown=True)
                last = g


def flights(games: list[dict], seed: int) -> dict:
    """Every winner's marble: hop, arc into its tube, fall, settle on the pile."""
    rng = np.random.default_rng(seed + 1)
    n = len(games)
    x0, y0 = np.zeros(n), np.full(n, float(MARK_Y))
    side = np.array([g["winner"] for g in games])
    for i, g in enumerate(games):
        if g["shown"]:
            # The winning marble sits centred under its door by launch time.
            x0[i] = DOOR_X[g["pick"] if g["winner"] == "stay" else g["switch"]]
        else:
            x0[i] = DOOR_X[g["prize"]]
    T = np.array([g["launch"] for g in games])
    tx = np.array([TUBE_X[s] for s in side])
    xm = tx + rng.uniform(-TUBE_W / 2 + 22, TUBE_W / 2 - 22, n)
    t1 = (-LAUNCH_VY + np.sqrt(LAUNCH_VY ** 2 + 2 * GRAVITY * (TUBE_TOP - y0))) / GRAVITY
    vx = (xm - x0) / t1
    va = LAUNCH_VY + GRAVITY * t1

    # Slots: in order of arrival, each marble takes the free place nearest to
    # where it entered, in the lowest row that still has room.
    xs, ys = np.zeros(n), np.zeros(n)
    for s in ("stay", "switch"):
        table = _slots(TUBE_X[s], N_GAMES)
        free_rows: dict[int, list[int]] = {}
        for k, (_, y) in enumerate(table):
            free_rows.setdefault(round((FLOOR - y) / ROW_H), []).append(k)
        idx = np.where(side == s)[0]
        for i in idx[np.argsort(T[idx] + t1[idx])]:
            row = min(r for r, ks in free_rows.items() if ks)
            ks = free_rows[row]
            best = min(ks, key=lambda k: abs(table[k][0] - xm[i]))
            ks.remove(best)
            xs[i], ys[i] = table[best]
    t2 = (-va + np.sqrt(va ** 2 + 2 * GRAVITY * (ys - TUBE_TOP))) / GRAVITY
    vland = va + GRAVITY * t2
    vb = 0.16 * vland
    t3 = 2 * vb / GRAVITY
    return dict(T=T, x0=x0, y0=y0, vx=vx, t1=t1, xm=xm, va=va, xs=xs, ys=ys, t2=t2,
                vb=vb, t3=t3, land=T + t1 + t2 + t3, side=side,
                shown=np.array([g["shown"] for g in games]))


def ball_state(f: dict, t: float):
    """Positions and radii of marbles in the air at time t (indices, x, y, r)."""
    live = np.where((f["T"] <= t) & (t < f["land"]))[0]
    if not len(live):
        return live, np.zeros(0), np.zeros(0), np.zeros(0)
    tau = t - f["T"][live]
    t1, t2 = f["t1"][live], f["t2"][live]
    x = np.empty(len(live))
    y = np.empty(len(live))
    a = tau < t1
    x[a] = f["x0"][live][a] + f["vx"][live][a] * tau[a]
    y[a] = f["y0"][live][a] + LAUNCH_VY * tau[a] + GRAVITY * tau[a] ** 2 / 2
    b = (~a) & (tau < t1 + t2)
    tb = tau[b] - t1[b]
    u = np.clip(tb / t2[b], 0, 1)
    x[b] = f["xm"][live][b] + (f["xs"][live][b] - f["xm"][live][b]) * (u * u * (3 - 2 * u))
    y[b] = TUBE_TOP + f["va"][live][b] * tb + GRAVITY * tb ** 2 / 2
    c = ~(a | b)
    tc = tau[c] - t1[c] - t2[c]
    x[c] = f["xs"][live][c]
    y[c] = np.minimum(f["ys"][live][c], f["ys"][live][c] - f["vb"][live][c] * tc + GRAVITY * tc ** 2 / 2)
    # Shown winners shrink from marker size; unshown ones pop out of the spout.
    r = np.where(f["shown"][live], MARK_R + (BALL_R - MARK_R) * np.clip(tau / 0.25, 0, 1),
                 BALL_R * np.clip(tau / 0.1, 0.25, 1))
    return live, x, y, r


# --------------------------------------------------------------------------- #
# Drawing: static board, door sprites, contents
# --------------------------------------------------------------------------- #
def _door_box(i: int) -> tuple[float, float, float, float]:
    return DOOR_X[i] - DOOR_W / 2, DOOR_Y0, DOOR_X[i] + DOOR_W / 2, DOOR_Y0 + DOOR_H


def _board() -> Image.Image:
    b = cv.Big()
    for i in range(3):
        x0, y0, x1, y1 = _door_box(i)
        b.rrect((x0 - 9, y0 - 9, x1 + 9, y1 + 4), 14, outline=scale(CYAN, 0.55),
                fill=(3, 4, 8), w=2.5)
    # Glass tubes: open-topped, rounded bottoms.
    for s, cx in TUBE_X.items():
        x0, x1 = cx - TUBE_W / 2 - 3, cx + TUBE_W / 2 + 3
        b.rrect((x0, TUBE_TOP - 60, x1, FLOOR + 3), 22, outline=scale(COL[s], 0.85), w=3.2)
        b.d.rectangle(((x0 - 10) * 3, (TUBE_TOP - 70) * 3, (x1 + 10) * 3, TUBE_TOP * 3 - 1), fill=(0, 0, 0))
        b.line([(x0 - 14, TUBE_TOP), (x0 + 4, TUBE_TOP)], scale(COL[s], 0.85), 3.2)
        b.line([(x1 - 4, TUBE_TOP), (x1 + 14, TUBE_TOP)], scale(COL[s], 0.85), 3.2)
    # A shared scale between the tubes: a tick every 100 games.
    gx0, gx1 = TUBE_X["stay"] + TUBE_W / 2 + 12, TUBE_X["switch"] - TUBE_W / 2 - 12
    for k in range(1, 9):
        y = FLOOR - 4 - k * 100 / PER_ROW * ROW_H
        if y < TUBE_TOP + 10:
            break
        b.line([(gx0, y), (gx0 + 12, y)], scale(MUTED, 0.6), 1.6)
        b.line([(gx1 - 12, y), (gx1, y)], scale(MUTED, 0.6), 1.6)
        if k % 2 == 0:
            b.text((gx0 + gx1) / 2, y, f"{k * 100}", 19, scale(MUTED, 0.85))
    img = cv.neon(b.shrink(), blur=8, gain=1.5)
    # Faint glass tint inside each tube.
    arr = np.asarray(img, np.float32).copy()
    for s, cx in TUBE_X.items():
        arr[TUBE_TOP:FLOOR, int(cx - TUBE_W / 2):int(cx + TUBE_W / 2)] += np.array(COL[s], np.float32) * 0.035
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return cv.title(img, TITLE)


M = 30                           # sprite margin around a door, for glow and perspective


def _door_sprite(num: int, f: float) -> Image.Image:
    """The door panel, open by fraction f (0 shut .. 1 swung ~80 degrees), as RGBA."""
    ss = 3
    w, h = DOOR_W + 2 * M, DOOR_H + 2 * M
    theta = f * math.radians(80)
    x0, y0 = M, M
    wd = DOOR_W * math.cos(theta)
    dy = 20 * math.sin(theta)

    def pt(u: float, v: float) -> tuple[float, float]:
        return ((x0 + u * wd) * ss, (y0 - dy * u + v * (DOOR_H + 2 * dy * u)) * ss)

    fill_m = Image.new("L", (w * ss, h * ss), 0)
    line_m = Image.new("L", (w * ss, h * ss), 0)
    inset_m = Image.new("L", (w * ss, h * ss), 0)
    num_m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(fill_m).polygon([pt(0, 0), pt(1, 0), pt(1, 1), pt(0, 1)], fill=255)
    ImageDraw.Draw(line_m).line([pt(0, 0), pt(1, 0), pt(1, 1), pt(0, 1), pt(0, 0)],
                                fill=255, width=3 * ss, joint="curve")
    di = ImageDraw.Draw(inset_m)
    for va, vb in ((0.08, 0.42), (0.5, 0.92)):
        di.line([pt(0.14, va), pt(0.86, va), pt(0.86, vb), pt(0.14, vb), pt(0.14, va)],
                fill=255, width=2 * ss, joint="curve")
    kx, ky = pt(0.85, 0.47)
    kr = 6 * ss * max(0.3, math.cos(theta))
    di.ellipse((kx - kr, ky - kr, kx + kr, ky + kr), fill=255)
    if f < 0.6:
        cx, cy = pt(0.5, 0.25)
        ImageDraw.Draw(num_m).text((cx, cy), str(num), font=cv.font(62 * ss), fill=int(255 * (1 - f / 0.6)),
                                   anchor="mm")

    def arr(m: Image.Image) -> np.ndarray:
        return np.asarray(m.resize((w, h), Image.LANCZOS), np.float32) / 255

    a_fill, a_line, a_in, a_num = arr(fill_m), arr(line_m), arr(inset_m) * 0.75, arr(num_m)
    shade = 1 - 0.55 * f
    fill_col = np.array(mix((18, 28, 58), (30, 46, 86), 0.4), np.float32) * shade
    line_col = np.array(mix(CYAN, WHITE, 0.35), np.float32) * (1 - 0.35 * f)
    in_col = np.array(scale(CYAN, 0.6), np.float32) * shade
    num_col = np.array(WHITE, np.float32) * 0.92

    C = fill_col * a_fill[..., None]
    A = a_fill.copy()
    for a, col in ((a_in, in_col), (a_num, num_col), (a_line, line_col)):
        C = C * (1 - a[..., None]) + col * a[..., None]
        A = np.maximum(A, a)
    g = np.asarray(Image.fromarray((a_line * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(7)),
                   np.float32) / 255 * 0.85
    glow = g * (1 - A)
    C = C + np.array(CYAN, np.float32) * glow[..., None]
    A = A + glow
    rgb = C / np.maximum(A[..., None], 1e-4)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(A * 255, 0, 255)]).astype(np.uint8), "RGBA")


def _star(r: float, color, ss: int = 4) -> Image.Image:
    """A glowing five-point star (the prize) on a soft gold halo."""
    size = int(r * 4.2) | 1
    c = size / 2
    halo = np.asarray(cv.halo_sprite(size // 2, color, 0.55), np.float32)
    big = Image.new("L", (size * ss, size * ss), 0)
    core = Image.new("L", (size * ss, size * ss), 0)

    def poly(rad: float):
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rr = rad if k % 2 == 0 else rad * 0.45
            pts.append(((c + rr * math.cos(a)) * ss, (c + 0.04 * rad + rr * math.sin(a)) * ss))
        return pts

    ImageDraw.Draw(big).polygon(poly(r), fill=255)
    ImageDraw.Draw(core).polygon(poly(r * 0.5), fill=255)
    a = np.asarray(big.resize((size, size), Image.LANCZOS), np.float32) / 255
    k = np.asarray(core.resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
    col = np.array(color, np.float32) * (1 - k[..., None] * 0.6) + np.array(WHITE, np.float32) * k[..., None] * 0.6
    ha = halo[..., 3] / 255
    C = halo[..., :3] * ha[..., None] * (1 - a[..., None]) + col * a[..., None]
    A = np.maximum(a, ha)
    rgb = C / np.maximum(A[..., None], 1e-4)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(A * 255, 0, 255)]).astype(np.uint8), "RGBA")


def _cross(size: int = 70) -> Image.Image:
    """An empty door: a dim cross."""
    ss = 4
    m = Image.new("L", (size * ss, size * ss), 0)
    d = ImageDraw.Draw(m)
    p, q = 0.3 * size * ss, 0.7 * size * ss
    d.line([(p, p), (q, q)], fill=255, width=5 * ss)
    d.line([(p, q), (q, p)], fill=255, width=5 * ss)
    a = m.resize((size, size), Image.LANCZOS)
    col = Image.new("RGB", (size, size), mix(MUTED, (40, 46, 64), 0.35))
    col.putalpha(a)
    return col


# --------------------------------------------------------------------------- #
# Per-frame state of the shown game
# --------------------------------------------------------------------------- #
def _u(t: float, g: dict) -> float:
    if "knots" in g:
        return float(np.interp(t, g["knots"], KNOT_U, left=-1.0, right=1.0))
    return (t - g["start"]) / g["dur"]


def time_at(g: dict, u: float) -> float:
    """When game g reaches step u (the inverse of _u)."""
    if "knots" in g:
        return float(np.interp(u, KNOT_U, g["knots"]))
    return g["start"] + u * g["dur"]


def _door_open(g: dict, u: float, i: int) -> float:
    close = 1 - cv.ease((u - 0.9) / 0.1)
    if i == g["host"]:
        return cv.ease((u - 0.24) / 0.1) * close
    return cv.ease((u - 0.68) / 0.1) * close


def _markers(g: dict, u: float):
    """(side, x, y, r, glow) for the two players' marbles of a shown game."""
    out = []
    appear = cv.ease_out(u / 0.1)
    move = cv.ease((u - 0.48) / 0.12)
    xp, xsw = DOOR_X[g["pick"]], DOOR_X[g["switch"]]
    for side, x_from, x_to in (("stay", xp - MARK_DX, xp), ("switch", xp + MARK_DX, xsw)):
        x = x_from + (x_to - x_from) * move
        lift = -46 * math.sin(math.pi * move) if side == "switch" else 0.0
        won = g["winner"] == side
        if u >= 0.8 and won:
            continue                                  # it has launched: now a flying marble
        r = MARK_R * appear
        if u >= 0.8:                                  # the loser fades away
            r *= 1 - cv.ease((u - 0.8) / 0.1)
        glow = cv.ease((u - 0.7) / 0.08) if won else 0.0
        if r > 0.5:
            out.append((side, x, MARK_Y + lift, r, glow))
    return out


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #
def _soundtrack(games, f, t_reveal: float, total: float, path: Path, seed: int,
                clips: list | None = None) -> None:
    rng = np.random.default_rng(seed + 2)
    mixer = snd.Mixer(total)
    door = snd.thud(74, 0.3)
    swish = snd.pluck(330, dur=0.25, bright=0.3)
    for g in games:
        if not g["shown"]:
            continue
        gain = 0.55 if g["dur"] > 1.5 else 0.3
        mixer.add(time_at(g, 0.24), door, gain, (DOOR_X[g["host"]] - CX) / 400)
        if g["dur"] > 1.5:
            mixer.add(time_at(g, 0.48), swish, 0.18, 0.3)
        mixer.add(time_at(g, 0.68), door, gain * 0.8, 0.0)

    # Each result: the winner's note. Stay sits low, switch high.
    T = f["T"]
    gains = snd.density_gains(T, base=0.5, window=0.1, calm=1.4)
    notes = {s: [snd.pluck(snd.scale_freq(i), dur=0.7, bright=0.8) for i in idx]
             for s, idx in (("stay", (5, 7, 9)), ("switch", (10, 12, 14)))}
    for i, g in enumerate(games):
        boost = 1.6 if g["shown"] and g["dur"] > 1.5 else 1.0
        mixer.add(T[i], notes[g["winner"]][rng.integers(3)], gains[i] * boost,
                  -0.55 if g["winner"] == "stay" else 0.55)
    click = snd.thud(150, 0.12)
    tick = snd.pluck(2300, dur=0.06, bright=0.2)
    click[: len(tick)] += tick * 0.5
    for t, g_, s in zip(f["land"], snd.density_gains(f["land"], base=0.24, calm=1.2), f["side"]):
        mixer.add(t, click, g_, -0.5 if s == "stay" else 0.5)
    for j, n in enumerate([10, 12, 14, 15, 17, 19]):
        mixer.add(t_reveal + j * 0.18, snd.pluck(snd.scale_freq(n), dur=1.4), 0.85, 0.4)
    mixer.add(t_reveal + 1.1, snd.chord([snd.scale_freq(i) for i in (10, 12, 14, 15)],
                                        dur=total - t_reveal), 1.4)
    if clips:
        voice.voice_over(mixer, clips, bed=0.5)
    mixer.write(path, total)


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(out_path: Path, ffmpeg: str, seed: int = 7, progress=None) -> float:
    lines = {k: voice.say(s, ffmpeg) for k, s in
             (("pick", SAY_PICK), ("host", SAY_HOST), ("ask", SAY_ASK), ("why", SAY_WHY))}
    knots, said_at = voice_knots(lines)
    games = play(seed)
    schedule(games, knots)
    f = flights(games, seed)
    t_reveal = float(f["land"].max()) + 0.5
    said_at["why"] = t_reveal + 0.5
    total = max(t_reveal + 4.8, said_at["why"] + lines["why"].secs + 1.1)
    clips = [(said_at[k], lines[k]) for k in ("pick", "host", "ask", "why")]
    n_frames = int(total * FPS)

    board = _board()
    doors = {(i, k): _door_sprite(i + 1, k / 24) for i in range(3) for k in range(25)}
    star, star_big = _star(40, GOLD), _star(46, GOLD)
    cross = _cross()
    sprites = {r: cv.Sprites([CYAN, PINK], r) for r in range(2, 13)}
    mark_halo = {s: cv.halo_sprite(40, COL[s], 0.75) for s in COL}
    win_halo = cv.halo_sprite(130, GOLD, 0.35)

    f_score, f_num, f_pct = cv.font(34), cv.font(56), cv.font(30, bold=False)
    f_cap, f_small = cv.font(38), cv.font(22)
    f_pay, f_pay2, f_frac = cv.font(64), cv.font(36, bold=False), cv.font(40)

    shown = [g for g in games if g["shown"]]
    order = np.argsort(f["land"])
    land_sorted = f["land"][order]
    pasted = 0
    T = f["T"]
    stay_win = np.array([g["winner"] == "stay" for g in games])
    cum_stay = np.cumsum(stay_win)

    def paste_ball(img, side, x, y, r):
        sp = sprites[int(min(12, max(2, round(r))))]
        sp.paste(img, COL[side], x, y)

    with tempfile.TemporaryDirectory() as tmp:
        silent = Path(tmp) / "video.mp4"
        enc = cv.Encoder(silent, ffmpeg, fps=FPS)
        for fi in range(n_frames):
            t = fi / FPS
            # Settled marbles join the board.
            while pasted < len(order) and land_sorted[pasted] <= t:
                j = order[pasted]
                paste_ball(board, f["side"][j], f["xs"][j], f["ys"][j], BALL_R)
                pasted += 1
            img = board.copy()

            fade = 1 - cv.ease((t - t_reveal) / 0.6)          # doors dim for the payoff
            g = next((s for s in shown if s["start"] <= t < s["start"] + s["dur"]), None)

            # Doors and what is behind them.
            for i in range(3):
                x0, y0, x1, y1 = _door_box(i)
                fo = _door_open(g, _u(t, g), i) if g else 0.0
                if fo > 0.02 and g:
                    if i == g["prize"]:
                        pulse = 1 + 0.12 * math.sin(math.pi * min(1, max(0, (_u(t, g) - 0.68) / 0.12)))
                        if fo > 0.5:
                            cv.add_rgba(img, win_halo, DOOR_X[i], (y0 + y1) / 2)
                        spr = star_big if pulse > 1.06 else star
                        cv.add_rgba(img, spr, DOOR_X[i], (y0 + y1) / 2)
                    else:
                        cv.add_rgba(img, cross, DOOR_X[i], (y0 + y1) / 2)
                spr = doors[(i, int(round(fo * 24)))]
                img.paste(spr, (int(x0 - M), int(y0 - M)), spr)

            # The two players' marbles.
            if g:
                u = _u(t, g)
                for side, x, y, r, glow in _markers(g, u):
                    if glow > 0:
                        h = mark_halo[side]
                        a = h.copy()
                        a.putalpha(a.getchannel("A").point(lambda v, k=glow: int(v * k)))
                        cv.add_rgba(img, a, x, y)
                    paste_ball(img, side, x, y, r)

            # Flying marbles.
            live, bx, by, br = ball_state(f, t)
            for j, x, y, r in zip(live, bx, by, br):
                paste_ball(img, f["side"][j], x, y, r)

            if fade < 1:
                arr = np.asarray(img, np.float32)
                band = arr[DOOR_Y0 - 40:MARK_Y + 30]
                band[:] = cv.BG + (band - cv.BG) * (0.04 + 0.96 * fade)
                img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            d = ImageDraw.Draw(img)

            # Scoreboard over each tube.
            n_done = int(np.searchsorted(T, t, side="right"))
            stay_n = int(cum_stay[n_done - 1]) if n_done else 0
            counts = {"stay": stay_n, "switch": n_done - stay_n}
            for s in ("stay", "switch"):
                cx = TUBE_X[s]
                lab = s.upper() + "  "
                num = f"{counts[s]:,}"
                lw, nw = f_score.getlength(lab), f_num.getlength(num)
                x0 = cx - (lw + nw) / 2
                d.text((x0, cv.LINE_Y + 4), lab, font=f_score, fill=COL[s], anchor="lm")
                d.text((x0 + lw, cv.LINE_Y), num, font=f_num, fill=WHITE, anchor="lm")
                if n_done:
                    pct = 100 * counts[s] / n_done
                    d.text((cx, cv.SUB_Y + 4), f"wins {pct:.1f}%", font=f_pct, fill=MUTED, anchor="mm")

            # Captions: the rules during game 1, then a games counter.
            g1 = games[0]
            u1 = _u(t, g1)
            if 0 <= u1 < 1:
                for a0, a1, text in CAPTIONS:
                    if a0 <= u1 < a1:
                        k = min(cv.ease((u1 - a0) / 0.04), 1 - cv.ease((u1 - a1 + 0.04) / 0.04))
                        d.text((CX, 398), text, font=f_cap, fill=mix(cv.BG, WHITE, k), anchor="mm")
                if u1 >= 0.8:
                    k = min(cv.ease((u1 - 0.8) / 0.04), 1 - cv.ease((u1 - 0.96) / 0.04))
                    d.text((CX, 398), f"{g1['winner'].title()} wins!", font=f_cap,
                           fill=mix(cv.BG, COL[g1["winner"]], k), anchor="mm")
                # Name the two marbles while they are new.
                together = u1 < 0.5          # side by side under one door: push labels apart
                for side, x, y, r, _ in _markers(g1, u1):
                    if r > 4:
                        anchor = ("rm" if side == "stay" else "lm") if together else "mm"
                        dx = (8 if side == "stay" else -8) if together else 0
                        d.text((x + dx, y + 30), side, font=f_small,
                               fill=mix(cv.BG, COL[side], min(1, r / MARK_R)), anchor=anchor)
            elif t >= games[1]["start"] and fade > 0:
                k = cv.ease((t - games[1]["start"]) / 0.4) * fade
                lab, num = "games played: ", f"{n_done:,}"
                lw, nw = f_cap.getlength(lab), f_cap.getlength(num)
                x0 = CX - (lw + nw) / 2
                d.text((x0, 398), lab, font=f_cap, fill=mix(cv.BG, MUTED, k), anchor="lm")
                d.text((x0 + lw, 398), num, font=f_cap, fill=mix(cv.BG, GOLD, k), anchor="lm")

            # Payoff.
            if t >= t_reveal:
                a = cv.ease((t - t_reveal - 0.3) / 0.6)
                d.text((CX, 540), "Switching wins", font=f_pay, fill=mix(cv.BG, GOLD, a), anchor="mm")
                d.text((CX, 618), "2 out of 3 games", font=f_pay, fill=mix(cv.BG, GOLD, a), anchor="mm")
                d.text((CX, 692), "Staying wins only 1 in 3", font=f_pay2, fill=mix(cv.BG, MUTED, a), anchor="mm")
                # Where exactly 1/3 and 2/3 of the games would reach.
                w = cv.ease((t - t_reveal - 0.9) / 0.8)
                for s, frac, label, lx in (("stay", 1 / 3, "⅓", TUBE_X["stay"] - TUBE_W / 2 - 34),
                                           ("switch", 2 / 3, "⅔", TUBE_X["switch"] + TUBE_W / 2 + 34)):
                    y = FLOOR - 4 - frac * N_GAMES / PER_ROW * ROW_H - BALL_R
                    xa = TUBE_X[s] - TUBE_W / 2 - 8
                    xb = xa + (TUBE_W + 16) * w
                    for xx in np.arange(xa, xb, 18):
                        d.line([(xx, y), (min(xx + 10, xb), y)], fill=GOLD, width=4)
                    if w > 0:
                        d.text((lx, y), label, font=f_frac, fill=mix(cv.BG, GOLD, w), anchor="mm")

            enc.write(np.asarray(img))
            if progress and fi % 60 == 0:
                progress(fi, n_frames)
        enc.close()
        wav = Path(tmp) / "sound.wav"
        _soundtrack(games, f, t_reveal, total, wav, seed, clips)
        cv.mux(silent, wav, Path(out_path), ffmpeg)
    return total
