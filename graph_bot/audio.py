"""Mux background music onto a rendered (video-only) mp4.

You supply your own **royalty-free / Creative Commons / public-domain** tracks by
dropping audio files into `assets/music/` (see that folder's README for legal
sources). This module never bundles or downloads copyrighted music.

Behaviour is controlled by the `audio` block in config/settings.yaml. If music is
disabled or the folder has no tracks, the video is left untouched (no error).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

from . import music_gen
from .config import PROJECT_ROOT
from .render import ffmpeg_exe

_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def list_tracks(folder: Path) -> list[Path]:
    """Every audio file in the folder, including one level of mood subfolders."""
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in _AUDIO_EXTS)


def _mood_of(track: Path, folder: Path) -> str | None:
    """Mood a track is tagged with, or None if it is untagged.

    Two ways to tag, whichever is tidier for you:
      * put it in a subfolder named after the mood — ``assets/music/majestic/``
      * name the file with the mood in it — ``majestic-fanfare.mp3``
    """
    try:
        parent = track.relative_to(folder).parts[0]
    except ValueError:
        parent = ""
    if parent.lower() in music_gen.STYLES:
        return parent.lower()
    stem = track.stem.lower()
    for mood in music_gen.STYLES:
        if mood in stem:
            return mood
    return None


# Topic-type -> mood, matched by keyword. First hit wins.
_MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("develop", "coding", "software", "mobile", "phone"), "lofi"),
    (("co2", "military", "defense", "migrant", "emission", "death"), "reflective"),
    (("gdp", "export", "econom", "trade"), "majestic"),
    (("patent", "science", "research", "internet", "innovation", "electric", "energy"), "hopeful"),
    (("touris", "travel", "forest", "meat", "food", "nature", "air", "flight"), "serene"),
    (("population", "life", "birth", "people"), "calm"),
]


def infer_mood(topic: dict[str, Any]) -> str:
    """Pick a fitting music mood from the topic's key/title/hashtags."""
    explicit = topic.get("mood")
    if explicit:
        return explicit
    text = " ".join([
        str(topic.get("key", "")),
        str(topic.get("title", "")),
        str(topic.get("subtitle", "")),
        " ".join(topic.get("hashtags", []) or []),
    ]).lower()
    for keywords, mood in _MOOD_KEYWORDS:
        if any(k in text for k in keywords):
            return mood
    return "calm"


def _seed(key: str) -> int:
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % (2**32)


def _pick_track(tracks: list[Path], key: str) -> Path:
    # Deterministic per-topic choice (stable across runs; varied across topics).
    return tracks[_seed(key) % len(tracks)]


def _has_audio(video: Path, settings: dict[str, Any]) -> bool:
    """True if the rendered video already carries an audio track (e.g. narration)."""
    proc = subprocess.run(
        [ffmpeg_exe(settings), "-i", str(video)], capture_output=True, text=True
    )
    return "Audio:" in (proc.stderr or "")


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _generated_track(key: str, duration: float, mood: str) -> Path:
    """Return a cached, seeded, mood-matched ambient track, generating if needed."""
    cache = PROJECT_ROOT / "data" / "music_cache"
    track = cache / f"{key}-{mood}.wav"
    if not track.exists() or _wav_duration(track) < duration:
        print(f"  ♪ generating '{mood}' theme for {key} ...")
        music_gen.generate(duration + 2.0, _seed(key), track, mood=mood)
    return track


_DURATION_CACHE: dict[str, float] = {}


def _track_duration(path: Path, settings: dict[str, Any]) -> float:
    """Length of an audio file in seconds; 0.0 if it cannot be read."""
    cached = _DURATION_CACHE.get(str(path))
    if cached is not None:
        return cached
    if path.suffix.lower() == ".wav":
        secs = _wav_duration(path)
    else:
        out = subprocess.run([ffmpeg_exe(settings), "-i", str(path)],
                             capture_output=True, text=True)
        secs = 0.0
        for line in (out.stderr or "").splitlines():
            if "Duration:" not in line:
                continue
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            try:
                h, m, s = stamp.split(":")
                secs = int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                secs = 0.0
            break
    _DURATION_CACHE[str(path)] = secs
    return secs


def _long_enough(tracks: list[Path], duration: float,
                 settings: dict[str, Any]) -> list[Path]:
    """Drop tracks shorter than the video.

    A short track is looped to fill the runtime, and the restart is audible —
    so a 24.5s bed under a 25.5s video has a seam a second before the end. If
    nothing is long enough, keep the longest so there is still a bed.
    """
    fits = [t for t in tracks if _track_duration(t, settings) >= duration]
    if fits:
        return fits
    longest = max(tracks, key=lambda t: _track_duration(t, settings))
    print(f"  ♪ no track covers {duration:.0f}s — using the longest ({longest.name})")
    return [longest]


