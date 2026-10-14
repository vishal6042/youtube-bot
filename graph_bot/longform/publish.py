"""Upload a finished long-form episode to YouTube, the way the Shorts go up.

Uses the Shorts uploader's steps (resumable insert, thumbnail, playlist) on the
episode's own folder, ``output/longform/<key>/``:

    episode.mp4  title.txt  description.txt  thumbnail.jpg  episode.srt

and adds the one thing Shorts do not need: the subtitle file, uploaded as the
English caption track (accurate to the script, unlike auto-captions on figures).

Like every API upload from this project, the video lands **Private**; you check
it in YouTube Studio and switch it to Public there. It is recorded in the
upload log as ``lf_<key>`` so it shows under Published and in the stats sync.

    python -m graph_bot.longform.publish india_climb --check
    python -m graph_bot.longform.publish india_climb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .. import store
from ..publish.auth import AuthError, assert_right_channel, service, token_info
from ..publish.upload import (CATEGORY_EDUCATION, DESCRIPTION_MAX, TITLE_MAX, UploadError,
                              add_to_playlist_named, insert_video, set_thumbnail)
from ..queue import playlist_of
from . import EpisodeError, out_dir, summary

# videos.insert 1600 + thumbnails.set 50 + captions.insert 400
# + playlistItems.insert 50 + the playlist and channel lookups.
QUOTA_UNITS = 2102


def log_key(key: str) -> str:
    """The episode's row in the upload log, kept apart from topic keys."""
    return f"lf_{key}"


def checks(key: str) -> list[dict[str, Any]]:
    """Everything that has to be true before spending quota on an upload."""
    try:
        s = summary(key)
    except EpisodeError as exc:
        return [{"name": "Episode", "ok": False, "detail": str(exc)}]
    folder = out_dir(key)
    missing = [f for f in ("episode.mp4", "title.txt", "description.txt") if not (folder / f).exists()]
    auth = token_info()
    quota = store.quota_status()
    uploaded = store.load_log().get(log_key(key))
    return [
        {"name": "Rendered", "ok": bool(s["has_video"] and not s["video_stale"] and not missing),
         "detail": ("Missing " + ", ".join(missing)) if missing and s["has_video"]
         else "Render the episode first" if not s["has_video"]
         else "The script changed since the last render" if s["video_stale"] else "Up to date"},
        {"name": "Reviewed", "ok": bool(s.get("reviewed")),
         "detail": "Tick 'I have read and checked the script'" if not s.get("reviewed") else "Checked"},
        {"name": "Not uploaded yet", "ok": not uploaded,
         "detail": f"Already uploaded: {uploaded.get('url') or 'no link recorded'}" if uploaded
         else "Not in the upload log"},
        {"name": "YouTube sign-in", "ok": not auth.get("needs_reauth", True),
         "detail": "Run: python -m graph_bot.publish.auth" if auth.get("needs_reauth", True)
         else "Authorised"},
        {"name": "Daily quota", "ok": quota["units_left"] >= QUOTA_UNITS,
         "detail": f"{quota['units_left']:,} of {quota['daily_units']:,} units left; this needs {QUOTA_UNITS:,}"},
    ]


def _read(key: str) -> dict[str, Any]:
    folder = out_dir(key)
    title = (folder / "title.txt").read_text(encoding="utf-8").strip().splitlines()[0].strip()
    thumb = folder / "thumbnail.jpg"
    srt = folder / "episode.srt"
    return {
        "video": folder / "episode.mp4",
        "title": title[:TITLE_MAX],
        "description": (folder / "description.txt").read_text(encoding="utf-8").strip()[:DESCRIPTION_MAX],
        "thumbnail": thumb if thumb.exists() else None,
        "subtitles": srt if srt.exists() and srt.stat().st_size else None,
    }


def _add_subtitles(yt, video_id: str, srt: Path, result: dict[str, Any]) -> None:
    from googleapiclient.http import MediaFileUpload

    try:
        yt.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": "en", "name": "English",
                              "isDraft": False}},
            media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream"),
        ).execute()
        result["subtitles_added"] = True
    except Exception as exc:
        result["warnings"].append(f"subtitles not added: {str(exc).splitlines()[0]}")


def upload_episode(key: str, on_progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """Upload the episode as Private. Returns {video_id, url, studio, warnings, ...}."""
    failed = [c for c in checks(key) if not c["ok"]]
    if failed:
        raise UploadError("; ".join(f"{c['name']}: {c['detail']}" for c in failed))

    report = on_progress or (lambda pct, stage: None)
    s = summary(key)
    data = _read(key)
    playlist_name, playlist_exists = playlist_of(s.get("series") or "world_in_data")

    report(0, "authorising")
    channel = assert_right_channel()
    yt = service()
    tags = [t.lstrip("#") for t in (s.get("hashtags") or []) if t.lower().lstrip("#") != "shorts"]
    body = {
        "snippet": {
            "title": data["title"],
            "description": data["description"],
            "tags": tags or None,
            "categoryId": CATEGORY_EDUCATION,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    video_id = insert_video(yt, data["video"], body, report, upto=85)
    result: dict[str, Any] = {
        "key": key, "video_id": video_id, "url": f"https://youtu.be/{video_id}",
        "studio": f"https://studio.youtube.com/video/{video_id}/edit",
        "channel": channel["title"], "title": data["title"],
        "thumbnail_set": False, "playlist": playlist_name, "playlist_added": False,
        "subtitles_added": False, "warnings": [],
    }
    if data["thumbnail"]:
        report(88, "thumbnail")
        set_thumbnail(yt, video_id, data["thumbnail"], result)
    if data["subtitles"]:
        report(92, "subtitles")
        _add_subtitles(yt, video_id, data["subtitles"], result)
    report(96, "playlist")
    add_to_playlist_named(yt, video_id, playlist_name, playlist_exists, result)

    # Recorded last and only once the video exists, like the Shorts uploader.
    report(99, "recording")
    store.mark_uploaded(log_key(key), result["url"])
    store.record_upload_units(QUOTA_UNITS)
    report(100, "done")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.longform.publish")
    ap.add_argument("key")
    ap.add_argument("--check", action="store_true", help="show the checks; upload nothing")
    args = ap.parse_args()

    for c in checks(args.key):
        print(f"  {'OK ' if c['ok'] else 'NO '} {c['name']:<18} {c['detail']}")
    if args.check:
        return
    try:
        r = upload_episode(args.key, on_progress=lambda pct, stage: print(f"  {stage:<12} {pct:>3}%", end="\r"))
    except (UploadError, AuthError) as exc:
        sys.exit(f"\n{exc}")
    print(f"\nUploaded (Private): {r['url']}")
    print(f"Switch it to Public in Studio: {r['studio']}")
    for w in r["warnings"]:
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
