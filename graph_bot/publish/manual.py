"""Export approved videos for MANUAL public upload.

Because API-uploaded videos from an unverified project are locked to private,
the reliable way to publish publicly is to upload the finished file yourself via
the YouTube app/site (and Instagram/TikTok/FB). This helper stages everything you
need into one tidy folder per video:

    export/<date>/<key>/
        video.mp4         <- the finished video (with music)
        title.txt         <- clickable title, ready to paste
        description.txt    <- description with source credit + hashtags

Title/description are regenerated fresh from the topic, so re-exporting picks up
any title/caption improvements without re-rendering.

Usage:
    python -m graph_bot.publish.manual --all
    python -m graph_bot.publish.manual --key population
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path

from .. import caption
from ..config import (
    get_topic,
    load_settings,
    resolve_path,
    topic_episode,
    topic_series,
)
from . import find_approved, save_meta


def _topic_for(meta: dict) -> dict:
    try:
        return get_topic(meta["key"])
    except KeyError:
        # Topic was removed from the catalog — fall back to stored metadata.
        return {
            "key": meta.get("key"),
            "title": meta.get("title"),
            "source": meta.get("source"),
            "hashtags": meta.get("hashtags", []),
        }


def export_one(meta_path: Path, meta: dict, export_root: Path) -> Path | None:
    video = Path(meta["video"])
    if not video.exists():
        print(f"  ! video missing, skipping: {video}")
        return None

    key = meta["key"]
    topic = _topic_for(meta)
    y0, y1 = int(meta.get("year_min", 0)), int(meta.get("year_max", 0))

    # Group by series so each folder maps 1:1 to a YouTube playlist, and
    # zero-pad the episode number so folders sort in course order.
    series = topic_series(topic)
    episode = topic_episode(topic)
    folder = f"{episode:02d}_{key}" if episode is not None else key
    dest = export_root / series / folder
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, dest / "video.mp4")
    (dest / "title.txt").write_text(caption.build_title(topic, y0, y1), encoding="utf-8")
    (dest / "description.txt").write_text(
        caption.build_description(topic, y0, y1, meta.get("music")), encoding="utf-8")

    meta["exported"] = True
    meta["exported_at"] = dt.datetime.now().isoformat(timespec="seconds")
    meta["series"] = series
    save_meta(meta_path, meta)
    print(f"  📦 {series}/{key}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export approved videos for manual public upload.")
    parser.add_argument("--key", help="Single topic key (default: all approved for the date)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--all", action="store_true", help="All approved items for the date")
    args = parser.parse_args()

    items = find_approved(args.date, args.key, args.all)
    if not items:
        date = args.date or dt.date.today().isoformat()
        print(f"No approved items for {date}. Approve some first: python -m graph_bot.review approve <key>")
        return

    date = args.date or dt.date.today().isoformat()
    export_root = resolve_path(load_settings(), "export") / date
    export_root.mkdir(parents=True, exist_ok=True)

    exported = [d for d in (export_one(p, m, export_root) for p, m in items) if d]

    print(f"\n✅ Exported {len(exported)} video(s) to {export_root}")
    print("   Folders are grouped by series — one folder per YouTube playlist:")
    for sub in sorted(p for p in export_root.iterdir() if p.is_dir()):
        print(f"     {sub.name}/  ({sum(1 for _ in sub.iterdir())} videos)")
    print("\n   To post publicly:")
    print("   1. Open a series folder, then a video folder inside it.")
    print("   2. Upload video.mp4 to YouTube (app or studio.youtube.com) — set Public.")
    print("   3. Paste title.txt as the title and description.txt as the description.")
    print("   4. Add it to the playlist matching the series folder name.")


if __name__ == "__main__":
    main()
