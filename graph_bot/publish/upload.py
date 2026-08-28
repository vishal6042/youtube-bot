"""Upload a finished export to YouTube.

Works from the export folder the pipeline already produces —

    export/<date>/<series>/<NN_key>/
        video.mp4  title.txt  description.txt  thumbnail.jpg

— rather than the older review/output path, because that folder is exactly what
gets posted by hand today: same file, same title, same description, same
thumbnail.

**Uploads land PRIVATE.** The Google Cloud project is unverified, so the API
cannot publish publicly; the video appears in YouTube Studio for you to flip.
That is a platform restriction, not a setting — lifting it needs the YouTube API
Services audit. Everything else (file, metadata, thumbnail, playlist) is done for
you, so the manual step shrinks to one click.

Usage:
    python -m graph_bot.publish.upload --key patents --dry-run
    python -m graph_bot.publish.upload --key patents
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .. import store
from ..config import PROJECT_ROOT, load_topics, topic_series
from ..queue import _exported_keys, load_log, playlist_of
from .auth import AuthError, assert_right_channel, service

TITLE_MAX = 100
DESCRIPTION_MAX = 5000
CATEGORY_EDUCATION = "27"
# videos.insert costs 1600 of the default 10,000 units/day.
QUOTA_PER_UPLOAD = 1600


class UploadError(RuntimeError):
    """Something a human needs to read, not a traceback."""


def find_export(key: str) -> Path:
    rel = _exported_keys().get(key)
    if not rel:
        raise UploadError(f"'{key}' has no export folder — render and export it first.")
    folder = PROJECT_ROOT / rel
    if not folder.exists():
        raise UploadError(f"Export folder is gone: {rel}")
    return folder


def read_export(folder: Path) -> dict[str, Any]:
    video = folder / "video.mp4"
    if not video.exists():
        raise UploadError(f"No video.mp4 in {folder.name}")
    title_file, desc_file = folder / "title.txt", folder / "description.txt"
    if not title_file.exists():
        raise UploadError(f"No title.txt in {folder.name}")
    title = title_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    description = desc_file.read_text(encoding="utf-8").strip() if desc_file.exists() else ""
    # Prefer the 16:9 file: YouTube stores thumbnails only at 16:9, so the
    # portrait cover is accepted by the API and then not used.
    wide, portrait = folder / "thumbnail_yt.jpg", folder / "thumbnail.jpg"
    thumb = wide if wide.exists() else (portrait if portrait.exists() else None)
    return {
        "video": video,
        "title": title[:TITLE_MAX],
        "description": description[:DESCRIPTION_MAX],
        "thumbnail": thumb,
        "size": video.stat().st_size,
    }


def _aspect(path: Path) -> float | None:
    """width/height of an image, or None if it cannot be read."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.width / im.height
    except Exception:
        return None


def _tags_for(key: str) -> list[str]:
    topic = next((t for t in load_topics() if t["key"] == key), None)
    tags = [h.lstrip("#") for h in ((topic or {}).get("hashtags") or [])]
    # YouTube caps the tag field at 500 characters in total.
    out, total = [], 0
    for tag in tags:
        if total + len(tag) + 1 > 480:
            break
        out.append(tag)
        total += len(tag) + 1
    return out


def find_playlist_id(yt, name: str) -> str | None:
    """Look up one of the channel's own playlists by exact name.

    Deliberately does NOT create a missing playlist: creating public objects on
    the channel is the user's call, and brand.json already tracks which ones
    exist. A missing playlist is reported, not invented.
    """
    req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        resp = req.execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"].strip().lower() == name.strip().lower():
                return item["id"]
        req = yt.playlists().list_next(req, resp)
    return None


