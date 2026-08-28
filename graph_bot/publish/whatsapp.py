"""WhatsApp Status stager (Phase 5).

WhatsApp has NO official API for posting Status updates, and unofficial automation
risks an account ban. So this "publisher" simply stages approved videos + captions
into an `upload/<date>/` folder for you to post manually (send to yourself / drag to
WhatsApp Status on phone or WhatsApp Desktop).

Usage:
    python -m graph_bot.publish.whatsapp --all
    python -m graph_bot.publish.whatsapp --key population
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path

from ..config import load_settings, resolve_path
from . import find_approved, read_caption, save_meta


def stage_one(meta_path: Path, meta: dict, upload_dir: Path) -> None:
    video = Path(meta["video"])
    if not video.exists():
        print(f"  ! video missing, skipping: {video}")
        return
    key = meta.get("key")
    dest_video = upload_dir / f"{key}.mp4"
    dest_caption = upload_dir / f"{key}.txt"
    shutil.copyfile(video, dest_video)
    dest_caption.write_text(read_caption(meta_path), encoding="utf-8")

    meta["whatsapp_staged"] = True
    meta["whatsapp_staged_at"] = dt.datetime.now().isoformat(timespec="seconds")
    meta["whatsapp_path"] = str(dest_video)
    save_meta(meta_path, meta)
    print(f"  📥 staged: {dest_video}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage approved videos for manual WhatsApp Status posting.")
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
    upload_dir = resolve_path(load_settings(), "upload") / date
    upload_dir.mkdir(parents=True, exist_ok=True)

    for meta_path, meta in items:
        stage_one(meta_path, meta, upload_dir)

    print(f"\n✅ Staged {len(items)} file(s) in {upload_dir}")
    print("   Post manually: WhatsApp > Status > add the mp4, paste the matching .txt caption.")


if __name__ == "__main__":
    main()
