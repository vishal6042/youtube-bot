"""Long-form videos go up the same way as every other video.

There is no separate long-form uploader any more: a video is the upload-queue
item ``lf_<key>`` (see graph_bot.library), staged into the same batch and sent
by the same uploader as the Shorts (graph_bot.publish.upload), which also adds
its subtitle file as the English caption track. This module keeps the names
older code and the command line use.

    python -m graph_bot.longform.publish india_climb --check
    python -m graph_bot.longform.publish india_climb
"""
from __future__ import annotations

import argparse
import sys

from .. import library


def log_key(key: str) -> str:
    """The episode's row in the upload log: the same as its queue key."""
    return library.video_key(key)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.longform.publish")
    ap.add_argument("key")
    ap.add_argument("--check", action="store_true", help="say whether it can go up; upload nothing")
    args = ap.parse_args()
    ok, why = library.ready(log_key(args.key))
    print(f"{'Ready' if ok else 'Not ready'}: {why}")
    if args.check or not ok:
        return
    from ..publish.auth import AuthError
    from ..publish.upload import UploadError, upload

    try:
        r = upload(log_key(args.key), on_progress=lambda pct, stage: print(f"  {stage:<12} {pct:>3}%", end="\r"))
    except (UploadError, AuthError) as exc:
        sys.exit(f"\n{exc}")
    print(f"\nUploaded (Private): {r['url']}")
    for w in r["warnings"]:
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
