"""CLI for the operational store."""
from __future__ import annotations

import argparse
import sys

from ..db import NotConfigured, safe_dsn
from . import (
    LEGACY_DISCARDED,
    LEGACY_JOBS,
    LEGACY_LOG,
    LEGACY_ORDER,
    export_to_json,
    init_schema,
    job_counts,
    load_discarded,
    load_log,
    load_order,
    migrate_from_json,
)


def cmd_init(_: argparse.Namespace) -> None:
    print(f"→ {safe_dsn()}")
    print(f"✅ tables ready: {', '.join(init_schema())}")


def cmd_migrate(_: argparse.Namespace) -> None:
    print(f"→ {safe_dsn()}")
    init_schema()
    c = migrate_from_json()
    print(f"📥 {c['uploads']} uploads · {c['discarded']} discarded ·"
          f" {c['order']} ordered · {c['jobs']} jobs")
    print("   The JSON files are left on disk untouched as a backup;"
          " nothing reads them now.")


def cmd_status(_: argparse.Namespace) -> None:
    print(f"→ {safe_dsn()}\n")
    log, disc, order = load_log(), load_discarded(), load_order()
    print(f"  uploads     {len(log):>4}   ({sum(1 for v in log.values() if v.get('url'))} with a link)")
    print(f"  discarded   {len(disc):>4}")
    print(f"  queue order {len(order):>4}   {'(custom order set)' if order else '(recommended order)'}")
    counts = job_counts()
    print(f"  jobs        {sum(counts.values()):>4}   " +
          (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"))
    print("\nLegacy JSON still on disk (backup only):")
    for p in (LEGACY_LOG, LEGACY_DISCARDED, LEGACY_ORDER, LEGACY_JOBS):
        print(f"  {'✓' if p.exists() else '·'} {p.name}")


def cmd_export(args: argparse.Namespace) -> None:
    for name, path in export_to_json().items():
        print(f"  wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the tables").set_defaults(fn=cmd_init)
    sub.add_parser("migrate", help="load the legacy JSON files").set_defaults(fn=cmd_migrate)
    sub.add_parser("status", help="what is in the store").set_defaults(fn=cmd_status)
    sub.add_parser("export", help="dump the tables back to JSON").set_defaults(fn=cmd_export)

    args = ap.parse_args()
    try:
        args.fn(args)
    except NotConfigured as exc:
        sys.exit(f"❌ {exc}")


if __name__ == "__main__":
    main()
