"""Long-form episodes: narrated 16:9 videos built from chart chapters.

An episode is one YAML file in ``config/longform/``: a title, a voice, and a
list of chapters. Each chapter is a chart (which data, which mode) plus the
narration spoken over it; the chart runs for exactly as long as the narration
takes to say. ``build.py`` renders the chapters and stitches them together.

Nothing here touches the Shorts pipeline: Shorts stay in ``config/topics.yaml``
and ``pipeline.py``; long-form reuses only the fetchers and renderers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..config import CONFIG_DIR, PROJECT_ROOT

EPISODE_DIR = CONFIG_DIR / "longform"
OUT_ROOT = PROJECT_ROOT / "output" / "longform"

# Narration pace used for estimates until a chapter has real audio. Edge's
# neural voices read documentary copy at about this speed.
WORDS_PER_MINUTE = 150

MODES = ("bar_race", "bump_race", "line_grow", "line_multi")
_KEY_RE = re.compile(r"^[a-z0-9_]+$")


class EpisodeError(ValueError):
    """An episode file that cannot be built, with a message a person can act on."""


def episode_path(key: str) -> Path:
    if not _KEY_RE.match(key or ""):
        raise EpisodeError("Episode key must be lowercase letters, numbers and underscores")
    return EPISODE_DIR / f"{key}.yaml"


def out_dir(key: str) -> Path:
    return OUT_ROOT / key


def words(text: str | None) -> int:
    return len((text or "").split())


def list_keys() -> list[str]:
    if not EPISODE_DIR.exists():
        return []
    return sorted(p.stem for p in EPISODE_DIR.glob("*.yaml"))


def load(key: str) -> dict[str, Any]:
    path = episode_path(key)
    if not path.exists():
        raise EpisodeError(f"No episode named '{key}'")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("key", key)
    data.setdefault("chapters", [])
    return data


def _header_comments(path: Path) -> str:
    """The leading comment block of an episode file, kept across saves.

    It is where the script's provenance lives (which data, what to verify), and
    a yaml round-trip would silently drop it.
    """
    if not path.exists():
        return ""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            lines.append(line)
        else:
            break
    return "\n".join(lines).rstrip() + "\n\n" if any(l.startswith("#") for l in lines) else ""


def validate(ep: dict[str, Any]) -> None:
    if not str(ep.get("title", "")).strip():
        raise EpisodeError("The episode needs a title")
    seen: set[str] = set()
    for i, ch in enumerate(ep.get("chapters") or [], start=1):
        cid = str(ch.get("id", ""))
        if not _KEY_RE.match(cid):
            raise EpisodeError(f"Chapter {i}: id must be lowercase letters, numbers and underscores")
        if cid in seen:
            raise EpisodeError(f"Chapter {i}: id '{cid}' is used twice")
        seen.add(cid)
        chart = ch.get("chart") or {}
        if chart.get("mode") not in MODES:
            raise EpisodeError(f"Chapter {i} ({cid}): chart mode must be one of {', '.join(MODES)}")
        if not chart.get("code"):
            raise EpisodeError(f"Chapter {i} ({cid}): the chart needs a World Bank indicator code")
        if chart["mode"] == "line_multi" and len(chart.get("entities") or []) < 2:
            raise EpisodeError(f"Chapter {i} ({cid}): a head-to-head needs at least two countries")
        if chart["mode"] == "line_grow" and not chart.get("entity"):
            raise EpisodeError(f"Chapter {i} ({cid}): a single line needs a country")


def save(key: str, ep: dict[str, Any]) -> None:
    """Write an episode back, validating first and keeping the header comments."""
    ep = {**ep, "key": key}
    validate(ep)
    path = episode_path(key)
    head = _header_comments(path)
    order = ["key", "title", "yt_title", "series", "voice", "voice_rate", "music_mood", "target_minutes",
             "reviewed", "chapters"]
    doc = {k: ep[k] for k in order if k in ep}
    doc.update({k: v for k, v in ep.items() if k not in doc})
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=88)
    EPISODE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(head + body, encoding="utf-8")


def read_state(key: str) -> dict[str, Any]:
    """What the last build left behind: per-chapter audio lengths and a status."""
    path = out_dir(key) / "state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def summary(key: str) -> dict[str, Any]:
    """Everything the dashboard shows for an episode, measured where possible."""
    ep = load(key)
    state = read_state(key)
    built = state.get("chapters", {})
    chapters = []
    total_secs = 0.0
    for ch in ep["chapters"]:
        n = words(ch.get("narration"))
        done = built.get(ch["id"], {})
        # A measured length only counts while the words it was measured on are
        # still the words in the script.
        fresh = done.get("words") == n and done.get("secs")
        secs = float(done["secs"]) if fresh else n / WORDS_PER_MINUTE * 60
        total_secs += secs
        chapters.append({**ch, "words": n, "secs": round(secs, 1), "measured": bool(fresh),
                         "rendered": bool(fresh and done.get("video"))})
    video = out_dir(key) / "episode.mp4"
    return {
        **ep,
        "chapters": chapters,
        "words": sum(c["words"] for c in chapters),
        "secs": round(total_secs, 1),
        "checks": sum(1 for c in chapters if c.get("check")),
        "rendered": sum(1 for c in chapters if c["rendered"]),
        "has_video": video.exists(),
        "video_stale": bool(video.exists() and any(not c["rendered"] for c in chapters)),
        "build": state.get("build") or {},
    }
