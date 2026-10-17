"""Every video the channel makes, behind one key format.

Three kinds of video go through the same render queue, upload queue, batch,
uploader, quota and history:

    population                   a daily Short, from config/topics.yaml
    lf_india_climb               a long-form video (an episode)
    lf_india_climb__the_catch    a Short cut from one of that video's chapters

``item(key)`` answers the same questions for any of them: what it is called,
which playlist it belongs to, where its files are, whether it is rendered and
current, and whether it has been uploaded. Callers that used to assume "a key
is a topic with an export folder" ask this module instead.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, load_topics, topic_series

LF_PREFIX = "lf_"
SEP = "__"
# Units one upload spends: videos.insert 1600, thumbnail 50, playlist 50 and
# lookups; a long-form video adds captions.insert (400) for its subtitles.
UNITS_SHORT = 1702
UNITS_VIDEO = 2102
# Shorts from one video go out one at a time, this many days apart.
SHORTS_GAP_DAYS = 2


def parse(key: str) -> tuple[str, str | None, str | None]:
    """(kind, episode, chapter): kind is "short" (daily), "video" or "video_short"."""
    if key.startswith(LF_PREFIX):
        rest = key[len(LF_PREFIX):]
        if SEP in rest:
            ep, cid = rest.split(SEP, 1)
            return "video_short", ep, cid
        return "video", rest, None
    return "short", None, None


def video_key(ep: str) -> str:
    return f"{LF_PREFIX}{ep}"


def short_key(ep: str, cid: str) -> str:
    return f"{LF_PREFIX}{ep}{SEP}{cid}"


def is_long_form(key: str) -> bool:
    return key.startswith(LF_PREFIX)


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def _video_item(ep_key: str) -> dict[str, Any] | None:
    from . import longform

    try:
        s = longform.summary(ep_key)
    except Exception:
        return None
    folder = longform.out_dir(ep_key)
    series = s.get("series") or "world_in_data"
    title_file = folder / "title.txt"
    return {
        "key": video_key(ep_key), "kind": "video", "episode": ep_key, "chapter": None,
        "title": (title_file.read_text(encoding="utf-8").strip().splitlines() or [""])[0]
        if title_file.exists() else s.get("yt_title") or s["title"],
        "name": s["title"], "series": series,
        "folder": folder, "video": folder / "episode.mp4",
        "title_file": title_file, "description_file": folder / "description.txt",
        "thumbnail": folder / "thumbnail.jpg", "subtitles": folder / "episode.srt",
        "tags": [t.lstrip("#") for t in (s.get("hashtags") or [])],
        "rendered": bool(s["has_video"]), "current": bool(s["has_video"] and not s["video_stale"]),
        "reviewed": bool(s.get("reviewed")), "check": None,
        "duration_sec": (s.get("build") or {}).get("secs") or s.get("secs"),
        "rendered_on": ((s.get("build") or {}).get("finished_at") or "")[:10] or None,
        "units": UNITS_VIDEO,
    }


def video_shorts(ep_key: str) -> list[dict[str, Any]]:
    """The Shorts a video's chapters make, in posting order, with their state."""
    from . import longform
    from .longform import shorts as sh

    try:
        ep = longform.load(ep_key)
    except Exception:
        return []
    work = longform.out_dir(ep_key) / "shorts"
    try:
        import json

        state = json.loads((work / "state.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    series = ep.get("series") or "world_in_data"
    out = []
    picked = [c for c in ep["chapters"] if not (c.get("short") or {}).get("skip")]
    for n, ch in enumerate(picked, start=1):
        cid = ch["id"]
        stem = f"{n:02d}_{cid}"
        done = state.get(cid) or {}
        video = work / f"{stem}.mp4"
        rendered = video.exists()
        current = rendered and done.get("hash") == sh._hash(ep, ch) and done.get("video") == video.name
        out.append({
            "key": short_key(ep_key, cid), "kind": "video_short", "episode": ep_key, "chapter": cid,
            "n": n, "title": ((ch.get("short") or {}).get("title") or ch.get("heading") or cid)[:100],
            "name": ch.get("heading") or cid, "series": series,
            "folder": work, "video": video, "text_file": work / f"{stem}.txt",
            "thumbnail": None, "subtitles": None,
            "tags": [t.lstrip("#") for t in (ep.get("hashtags") or [])],
            "rendered": rendered, "current": bool(current),
            "reviewed": bool(ep.get("reviewed")), "check": ch.get("check"),
            "duration_sec": done.get("secs"), "units": UNITS_SHORT,
            "rendered_on": dt.date.fromtimestamp(video.stat().st_mtime).isoformat() if rendered else None,
        })
    return out


def item(key: str) -> dict[str, Any] | None:
    """Everything known about one video, whatever its kind; None if no such key."""
    kind, ep, cid = parse(key)
    if kind == "video":
        return _video_item(ep)
    if kind == "video_short":
        return next((s for s in video_shorts(ep) if s["chapter"] == cid), None)
    topic = next((t for t in load_topics() if t["key"] == key), None)
    if topic is None:
        return None
    from .queue import _exported_keys

    rel = _exported_keys().get(key)
    folder = PROJECT_ROOT / rel if rel else None
    return {
        "key": key, "kind": "short", "episode": None, "chapter": None,
        "title": topic.get("title", key), "name": topic.get("title", key),
        "series": topic_series(topic), "folder": folder,
        "video": folder / "video.mp4" if folder else None,
        "title_file": folder / "title.txt" if folder else None,
        "description_file": folder / "description.txt" if folder else None,
        "thumbnail": None, "subtitles": None,
        "tags": [h.lstrip("#") for h in (topic.get("hashtags") or [])],
        "rendered": bool(folder), "current": bool(folder), "reviewed": True, "check": None,
        "units": UNITS_SHORT,
    }


def exists(key: str) -> bool:
    return item(key) is not None


def ready(key: str) -> tuple[bool, str]:
    """Can this be uploaded right now? (ok, reason a person can act on)."""
    it = item(key)
    if it is None:
        return False, f"Unknown video: {key}"
    return ready_item(it)


def ready_item(it: dict[str, Any]) -> tuple[bool, str]:
    """ready() for an item already looked up. Use it in loops: item() of a Short
    reloads its video's script and recomputes all of that video's Shorts."""
    if not it["rendered"] or not it.get("video") or not Path(it["video"]).exists():
        return False, "Not rendered yet"
    if not it["current"]:
        return False, "The script changed since it was rendered; render it again"
    if not it["reviewed"]:
        return False, "The script is not marked as reviewed"
    if it.get("check"):
        return False, "Has a line to fact-check (remove the chapter's check note when done)"
    return True, "Ready"


def folder_rel(key: str) -> str | None:
    """The folder holding the video's files, relative to the project."""
    it = item(key)
    folder = it and it.get("folder")
    return _rel(Path(folder)) if folder else None


def read_upload(key: str) -> dict[str, Any]:
    """What the uploader sends: video, title, description, thumbnail, subtitles, tags."""
    it = item(key)
    if it is None:
        raise ValueError(f"Unknown video: {key}")
    if it["kind"] == "video_short":
        lines = Path(it["text_file"]).read_text(encoding="utf-8").split("\n")
        title, description = lines[0].strip(), "\n".join(lines[1:]).strip()
    else:
        title = Path(it["title_file"]).read_text(encoding="utf-8").strip().splitlines()[0].strip()
        desc = it.get("description_file")
        description = Path(desc).read_text(encoding="utf-8").strip() if desc and Path(desc).exists() else ""
    thumb = it.get("thumbnail")
    subs = it.get("subtitles")
    return {
        "video": Path(it["video"]), "title": title, "description": description,
        "thumbnail": Path(thumb) if thumb and Path(thumb).exists() else None,
        "subtitles": Path(subs) if subs and Path(subs).exists() and Path(subs).stat().st_size else None,
        "tags": it.get("tags") or [], "series": it["series"], "units": it["units"],
        "language": "en" if it["kind"] != "short" else None,
    }


def queue_items(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Videos and Shorts from videos that are rendered and not uploaded yet.

    ``held``: cannot be uploaded yet (the video is not up, a fact-check, out of
    date); ``reason`` says why. ``planned``: can be uploaded, but the posting
    plan suggests a later day (one Short per video every few days); the person
    may still send it now and schedule it in YouTube Studio."""
    from . import longform

    today = dt.date.today()
    out: list[dict[str, Any]] = []
    for ep_key in longform.list_keys():
        v = _video_item(ep_key)
        if v is None or not v["rendered"]:
            continue
        v_up = log.get(v["key"])
        if not v_up:
            ok, why = ready_item(v)
            out.append({**_public(v), "held": not ok, "planned": False,
                        "reason": "New video" if ok else why})
        shorts = video_shorts(ep_key)
        posted = [log[s["key"]] for s in shorts if s["key"] in log]
        last = max((_day(p.get("uploaded_at")) for p in posted), default=None)
        # The day the next Short from this video may go out; each ready one
        # after it is planned a gap further on.
        slot = max(today, last + dt.timedelta(days=SHORTS_GAP_DAYS)) if last else today
        for s in shorts:
            if s["key"] in log or not s["rendered"]:
                continue
            ok, why = ready_item(s)
            planned = False
            if not v_up:
                held, reason = True, "Waits for the full video to be uploaded (it links to it)"
            elif not ok:
                held, reason = True, why
            else:
                held, planned = False, slot > today
                reason = (f"Suggested for {slot:%d %b} (one Short from this video every {SHORTS_GAP_DAYS} days). "
                          "You can send it now and schedule it in YouTube Studio."
                          if planned else f"Short {s['n']} of {len(shorts)} from {v['name']}")
                slot += dt.timedelta(days=SHORTS_GAP_DAYS)
            out.append({**_public(s), "held": held, "planned": planned, "reason": reason})
    return out


def _day(iso: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(str(iso)[:10])
    except Exception:
        return dt.date.min


def _public(it: dict[str, Any]) -> dict[str, Any]:
    """The JSON-safe part of an item, for the dashboard."""
    folder = it.get("folder")
    return {
        "key": it["key"], "kind": it["kind"], "episode": it.get("episode"), "chapter": it.get("chapter"),
        "title": it["title"], "name": it.get("name"), "series": it["series"],
        "duration_sec": it.get("duration_sec"), "rendered_on": it.get("rendered_on"),
        "exported": _rel(Path(folder)) if folder else None,
        "has_thumb": bool(it.get("thumbnail") and Path(it["thumbnail"]).exists()),
        "n": it.get("n"), "current": it.get("current"), "units": it.get("units"),
    }
