"""Event sounds for simulated Shorts: soft plucks placed at exact event times.

Every bounce, landing or reveal is a timestamped event from the simulation, so
the soundtrack is built by dropping a short synthesised note at each one. When
events crowd together (hundreds of bounces a second) each note is turned down,
so a busy board becomes a shimmer instead of a roar.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100

# A minor pentatonic from A2: any mix of these notes sounds consonant.
_PENTA = [0, 3, 5, 7, 10]


def scale_freq(i: int, base: float = 110.0) -> float:
    octave, step = divmod(i, len(_PENTA))
    return base * 2 ** (octave + _PENTA[step] / 12)


def pluck(freq: float, dur: float = 0.45, bright: float = 1.0) -> np.ndarray:
    """A marimba-like note: fast attack, quick decay, a little upper harmonic."""
    t = np.arange(int(SR * dur)) / SR
    attack = 1 - np.exp(-t * 900)
    tone = (np.sin(2 * np.pi * freq * t) * np.exp(-t * 9)
            + 0.35 * bright * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 22)
            + 0.12 * bright * np.sin(2 * np.pi * 4.2 * freq * t) * np.exp(-t * 45))
    return (tone * attack).astype(np.float32)


def thud(freq: float = 90.0, dur: float = 0.18) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    return (np.sin(2 * np.pi * freq * t * (1 - 0.3 * t)) * np.exp(-t * 28)
            * (1 - np.exp(-t * 1500))).astype(np.float32)


def chord(freqs: list[float], dur: float = 3.0) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    env = (1 - np.exp(-t * 6)) * np.exp(-t * 0.9)
    out = sum(np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) for f in freqs)
    return (out * env / len(freqs)).astype(np.float32)


class Mixer:
    def __init__(self, seconds: float):
        self.buf = np.zeros((int(SR * seconds) + SR, 2), dtype=np.float32)

    def add(self, t: float, sample: np.ndarray, gain: float = 0.3, pan: float = 0.0) -> None:
        """Place `sample` at time t; pan -1 (left) .. 1 (right)."""
        i = int(t * SR)
        if i >= len(self.buf):
            return
        s = sample[: len(self.buf) - i] * gain
        self.buf[i:i + len(s), 0] += s * np.sqrt((1 - pan) / 2)
        self.buf[i:i + len(s), 1] += s * np.sqrt((1 + pan) / 2)

    def write(self, path: Path, seconds: float) -> None:
        out = self.buf[: int(SR * seconds)]
        out = np.tanh(out * 1.2)                       # soft limit, no hard clipping
        out = out / max(1e-6, np.abs(out).max()) * 0.89  # about -1 dBFS
        pcm = (out * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


def density_gains(times: np.ndarray, base: float, window: float = 0.08, calm: float = 2.0) -> np.ndarray:
    """Per-event gain (same order as `times`): `base` when events are sparse,
    lower as they crowd."""
    times = np.asarray(times, dtype=np.float64)
    st = np.sort(times)
    crowd = (np.searchsorted(st, times + window / 2) - np.searchsorted(st, times - window / 2))
    return base / np.sqrt(np.maximum(1.0, crowd.astype(np.float32) / calm))