def _select_track(conf: dict[str, Any], topic: dict[str, Any], duration: float,
                  settings: dict[str, Any] | None = None) -> Path | None:
    key = topic.get("key", "track")
    source = conf.get("source", "generate")
    if source == "generate":
        return _generated_track(key, duration, infer_mood(topic))
    folder = PROJECT_ROOT / conf.get("folder", "assets/music")
    tracks = list_tracks(folder)
    mood = infer_mood(topic)
    if not tracks:
        print(f"  ♪ music source=folder but no tracks in {folder} — skipping "
              f"(add royalty-free files or set audio.source: generate)")
        return None

    # Prefer a track tagged with this topic's mood, then untagged ones. A wrong
    # mood is worse than no folder track at all — an upbeat dance bed under a
    # poverty or emissions topic reads as tone-deaf — so rather than picking any
    # file, fall back to the synth, which is always mood-matched.
    settings = settings or {}
    tagged = [t for t in tracks if _mood_of(t, folder) == mood]
    if tagged:
        return _pick_track(_long_enough(tagged, duration, settings), key)
    untagged = [t for t in tracks if _mood_of(t, folder) is None]
    if untagged:
        return _pick_track(_long_enough(untagged, duration, settings), key)
    print(f"  ♪ no '{mood}' track in {folder.name}/ — using the generated theme")
    return _generated_track(key, duration, mood)


def select_track(settings: dict[str, Any], topic: dict[str, Any], duration: float) -> Path | None:
    """Pick (or synthesize) the mood-matched track for a topic.

    Separate from mux_track so an orchestrator can choose music in parallel
    with the video render — the mux loops the track, so an estimated duration
    is fine here; fades use the real duration at mux time.
    """
    conf = settings.get("audio", {}) or {}
    if not conf.get("enabled", False):
        return None
    return _select_track(conf, topic, duration, settings)


def add_music(video_path: Path, settings: dict[str, Any], duration: float, topic: dict[str, Any],
              on_stage=None) -> str | None:
    """Overlay a mood-matched music track onto video_path in place. Returns track name or None."""
    track = select_track(settings, topic, duration)
    if track is None:
        return None
    if on_stage:  # track picked/generated; muxing + loudness is the "mixing" phase
        on_stage("mixing")
    return mux_track(video_path, settings, duration, track)


def mux_track(video_path: Path, settings: dict[str, Any], duration: float,
              track: Path) -> str | None:
    """Mux a pre-selected track onto video_path in place. Returns track name or None."""
    conf = settings.get("audio", {}) or {}
    narrated = _has_audio(video_path, settings)
    # Duck the music well below a voice track so narration stays intelligible.
    volume = float(conf.get("volume_under_voice", 0.15) if narrated
                   else conf.get("volume", 0.6))
    fade_in, fade_out = _fades(conf, duration)

    parts = [f"afade=t=in:st=0:d={fade_in:.2f}"]
    if fade_out > 0:
        parts.append(f"afade=t=out:st={max(0.0, duration - fade_out):.2f}:d={fade_out:.2f}")
    parts.append(f"volume={volume}")
    afilter = ",".join(parts)
    if narrated:
        # Mix the bed under the existing narration (normalize=0 keeps voice at full level).
        filter_complex = (
            f"[0:a]{afilter}[music];"
            f"[1:a][music]amix=inputs=2:duration=first:normalize=0[a]"
        )
    else:
        filter_complex = f"[0:a]{afilter}[a]"

    tmp = video_path.with_suffix(".withaudio.mp4")
    cmd = [
        ffmpeg_exe(settings), "-y", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(track),   # loop music to cover the video
        "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "1:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        print(f"  ♪ music mux failed ({exc.returncode}); keeping silent video.\n{exc.stderr}")
        tmp.unlink(missing_ok=True)
        return None

    tmp.replace(video_path)  # atomic swap
    _normalize_loudness(video_path, settings, conf)
    print(f"  ♪ added music: {track.name}")
    return track.name


def _fades(conf: dict[str, Any], duration: float) -> tuple[float, float]:
    """Fade lengths for this runtime.

    Each fade is capped at a share of the video so a fixed 1.5s/2.0s pair does
    not swallow a 6-second topic, and short videos get no tail fade at all —
    they are watched on loop, and a fade to silence makes the seam audible.
    """
    cap = duration * float(conf.get("fade_max_fraction", 0.08))
    fade_in = min(float(conf.get("fade_in", 1.5)), cap)
    if duration < float(conf.get("loop_seamless_below", 12)):
        return fade_in, 0.0
    return fade_in, min(float(conf.get("fade_out", 2.0)), cap)


def _normalize_loudness(video_path: Path, settings: dict[str, Any],
                        conf: dict[str, Any]) -> bool:
    """Two-pass EBU R128 normalization to the configured target.

    Two passes rather than one: single-pass loudnorm adapts as it goes, which
    pumps the level on a quiet ambient bed. Measuring first and applying a fixed
    correction keeps the music steady.
    """
    target = conf.get("loudness_lufs", -14)
    if target is None:
        return False
    peak = float(conf.get("true_peak_db", -1.5))
    exe = ffmpeg_exe(settings)

    probe = subprocess.run(
        [exe, "-i", str(video_path), "-af", "loudnorm=print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"\{[^{}]*input_i[^{}]*\}", probe.stderr or "", re.S)
    if not match:
        print("  ♪ loudness probe failed; leaving levels as rendered.")
        return False
    m = json.loads(match.group(0))

    measured = (
        f"loudnorm=I={target}:TP={peak}:LRA=11"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}:linear=true"
    )
    tmp = video_path.with_suffix(".loudnorm.mp4")
    try:
        subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(video_path),
             "-af", measured, "-map", "0:v", "-map", "0:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             str(tmp)],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  ♪ loudness normalize failed ({exc.returncode}); keeping original levels.")
        tmp.unlink(missing_ok=True)
        return False

    tmp.replace(video_path)
    print(f"  ♪ normalized {m['input_i']} -> {target} LUFS")
    return True
