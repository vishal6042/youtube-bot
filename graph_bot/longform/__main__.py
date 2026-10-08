"""CLI: python -m graph_bot.longform list | build <key> [--only a,b] [--force]"""
from __future__ import annotations

import argparse

from . import list_keys, summary
from .build import build


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.longform")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="episodes and where each one stands")
    b = sub.add_parser("build", help="render an episode (only changed chapters are redone)")
    b.add_argument("key")
    b.add_argument("--only", help="comma-separated chapter ids to rebuild")
    b.add_argument("--force", action="store_true", help="rebuild chapters even if unchanged")
    args = ap.parse_args()

    if args.cmd == "list":
        for key in list_keys():
            s = summary(key)
            m, sec = divmod(int(s["secs"]), 60)
            print(f"{key}: {s['title']}  |  {len(s['chapters'])} chapters, {s['words']} words, "
                  f"{m}:{sec:02d}  |  {s['rendered']} rendered"
                  f"{'  |  video ready' if s['has_video'] and not s['video_stale'] else ''}")
        return

    build(args.key, only=args.only.split(",") if args.only else None, force=args.force)


if __name__ == "__main__":
    main()
