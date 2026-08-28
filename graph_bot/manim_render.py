"""Render a Manim concept scene and hand the finished mp4 back to the pipeline.

Manim owns its own render loop and writes into a media directory, so this module
shells out to the Manim CLI (isolated process = no global config bleed between
scenes), then moves the result to the pipeline's output path.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .render import ffmpeg_exe
from .scenes import SCENES

_QUALITY_FLAG = "-qh"  # high quality: honours our 1080x1920 config at 30fps


def render_scene(topic: dict[str, Any], settings: dict[str, Any], out_path: Path) -> float:
    """Render the topic's Manim scene to out_path. Returns duration in seconds."""
    scene_key = topic.get("scene")
    if scene_key not in SCENES:
        raise ValueError(
            f"Unknown scene {scene_key!r} for topic '{topic.get('key')}'. "
            f"Known scenes: {', '.join(SCENES)}"
        )
    module_path, class_name = SCENES[scene_key]
    module_file = PROJECT_ROOT / Path(module_path.replace(".", "/") + ".py")
    media_dir = PROJECT_ROOT / "data" / "manim_media"

    cmd = [
        sys.executable, "-m", "manim", "render", _QUALITY_FLAG,
        "--media_dir", str(media_dir),
        "--output_file", f"{topic['key']}.mp4",
        str(module_file), class_name,
    ]
    # Scene files import `graph_bot.scenes._base` absolutely, so the project root
    # must be importable inside the Manim subprocess.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    # Manim's console output contains Unicode; Windows' default cp1252 decode
    # would raise UnicodeDecodeError, so decode as UTF-8 and never fail on it.
    proc = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), env=env,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-25:]
        raise RuntimeError(
            f"Manim failed for scene '{scene_key}' (exit {proc.returncode}):\n"
            + "\n".join(tail)
        )

    produced = _find_output(media_dir, topic["key"])
    if produced is None:
        raise RuntimeError(f"Manim reported success but no mp4 found for '{scene_key}'")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(produced, out_path)
    return _duration(out_path, settings)


def _find_output(media_dir: Path, key: str) -> Path | None:
    matches = sorted(
        media_dir.rglob(f"{key}.mp4"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return matches[0] if matches else None


def _duration(path: Path, settings: dict[str, Any]) -> float:
    """Probe duration with ffmpeg (ffprobe isn't bundled with imageio-ffmpeg)."""
    proc = subprocess.run(
        [ffmpeg_exe(settings), "-i", str(path)], capture_output=True, text=True
    )
    for line in (proc.stderr or "").splitlines():
        if "Duration:" in line:
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = stamp.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 30.0
