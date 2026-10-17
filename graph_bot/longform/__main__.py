"""CLI: python -m graph_bot.longform list | build|shorts <key> [--only a,b] [--force] | thumbnail <key>"""
from __future__ import annotations

import argparse

from . import list_keys, summary
from .build import build
from .shorts import build_shorts


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.longform")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="episodes and where each one stands")
    b = sub.add_parser("build", help="render an episode (only changed chapters are redone)")
    b.add_argument("key")
    b.add_argument("--only", help="comma-separated chapter ids to rebuild")
    b.add_argument("--force", action="store_true", help="rebuild chapters even if unchanged")
    t = sub.add_parser("thumbnail", help="redraw just the video's thumbnail (no render)")
    t.add_argument("key")
    s = sub.add_parser("shorts", help="render a vertical Short per chapter (skips short.skip)")
    s.add_argument("key")
    s.add_argument("--only", help="comma-separated chapter ids to rebuild")
    s.add_argument("--force", action="store_true", help="rebuild Shorts even if unchanged")
    args = ap.parse_args()

    if args.cmd == "list":
        for key in list_keys():
            s = summary(key)
            m, sec = divmod(int(s["secs"]), 60)
            print(f"{key}: {s['title']}  |  {len(s['chapters'])} chapters, {s['words']} words, "
                  f"{m}:{sec:02d}  |  {s['rendered']} rendered"
                  f"{'  |  video ready' if s['has_video'] and not s['video_stale'] else ''}")
        return

    if args.cmd == "thumbnail":
        from . import load, out_dir
        from .thumbnail_hero import build_hero
        from ..config import load_settings

        ep = load(args.key)
        if not ep.get("thumbnail"):
            raise SystemExit("This script has no thumbnail: block; the generic one is made with the render.")
        print(build_hero(ep, out_dir(args.key) / "thumbnail.jpg", load_settings()))
        return
    run = build_shorts if args.cmd == "shorts" else build
    run(args.key, only=args.only.split(",") if args.only else None, force=args.force)


if __name__ == "__main__":
    main()