def upload(key: str, *, privacy: str = "private", add_to_playlist: bool = True,
           on_progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """Upload one exported video. Returns {video_id, url, playlist, ...}."""
    from googleapiclient.http import MediaFileUpload

    if key in load_log():
        raise UploadError(f"'{key}' is already marked uploaded — unmark it first if that was wrong.")

    folder = find_export(key)
    data = read_export(folder)
    series = topic_series({"key": key})
    playlist_name, playlist_exists = playlist_of(series)

    def report(pct: int, stage: str) -> None:
        if on_progress:
            on_progress(pct, stage)

    report(0, "authorising")
    # Checked on every upload, not just at auth time: a token for the personal
    # channel looks perfectly valid and would silently post to the wrong place.
    channel = assert_right_channel()
    yt = service()

    body = {
        "snippet": {
            "title": data["title"],
            "description": data["description"],
            "tags": _tags_for(key) or None,
            "categoryId": CATEGORY_EDUCATION,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(data["video"]), chunksize=1024 * 1024,
                            resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    report(1, "uploading")
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except Exception as exc:
            raise UploadError(f"Upload failed: {str(exc).splitlines()[0]}") from exc
        if status:
            # Reserve the last 10% for the thumbnail and playlist steps.
            report(max(1, int(status.progress() * 90)), "uploading")

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    result: dict[str, Any] = {
        "key": key, "video_id": video_id, "url": url, "channel": channel["title"],
        "title": data["title"], "privacy": privacy,
        "bytes": data["size"], "thumbnail_set": False,
        "playlist": playlist_name, "playlist_added": False, "warnings": [],
    }

    # ---- thumbnail ----
    if data["thumbnail"]:
        report(92, "thumbnail")
        try:
            yt.thumbnails().set(videoId=video_id, media_body=str(data["thumbnail"])).execute()
            result["thumbnail_set"] = True
            # The API accepts a portrait image and reports success, but every
            # YouTube thumbnail slot is 16:9 — so it gets pillarboxed or ignored
            # and the video shows a frame instead. Success here is not proof the
            # thumbnail is actually being used.
            ratio = _aspect(data["thumbnail"])
            if ratio is not None and ratio < 1.0:
                result["warnings"].append(
                    f"thumbnail is portrait ({ratio:.2f}); YouTube shows thumbnails at 16:9, "
                    "so it may not be used — a 1280x720 image would be")
        except Exception as exc:
            # Custom thumbnails need a verified (phone-confirmed) channel. The
            # video is already up, so this is a warning, never a failure.
            result["warnings"].append(f"thumbnail not set: {str(exc).splitlines()[0]}")

    # ---- playlist ----
    if add_to_playlist:
        report(96, "playlist")
        if not playlist_exists:
            result["warnings"].append(
                f"playlist '{playlist_name}' is not marked as created on YouTube — skipped")
        else:
            try:
                pid = find_playlist_id(yt, playlist_name)
                if pid is None:
                    result["warnings"].append(
                        f"no playlist named '{playlist_name}' on the channel — skipped")
                else:
                    yt.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": pid,
                                          "resourceId": {"kind": "youtube#video",
                                                         "videoId": video_id}}},
                    ).execute()
                    result["playlist_added"] = True
            except Exception as exc:
                result["warnings"].append(f"playlist add failed: {str(exc).splitlines()[0]}")

    # ---- record it ----
    # Written last and only on success, so the upload log never claims a video
    # went live when it did not.
    report(99, "recording")
    store.mark_uploaded(key, url)
    report(100, "done")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.publish.upload")
    ap.add_argument("--key", required=True, help="topic key to upload")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--no-playlist", action="store_true", help="skip playlist auto-add")
    ap.add_argument("--dry-run", action="store_true", help="show what would upload; no API calls")
    args = ap.parse_args()

    try:
        folder = find_export(args.key)
        data = read_export(folder)
    except UploadError as exc:
        sys.exit(f"❌ {exc}")

    series = topic_series({"key": args.key})
    name, exists = playlist_of(series)
    print(f"key         : {args.key}")
    print(f"folder      : {folder.relative_to(PROJECT_ROOT)}")
    print(f"title       : {data['title']}")
    print(f"video       : {data['size'] / 1e6:.1f} MB")
    ratio = _aspect(data["thumbnail"]) if data["thumbnail"] else None
    shape = "MISSING" if not data["thumbnail"] else (
        f"{'portrait' if ratio and ratio < 1 else '16:9'}"
        + (f" ({ratio:.2f}) - YouTube shows 16:9, may be ignored" if ratio and ratio < 1 else ""))
    print(f"thumbnail   : {shape}")
    print(f"tags        : {', '.join(_tags_for(args.key)) or 'none'}")
    print(f"playlist    : {name}{'' if exists else '  (not created on YouTube — will skip)'}")
    print(f"privacy     : {args.privacy}")
    print(f"quota cost  : {QUOTA_PER_UPLOAD} units of 10,000/day")
    if args.key in load_log():
        print("\n⚠ Already marked uploaded — a real run would refuse."
              " Unmark it first if that record is wrong.")

    try:
        me = assert_right_channel()
        print(f"channel     : {me['title']}  OK")
    except AuthError as exc:
        print(f"channel     : BLOCKED - {exc}")
        if not args.dry_run:
            sys.exit(1)

    if args.dry_run:
        print("\n[dry-run] Nothing uploaded.")
        return
    if args.privacy != "private":
        print("\n⚠ This project is unverified, so YouTube will force the video to Private")
        print("  regardless of this setting until the API audit is granted.")

    try:
        r = upload(args.key, privacy=args.privacy,
                   add_to_playlist=not args.no_playlist,
                   on_progress=lambda pct, stage: print(f"  {stage:<12} {pct:>3}%", end="\r"))
    except (UploadError, AuthError) as exc:
        sys.exit(f"\n❌ {exc}")

    print(f"\n✅ {r['url']}")
    print(f"   thumbnail {'set' if r['thumbnail_set'] else 'not set'} ·"
          f" playlist {'added' if r['playlist_added'] else 'not added'}")
    for w in r["warnings"]:
        print(f"   ⚠ {w}")
    print("   Marked uploaded. Flip it to Public in YouTube Studio when ready.")


if __name__ == "__main__":
    main()
