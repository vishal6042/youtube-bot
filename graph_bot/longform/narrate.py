"""Narration for long-form chapters, using the free Edge neural voices.

The Shorts pipeline only speaks inside Manim scenes (manim-voiceover). Chart
chapters need plain audio with timings, so this talks to edge-tts directly and
returns the sentence cues, which become the episode's subtitle file.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

from ..render import ffmpeg_exe

DEFAULT_VOICE = "en-IN-NeerjaNeural"
_TICKS = 10_000_000  # edge-tts reports offsets in 100-nanosecond units


async def _synth(text: str, voice: str, out_path: Path, rate: str) -> list[dict[str, Any]]:
    import edge_tts

    cues: list[dict[str, Any]] = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="SentenceBoundary")
    with out_path.open("wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                start = chunk["offset"] / _TICKS
                cues.append({"start": start, "end": start + chunk["duration"] / _TICKS,
                             "text": chunk["text"]})
    return cues


def audio_seconds(path: Path, settings: dict[str, Any]) -> float:
    """Length of an audio/video file, read from ffmpeg's own header dump."""
    proc = subprocess.run([ffmpeg_exe(settings), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        raise RuntimeError(f"Could not read the length of {path.name}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def speak(text: str, voice: str, out_path: Path, settings: dict[str, Any],
          rate: str = "+0%") -> tuple[float, list[dict[str, Any]]]:
    """Synthesize ``text`` to ``out_path`` (mp3). Returns (seconds, sentence cues)."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("Nothing to say: the chapter has no narration")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cues = asyncio.run(_synth(text, voice or DEFAULT_VOICE, out_path, rate or "+0%"))
    except Exception as exc:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"The narration service did not return audio ({type(exc).__name__}: {exc}). "
            "It needs an internet connection; check the voice name too."
        ) from exc
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"The narration service returned no audio for voice '{voice}'")
    return audio_seconds(out_path, settings), cues
