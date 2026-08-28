"""Instagram Reels + Facebook publisher (Phase 4) via the Meta Graph API.

Publishes only APPROVED items. Requires a Meta app with approved permissions and
a long-lived Page access token (see docs/SETUP_META.md).

IMPORTANT constraint: Instagram's API cannot accept a local file — it fetches the
video from a **public URL**. So the approved mp4 must be reachable at
  {PUBLIC_BASE_URL}/{date}/{key}/video.mp4
Set PUBLIC_BASE_URL in .env to wherever you serve the `output/` folder (your own
host, S3/CDN, or a tunnel like ngrok over `python -m http.server`).
Facebook, by contrast, accepts a direct file upload.

.env keys:
  META_ACCESS_TOKEN   long-lived Page access token
  IG_USER_ID          Instagram Business account id  (for Instagram)
  FB_PAGE_ID          Facebook Page id                (for Facebook)
  PUBLIC_BASE_URL     public base URL for the output folder (for Instagram)
  META_GRAPH_VERSION  optional, default v21.0

Usage:
    python -m graph_bot.publish.meta --dry-run
    python -m graph_bot.publish.meta --key population --targets instagram,facebook
    python -m graph_bot.publish.meta --all --targets facebook
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import requests

from ..config import env
from . import find_approved, read_caption, save_meta

GRAPH = "https://graph.facebook.com"
GRAPH_VIDEO = "https://graph-video.facebook.com"
_POLL_SECONDS = 5
_POLL_MAX = 60  # ~5 min for Instagram container processing


def _ver() -> str:
    return env("META_GRAPH_VERSION", "v21.0")


# --------------------------------------------------------------------------- #
# Instagram Reels
# --------------------------------------------------------------------------- #
def publish_instagram(meta_path: Path, meta: dict, token: str, ig_user_id: str, base_url: str) -> None:
    date = meta_path.parent.parent.name
    key = meta.get("key")
    video_url = f"{base_url.rstrip('/')}/{date}/{key}/video.mp4"
    caption = read_caption(meta_path)

    # 1. Create the media container.
    create = requests.post(
        f"{GRAPH}/{_ver()}/{ig_user_id}/media",
        data={"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": token},
        timeout=60,
    ).json()
    if "id" not in create:
        raise RuntimeError(f"IG container creation failed: {create}")
    container_id = create["id"]

    # 2. Poll until the upload/transcode finishes.
    for _ in range(_POLL_MAX):
        status = requests.get(
            f"{GRAPH}/{_ver()}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        ).json()
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"IG container error: {status}")
        time.sleep(_POLL_SECONDS)
    else:
        raise TimeoutError("IG container did not finish in time")

    # 3. Publish.
    publish = requests.post(
        f"{GRAPH}/{_ver()}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    ).json()
    if "id" not in publish:
        raise RuntimeError(f"IG publish failed: {publish}")

    meta["instagram_id"] = publish["id"]
    _mark_published(meta, "instagram")
    save_meta(meta_path, meta)
    print(f"  ✅ instagram: {key} -> media {publish['id']}")


# --------------------------------------------------------------------------- #
# Facebook Page video (direct file upload)
# --------------------------------------------------------------------------- #
def publish_facebook(meta_path: Path, meta: dict, token: str, page_id: str) -> None:
    video = Path(meta["video"])
    if not video.exists():
        raise FileNotFoundError(video)
    caption = read_caption(meta_path)

    with open(video, "rb") as fh:
        resp = requests.post(
            f"{GRAPH_VIDEO}/{_ver()}/{page_id}/videos",
            data={"description": caption, "access_token": token},
            files={"source": fh},
            timeout=600,
        ).json()
    if "id" not in resp:
        raise RuntimeError(f"Facebook upload failed: {resp}")

    meta["facebook_id"] = resp["id"]
    _mark_published(meta, "facebook")
    save_meta(meta_path, meta)
    print(f"  ✅ facebook: {meta.get('key')} -> video {resp['id']}")


# --------------------------------------------------------------------------- #
# Helpers / CLI
# --------------------------------------------------------------------------- #
def _mark_published(meta: dict, platform: str) -> None:
    published_to = set(meta.get("published_to", []))
    published_to.add(platform)
    meta["published_to"] = sorted(published_to)
    meta["status"] = "published"
    meta[f"{platform}_published_at"] = dt.datetime.now().isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish approved videos to Instagram/Facebook.")
    parser.add_argument("--key", help="Single topic key (default: all approved for the date)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--all", action="store_true", help="All approved items for the date")
    parser.add_argument("--targets", default="instagram,facebook", help="Comma list: instagram,facebook")
    parser.add_argument("--dry-run", action="store_true", help="Show what would publish; no API calls")
    args = parser.parse_args()

    targets = {t.strip().lower() for t in args.targets.split(",") if t.strip()}
    items = find_approved(args.date, args.key, args.all)
    if not items:
        date = args.date or dt.date.today().isoformat()
        print(f"No approved items for {date}. Approve some first: python -m graph_bot.review approve <key>")
        return

    token = env("META_ACCESS_TOKEN")
    ig_user_id = env("IG_USER_ID")
    fb_page_id = env("FB_PAGE_ID")
    base_url = env("PUBLIC_BASE_URL")

    print(f"{len(items)} approved item(s); targets: {', '.join(sorted(targets))}")
    for _, meta in items:
        print(f"  - {meta.get('key')}")

    if args.dry_run:
        # Report readiness of each target without calling the API.
        checks = {
            "instagram": [("META_ACCESS_TOKEN", token), ("IG_USER_ID", ig_user_id), ("PUBLIC_BASE_URL", base_url)],
            "facebook": [("META_ACCESS_TOKEN", token), ("FB_PAGE_ID", fb_page_id)],
        }
        for tgt in sorted(targets):
            missing = [name for name, val in checks.get(tgt, []) if not val]
            state = "READY" if not missing else f"missing {', '.join(missing)}"
            print(f"  [dry-run] {tgt}: {state}")
        print("\n[dry-run] Nothing published. See docs/SETUP_META.md to configure .env.")
        return

    for meta_path, meta in items:
        if "instagram" in targets:
            if not (token and ig_user_id and base_url):
                print("  ! instagram skipped: set META_ACCESS_TOKEN, IG_USER_ID, PUBLIC_BASE_URL in .env")
            else:
                try:
                    publish_instagram(meta_path, meta, token, ig_user_id, base_url)
                except Exception as exc:
                    print(f"  ✗ instagram failed for {meta.get('key')}: {exc}")
        if "facebook" in targets:
            if not (token and fb_page_id):
                print("  ! facebook skipped: set META_ACCESS_TOKEN, FB_PAGE_ID in .env")
            else:
                try:
                    publish_facebook(meta_path, meta, token, fb_page_id)
                except Exception as exc:
                    print(f"  ✗ facebook failed for {meta.get('key')}: {exc}")


if __name__ == "__main__":
    main()
