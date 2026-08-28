"""Review queue: list / preview / approve / reject generated draft videos.

Every render writes metadata.json with status "draft". Publishing (later phases)
only ever acts on items whose status is "approved" — so this CLI is the human
gate that sits between rendering and posting.

Usage:
    python -m graph_bot.review list                 # today's queue
    python -m graph_bot.review list --all            # every date
    python -m graph_bot.review preview population     # open the mp4 in your player
    python -m graph_bot.review approve population
    python -m graph_bot.review approve --all          # approve every draft for the date
    python -m graph_bot.review reject developers --note "bad estimates"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from .config import load_settings, resolve_path

_STATUS_ICON = {"draft": "•", "approved": "✅", "rejected": "✗", "published": "📤"}


# --------------------------------------------------------------------------- #
# Metadata discovery
# --------------------------------------------------------------------------- #
def _output_root() -> Path:
    return resolve_path(load_settings(), "output")


def _iter_metadata(date: str | None, all_dates: bool) -> Iterable[Path]:
    root = _output_root()
    if all_dates:
        yield from sorted(root.glob("*/*/metadata.json"))
    else:
        date = date or dt.date.today().isoformat()
        yield from sorted((root / date).glob("*/metadata.json"))


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _find_one(key: str, date: str | None) -> tuple[Path, dict[str, Any]]:
    date = date or dt.date.today().isoformat()
    path = _output_root() / date / key / "metadata.json"
    if not path.exists():
        sys.exit(f"No draft found for '{key}' on {date} ({path})")
    return path, _load(path)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_list(args: argparse.Namespace) -> None:
    rows = list(_iter_metadata(args.date, args.all))
    if not rows:
        where = "any date" if args.all else (args.date or dt.date.today().isoformat())
        print(f"Queue empty for {where}.")
        return
    print(f"{'STATUS':<9} {'DATE':<12} {'KEY':<18} TITLE")
    for path in rows:
        m = _load(path)
        status = m.get("status", "draft")
        icon = _STATUS_ICON.get(status, "?")
        date = path.parent.parent.name
        print(f"{icon} {status:<7} {date:<12} {m.get('key',''):<18} {m.get('title','')}")


def cmd_preview(args: argparse.Namespace) -> None:
    path, meta = _find_one(args.key, args.date)
    video = Path(meta["video"])
    if not video.exists():
        sys.exit(f"Video file missing: {video}")
    print(f"Opening {video} ...")
    _open_in_player(video)


def cmd_approve(args: argparse.Namespace) -> None:
    _bulk_set_status(args, "approved")


def cmd_reject(args: argparse.Namespace) -> None:
    _bulk_set_status(args, "rejected")


def _bulk_set_status(args: argparse.Namespace, status: str) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    stamp_field = f"{status}_at"

    if getattr(args, "all", False):
        targets = [(p, _load(p)) for p in _iter_metadata(args.date, all_dates=False)]
        targets = [(p, m) for p, m in targets if m.get("status") == "draft"]
        if not targets:
            print("No draft items to update.")
            return
    else:
        if not args.key:
            sys.exit("Provide a topic key or use --all.")
        targets = [_find_one(args.key, args.date)]

    for path, meta in targets:
        meta["status"] = status
        meta[stamp_field] = now
        if getattr(args, "note", None):
            meta["note"] = args.note
        _save(path, meta)
        print(f"{_STATUS_ICON.get(status,'?')} {status}: {meta.get('key')} ({path.parent.parent.name})")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _open_in_player(video: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(video))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(video)], check=False)
        else:
            subprocess.run(["xdg-open", str(video)], check=False)
    except Exception as exc:  # pragma: no cover
        print(f"Could not auto-open player ({exc}). Path: {video}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review generated draft videos.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List the queue")
    p_list.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_list.add_argument("--all", action="store_true", help="All dates")
    p_list.set_defaults(func=cmd_list)

    p_prev = sub.add_parser("preview", help="Open a video in your player")
    p_prev.add_argument("key")
    p_prev.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_prev.set_defaults(func=cmd_preview)

    p_appr = sub.add_parser("approve", help="Approve a draft (or --all)")
    p_appr.add_argument("key", nargs="?")
    p_appr.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_appr.add_argument("--all", action="store_true", help="Approve every draft for the date")
    p_appr.add_argument("--note", help="Optional note")
    p_appr.set_defaults(func=cmd_approve)

    p_rej = sub.add_parser("reject", help="Reject a draft (or --all)")
    p_rej.add_argument("key", nargs="?")
    p_rej.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_rej.add_argument("--all", action="store_true", help="Reject every draft for the date")
    p_rej.add_argument("--note", help="Optional note")
    p_rej.set_defaults(func=cmd_reject)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
