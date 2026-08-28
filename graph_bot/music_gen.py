"""Procedural ambient music generator with selectable moods.

Synthesizes ORIGINAL soothing background music from scratch with numpy — no
samples, no models, no downloads. Copyright-free by construction.

Each mood is a small parameter preset (scale, register, pace, brightness, reverb,
optional soft beat). The pipeline auto-picks a mood per topic (see audio.infer_mood).

CLI:
    python -m graph_bot.music_gen --mood hopeful --seed 3 --duration 40 -o out.wav
    python -m graph_bot.music_gen --list
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 44100

MINOR_PENT = [0, 3, 5, 7, 10]
MAJOR_PENT = [0, 2, 4, 7, 9]

# mood -> synthesis parameters
STYLES: dict[str, dict] = {
    "calm":       dict(scale="minor", root=57, segs=4, mel_gap=(2.0, 3.5), mel_oct=[12, 24], bright=1.0, reverb=1.0, lp=9,  sub=0.18, beat=None),
    "hopeful":    dict(scale="major", root=60, segs=5, mel_gap=(1.2, 2.4), mel_oct=[12, 24], bright=1.3, reverb=0.8, lp=7,  sub=0.15, beat=None),
    "reflective": dict(scale="minor", root=50, segs=3, mel_gap=(3.0, 5.0), mel_oct=[12],     bright=0.7, reverb=1.3, lp=15, sub=0.30, beat=None),
    "majestic":   dict(scale="major", root=53, segs=4, mel_gap=(2.5, 4.0), mel_oct=[12, 24], bright=1.2, reverb=1.3, lp=7,  sub=0.26, beat=None),
    "serene":     dict(scale="major", root=57, segs=5, mel_gap=(1.5, 2.8), mel_oct=[12, 24], bright=1.4, reverb=0.9, lp=7,  sub=0.15, beat=None),
    "lofi":       dict(scale="minor", root=55, segs=4, mel_gap=(1.5, 3.0), mel_oct=[12],     bright=0.9, reverb=0.7, lp=11, sub=0.22, beat=75),
}
DEFAULT_MOOD = "calm"


def _midi_to_freq(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return x * (peak / m)


def _delay(x: np.ndarray, seconds: float, gain: float) -> np.ndarray:
    d = int(seconds * SR)
    if d <= 0 or d >= len(x):
        return np.zeros_like(x)
    y = np.zeros_like(x)
    y[d:] = x[:-d] * gain
    return y


def _pad_layer(n: int, roots: list[int], bright: float) -> np.ndarray:
    pad = np.zeros(n)
    nseg = max(2, len(roots))
    seg = n // nseg
    win_len = seg * 2
    window = np.hanning(win_len)
    tt = np.arange(win_len) / SR
    for i in range(nseg + 1):
        root = roots[i % len(roots)]
        chord = np.zeros(win_len)
        for note in (root, root + 7, root + 12):
            f = _midi_to_freq(note)
            chord += (np.sin(2 * np.pi * f * tt)
                      + 0.4 * bright * np.sin(2 * np.pi * 2 * f * tt)
                      + 0.2 * bright * np.sin(2 * np.pi * 3 * f * tt))
        chord *= window / 3.0
        start = i * seg - seg // 2
        a, b = max(0, start), min(n, start + win_len)
        if b > a:
            pad[a:b] += chord[a - start:b - start]
    return pad


def _melody_layer(n, root, rng, scale, mel_gap, mel_oct, bright) -> np.ndarray:
    mel = np.zeros(n)
    duration = n / SR
    t_cur = 1.0
    while t_cur < duration - 1.0:
        octave = int(rng.choice(mel_oct))
        midi = root + octave + scale[int(rng.integers(len(scale)))]
        f = _midi_to_freq(midi)
        note_len = int(rng.uniform(0.8, 1.6) * SR)
        idx = int(t_cur * SR)
        avail = min(note_len, n - idx)
        if avail > 0:
            tt = np.arange(avail) / SR
            env = np.exp(-tt * 3.0)
            note = (np.sin(2 * np.pi * f * tt) + 0.3 * bright * np.sin(2 * np.pi * 2 * f * tt)) * env
            mel[idx:idx + avail] += note
        t_cur += rng.uniform(*mel_gap)
    return mel


def _beat_layer(n, bpm, rng) -> np.ndarray:
    out = np.zeros(n)
    spb = 60.0 / bpm
    nbeats = int((n / SR) / spb)
    for b in range(nbeats):
        t0 = b * spb
        # soft kick on the beat
        idx = int(t0 * SR)
        klen = min(int(0.18 * SR), n - idx)
        if klen > 0:
            tt = np.arange(klen) / SR
            kick = np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 18)
            out[idx:idx + klen] += kick * 0.9
        # soft hat on the off-beat
        idx2 = int((t0 + spb / 2) * SR)
        hlen = min(int(0.05 * SR), n - idx2)
        if hlen > 0 and idx2 >= 0:
            hat = rng.standard_normal(hlen) * np.exp(-np.arange(hlen) / SR * 80)
            out[idx2:idx2 + hlen] += hat * 0.12
    return out


def generate(duration: float, seed: int, out_path: Path, mood: str = DEFAULT_MOOD) -> Path:
    style = STYLES.get(mood, STYLES[DEFAULT_MOOD])
    scale = MAJOR_PENT if style["scale"] == "major" else MINOR_PENT
    rng = np.random.default_rng(seed)

    n = int(duration * SR)
    t = np.arange(n) / SR
    root = style["root"]
    pool = np.array([0, 5, 7, 3, 10])
    roots = [root + int(o) for o in rng.permutation(pool)[:style["segs"]]]

    pad = _pad_layer(n, roots, style["bright"])
    mel = _melody_layer(n, root, rng, scale, style["mel_gap"], style["mel_oct"], style["bright"])
    f_sub = _midi_to_freq(root - 12)
    sub = np.sin(2 * np.pi * f_sub * t) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.1 * t))

    mix = 0.5 * _norm(pad) + 0.28 * _norm(mel) + style["sub"] * sub
    if style["beat"]:
        mix += 0.22 * _norm(_beat_layer(n, style["beat"], rng))

    rv = style["reverb"]
    mix = mix + _delay(mix, 0.09, 0.35 * rv) + _delay(mix, 0.15, 0.25 * rv) + _delay(mix, 0.23, 0.18 * rv)

    k = np.hanning(style["lp"])
    k /= k.sum()
    mix = np.convolve(mix, k, mode="same")

    fade = int(min(1.5, duration / 4) * SR)
    if fade > 0:
        env = np.ones(n)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        mix *= env

    mix = _norm(mix, 0.9)
    right = _delay(mix, 0.008, 0.95)
    right[:int(0.008 * SR)] = mix[:int(0.008 * SR)] * 0.95
    stereo = _norm(np.stack([mix, right], axis=1), 0.9)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = (stereo * 32767).astype("<i2")
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a mood-based ambient track.")
    parser.add_argument("--mood", default=DEFAULT_MOOD, choices=list(STYLES))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("-o", "--out", help="Output .wav path")
    parser.add_argument("--list", action="store_true", help="List moods and exit")
    args = parser.parse_args()
    if args.list:
        print("Moods:", ", ".join(STYLES))
        return
    if not args.out:
        parser.error("-o/--out is required unless --list")
    generate(args.duration, args.seed, Path(args.out), args.mood)
    print(f"Wrote {args.out} ({args.duration:.0f}s, mood={args.mood}, seed={args.seed})")


if __name__ == "__main__":
    main()
