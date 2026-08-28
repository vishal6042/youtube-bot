"""CLI for the analytics warehouse."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..db import NotConfigured, safe_dsn
from .importer import ANALYTICS_DIR, import_all, init_schema, status


def cmd_init(_: argparse.Namespace) -> None:
    print(f"→ {safe_dsn()}")
    tables = init_schema()
    print(f"✅ schema ready — {len(tables)} tables: {', '.join(tables)}")


def cmd_import(args: argparse.Namespace) -> None:
    paths = [Path(p) for p in args.files] if args.files else None
    if paths:
        missing = [p for p in paths if not p.exists()]
        if missing:
            sys.exit(f"No such file: {missing[0]}")
    elif not ANALYTICS_DIR.exists() or not list(ANALYTICS_DIR.glob("*.zip")):
        sys.exit(f"No exports found in {ANALYTICS_DIR.relative_to(Path.cwd())}")

    for r in import_all(paths):
        lo, hi = r["range"]
        print(f"📦 {r['source']}")
        print(f"   {lo} → {hi} · {r['videos']} videos · {r['daily']} daily rows"
              f" · {r['period']} period rows · {r['channel']} channel days"
              f" · {r['raw']} raw lines")
        if r["unmapped"]:
            print(f"   ⚠ {len(r['unmapped'])} video(s) not matched to a topic:"
                  f" {', '.join(r['unmapped'][:5])}"
                  f"{' …' if len(r['unmapped']) > 5 else ''}")


def cmd_status(_: argparse.Namespace) -> None:
    s = status()
    print(f"→ {safe_dsn()}\n")
    print("Imports:")
    for src, lo, hi, at, rows in s["imports"]:
        print(f"  {lo} → {hi}  {rows:>5} daily rows  {src}  (loaded {at:%Y-%m-%d %H:%M})")
    print("\nRows:")
    for table, n in s["counts"].items():
        print(f"  {n:>8,}  {table}")
    mapped, total = s["mapped"]
    print(f"\nVideos mapped to a topic: {mapped}/{total}")
    lo, hi = s["span"]
    if lo:
        print(f"Daily coverage: {lo} → {hi}")
    print(f"Partitions: {', '.join(s['partitions']) or 'none yet'}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.analytics")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the schema (safe to re-run)").set_defaults(fn=cmd_init)

    p = sub.add_parser("import", help="load YouTube Studio export zips")
    p.add_argument("files", nargs="*", help="zip files (default: analytics_data/*.zip)")
    p.set_defaults(fn=cmd_import)

    sub.add_parser("status", help="what is in the warehouse").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    try:
        args.fn(args)
    except NotConfigured as exc:
        sys.exit(f"❌ {exc}")


if __name__ == "__main__":
    main()
