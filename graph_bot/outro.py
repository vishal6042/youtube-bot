"""A short spoken sign-off ("Subscribe for more.") at the end of every Short.

It plays over the video's last image instead of a separate end card: the final
frame is held for about a second while the line is spoken, and the video's own
sound dips under it. The line is said in the video's own voice where it has one
(a sim's VOICE, a Manim scene's narrator), else in the default from settings.

Settings live under ``outro:`` in config/settings.yaml. A topic can turn it off
with ``outro: false``, change the words with ``outro: "..."``, or pick the
voice with ``outro_voice`` / ``outro_rate``. Loop-length Shorts (under
``min_seconds``) are left alone: there a replay is worth more than the ask.

Long-form videos and the Shorts cut from them have their own closing lines.
"""
from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np

from .render import ffmpeg_exe, h264_args

RAMP = 0.25          # seconds for the video's sound to dip under the line
SPEECH_RMS = 0.2     # level of the line before the final pass: ~1 dB under the sims' own narration


def _conf(settings: dict[str, Any]) -> dict[str, Any]:
    return dict(settings.get("outro") or {})


def _duration(video: Path, settings: dict[str, Any]) -> float:
    err = subprocess.run([ffmpeg_exe(settings), "-i", str(video)], capture_output=True,
                         text=True, encoding="utf-8", errors="replace").stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _has_audio(video: Path, settings: dict[str, Any]) -> bool:
    err = subprocess.run([ffmpeg_exe(settings), "-i", str(video)], capture_output=True,
                         text=True, encoding="utf-8", errors="replace").stderr
    return "Audio:" in err


def voice_for(topic: dict[str, Any], settings: dict[str, Any]) -> tuple[str, str]:
    """The video's own narrator if it has one, else the default outro voice."""
    conf = _conf(settings)
    voice, rate = conf.get("voice", "en-US-AndrewMultilingualNeural"), conf.get("rate", "+0%")
    if topic.get("mode") == "sim":
        import importlib

        from .sims import SIMS, kit

        mod = importlib.import_module(SIMS[topic["sim"]])
        voice, rate = getattr(mod, "VOICE", kit.VOICE), getattr(mod, "RATE", kit.RATE)
    elif topic.get("mode") == "manim":
        from .scenes._base import DEFAULT_VOICE

        voice = DEFAULT_VOICE
    return topic.get("outro_voice") or voice, topic.get("outro_rate") or rate


def text_for(topic: dict[str, Any], settings: dict[str, Any], duration: float) -> str | None:
    """The line to say, or None when this video gets no outro."""
    conf = _conf(settings)
    if not conf.get("enabled", True) or topic.get("outro") is False:
        return None
    if duration < float(conf.get("min_seconds", 15)):
        return None
    own = topic.get("outro")
    return own if isinstance(own, str) and own.strip() else conf.get("text", "Subscribe for more.")


class Outro:
    """One planned sign-off: `extend()` before the music, `mix()` after it."""

    def __init__(self, topic: dict[str, Any], settings: dict[str, Any], video: Path, duration: float):
        from .sims import voice as vo

        conf = _conf(settings)
        self.settings, self.video = settings, Path(video)
        text = text_for(topic, settings, duration)
        name, rate = voice_for(topic, settings)
        self.line = vo.say(text, ffmpeg_exe(settings), voice=name, rate=rate)
        end = _duration(self.video, settings)
        overlap = float(conf.get("overlap", 0.5))   # start this far inside the video's own ending
        tail = float(conf.get("tail", 0.45))         # hold after the last word
        self.at = max(0.0, end - overlap)
        self.hold = max(0.0, self.at + self.line.secs + tail - end)
        self.total = end + self.hold

    def extend(self) -> float:
        """Hold the last frame (and pad any sound with silence). Returns the new length."""
        if self.hold <= 0:
            return self.total
        s = self.settings
        tmp = self.video.with_suffix(".hold.mp4")
        cmd = [ffmpeg_exe(s), "-y", "-loglevel", "error", "-i", str(self.video),
               "-vf", f"tpad=stop_mode=clone:stop_duration={self.hold:.3f},format=yuv420p",
               *h264_args(s)]
        if _has_audio(self.video, s):
            cmd += ["-af", f"apad=pad_dur={self.hold:.3f}", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-t", f"{self.total:.3f}", str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True)
        tmp.replace(self.video)
        return self.total

    def mix(self) -> None:
        """Speak the line over the ending, dipping the video's own sound under it."""
        from .sims import sound as snd

        s, conf = self.settings, _conf(self.settings)
        wav = self.video.with_suffix(".outro.wav")
        x = self.line.samples
        loud = x[np.abs(x) > 0.02]
        x = x * (SPEECH_RMS / float(np.sqrt(np.mean(loud ** 2)) if len(loud) else 1.0))
        x = np.clip(x, -0.98, 0.98)
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(snd.SR)
            w.writeframes((x * 32767).astype(np.int16).tobytes())

        duck = float(conf.get("duck", 0.3))
        t0 = max(0.0, self.at - 0.1)
        voice = f"[1:a]adelay={int(self.at * 1000)}:all=1,apad"
        if _has_audio(self.video, s):
            dip = (f"volume='if(lt(t,{t0:.3f}),1,max({duck},1-(1-{duck})*(t-{t0:.3f})/{RAMP}))'"
                   ":eval=frame")
            graph = f"[0:a]{dip}[bed];{voice}[vo];[bed][vo]amix=inputs=2:duration=first:normalize=0[a]"
        else:
            graph = f"{voice}[a]"
        tmp = self.video.with_suffix(".outro.mp4")
        try:
            subprocess.run([ffmpeg_exe(s), "-y", "-loglevel", "error", "-i", str(self.video), "-i", str(wav),
                            "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{self.total:.3f}", str(tmp)],
                           check=True, capture_output=True)
            tmp.replace(self.video)
        finally:
            wav.unlink(missing_ok=True)
        print(f"  🔔 outro: \"{self.line.text}\" at {self.at:.1f}s (+{self.hold:.1f}s)")


def plan(topic: dict[str, Any], settings: dict[str, Any], video: Path, duration: float) -> Outro | None:
    """An Outro for this video, or None (turned off, a loop-length Short, or no voice)."""
    if text_for(topic, settings, duration) is None:
        return None
    try:
        return Outro(topic, settings, video, duration)
    except RuntimeError as exc:    # no internet for a new line: ship without it rather than fail
        print(f"  🔔 outro skipped: {exc}")
        return None
