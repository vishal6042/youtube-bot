"""Short voice-over for simulated Shorts: a line or two, never narration throughout.

Uses the same free Edge neural voice as the long-form videos. Each line is
synthesised once and cached under data/cache/voice (keyed by text, voice and
rate), so re-renders are identical and need no internet. Word timings come back
too, so a sim can time an event to a spoken word.

While the voice speaks, the simulation's own sounds dip so every word is clear.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from ..config import PROJECT_ROOT
from . import sound as snd

VOICE = "en-IN-NeerjaNeural"
RATE = "+5%"
CACHE = PROJECT_ROOT / "data" / "cache" / "voice"


class Line:
    """One spoken line: mono samples at sound.SR, its length and word timings."""

    def __init__(self, text: str, samples: np.ndarray, words: list[dict[str, Any]]):
        self.text, self.samples, self.words = text, samples, words
        self.secs = len(samples) / snd.SR

    def word_at(self, word: str) -> float:
        """Seconds into the line where `word` starts (first match, case-insensitive)."""
        w = word.lower()
        for c in self.words:
            if c["text"].lower().strip(".,!?;:").startswith(w):
                return float(c["start"])
        raise KeyError(f"'{word}' is not in: {self.text}")


def say(text: str, ffmpeg: str, voice: str = VOICE, rate: str = RATE) -> Line:
    text = " ".join(text.split())
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:16]
    mp3, meta = CACHE / f"{key}.mp3", CACHE / f"{key}.json"
    if not (mp3.exists() and meta.exists()):
        import asyncio

        from ..longform.narrate import _synth

        CACHE.mkdir(parents=True, exist_ok=True)
        try:
            words = asyncio.run(_synth(text, voice, mp3, rate, "WordBoundary"))
        except Exception as exc:
            mp3.unlink(missing_ok=True)
            raise RuntimeError(f"Voice-over failed ({type(exc).__name__}: {exc}). "
                               "The first render of a new line needs an internet connection.") from exc
        meta.write_text(json.dumps({"text": text, "words": words}, ensure_ascii=False), encoding="utf-8")
    words = json.loads(meta.read_text(encoding="utf-8"))["words"]
    pcm = subprocess.run([ffmpeg, "-loglevel", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
                          "-ar", str(snd.SR), "-"], capture_output=True, check=True).stdout
    samples = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    # Trim the silence edge-tts leaves at the end, keep a short tail.
    loud = np.where(np.abs(samples) > 0.01)[0]
    if len(loud):
        samples = samples[: min(len(samples), loud[-1] + int(0.08 * snd.SR))]
    peak = float(np.abs(samples).max()) or 1.0
    return Line(text, samples / peak * 0.9, words)


def voice_over(mixer: snd.Mixer, clips: list[tuple[float, Line]], duck: float = 0.28,
               gain: float = 1.0, bed: float = 1.0) -> None:
    """Dip everything already in the mix while each line plays, then add the lines.

    `bed` scales the whole simulation sound first: below 1 for sims whose busy
    middle is louder than the voice (the final loudness pass would otherwise
    turn the voice down to match it)."""
    n = len(mixer.buf)
    env = np.ones(n, np.float32)
    ramp = int(0.18 * snd.SR)
    for t, line in clips:
        a = max(0, int((t - 0.12) * snd.SR))
        b = min(n, int((t + line.secs + 0.1) * snd.SR))
        env[a:b] = duck
        # Smooth edges so the dip never clicks.
        lo = max(0, a - ramp)
        env[lo:a] = np.minimum(env[lo:a], np.linspace(1, duck, a - lo, dtype=np.float32))
        hi = min(n, b + ramp)
        env[b:hi] = np.minimum(env[b:hi], np.linspace(duck, 1, hi - b, dtype=np.float32))
    mixer.buf *= (env * bed)[:, None]
    for t, line in clips:
        mixer.add(t, line.samples, gain, 0.0)
