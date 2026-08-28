"""YouTube Shorts publisher (Phase 3).

Uploads APPROVED videos as **private** (you flip to public in YouTube Studio, or
pass --privacy public once you trust it). Uses the YouTube Data API v3.

One-time setup (see docs/SETUP_YOUTUBE.md):
  1. Create a Google Cloud project, enable "YouTube Data API v3".
  2. Create an OAuth client ID (type: Desktop app).
  3. Download it as config/client_secret.json.
The first run opens a browser to authorize; the token is cached in
config/youtube_token.json for subsequent runs.

Usage:
    python -m graph_bot.publish.youtube --dry-run          # today's approved items
    python -m graph_bot.publish.youtube --key population
    python -m graph_bot.publish.youtube --all --privacy private
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from ..config import CONFIG_DIR
from . import find_approved, read_caption, save_meta

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "youtube_token.json"
TITLE_MAX = 100


def _require_google_libs():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        return Request, Credentials, InstalledAppFlow, build, MediaFileUpload
    except ImportError:
        sys.exit(
            "Google API libraries missing. Run:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        )


def get_service():
    Request, Credentials, InstalledAppFlow, build, _ = _require_google_libs()
    if not CLIENT_SECRET.exists():
        sys.exit(
            f"Missing {CLIENT_SECRET}. See docs/SETUP_YOUTUBE.md to create an OAuth client."
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _title_for(meta: dict) -> str:
    # Prefer the clickable title built at render time; fall back to the plain title.
    title = meta.get("yt_title") or meta.get("title", "World Statistics")
    if "#shorts" not in title.lower():
        candidate = f"{title} #Shorts"
        title = candidate if len(candidate) <= TITLE_MAX else title
    return title[:TITLE_MAX]


def upload_one(service, meta_path: Path, meta: dict, privacy: str, MediaFileUpload) -> None:
    video = Path(meta["video"])
    if not video.exists():
        print(f"  ! video missing, skipping: {video}")
        return
    body = {
        "snippet": {
            "title": _title_for(meta),
            "description": read_caption(meta_path),
            "tags": [h.lstrip("#") for h in (meta.get("hashtags") or [])] or None,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  ... {int(status.progress() * 100)}%")

    video_id = response["id"]
    meta["status"] = "published"
    meta["youtube_id"] = video_id
    meta["youtube_url"] = f"https://youtu.be/{video_id}"
    meta["published_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_meta(meta_path, meta)
    print(f"  ✅ {meta.get('key')} -> https://youtu.be/{video_id}  (privacy: {privacy})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish approved videos to YouTube.")
    parser.add_argument("--key", help="Single topic key (default: all approved for the date)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--all", action="store_true", help="All approved items for the date")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--dry-run", action="store_true", help="List what would upload; no API calls")
    args = parser.parse_args()

    items = find_approved(args.date, args.key, args.all)
    if not items:
        date = args.date or dt.date.today().isoformat()
        print(f"No approved items for {date}. Approve some first: python -m graph_bot.review approve <key>")
        return

    print(f"{len(items)} approved item(s):")
    for _, meta in items:
        print(f"  - {meta.get('key'):<18} {_title_for(meta)}")

    if args.dry_run:
        print("\n[dry-run] Nothing uploaded. Remove --dry-run to publish.")
        return

    _, _, _, _, MediaFileUpload = _require_google_libs()
    service = get_service()
    print(f"\nUploading as '{args.privacy}' ...")
    for meta_path, meta in items:
        upload_one(service, meta_path, meta, args.privacy, MediaFileUpload)


if __name__ == "__main__":
    main()
