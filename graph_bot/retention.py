"""Disk retention: delete working copies and exports once they are disposable.

The durations are measured from a LIFECYCLE EVENT, never from the folder's date:

    output/<date>/<key>/          deleted N days after the topic was EXPORTED
    export/<date>/<series>/<key>/ deleted N days after the video was UPLOADED

and — the rule that matters most — **anything not yet uploaded is never
deleted**, however old it gets. The channel produces faster than it can post, so
a three-month-old staged video is a backlog item, not an abandoned one. A blind
"delete exports older than 30 days" rule would quietly destroy finished videos
that were still waiting their turn, and because the upload queue is built by
scanning the export folder they would not even show up as missing.

Deleting folders is only safe because `topic_lifecycle` in Postgres remembers
that a topic was rendered and exported. Without that, purging output/ would make
the whole back catalogue look "never rendered" and Launch Control would offer to
re-render all of it.

Usage:
    python -m graph_bot.retention plan     # what would go, and why (default)
    python -m graph_bot.retention apply    # actually delete
    python -m graph_bot.retention sync     # fold today's disk state into history
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path
from typing import Any

from . import store
from .config import PROJECT_ROOT, load_settings, load_topics, resolve_path
from .queue import _exported_keys, load_discarded, load_log

DEFAULTS = {
    "output_days_after_export": 7,
    "export_days_after_upload": 30,
    "stale_warn_days": 60,
}


def policy() -> dict[str, int]:
    cfg = (load_settings().get("retention") or {})
    return {k: int(cfg.get(k, v)) for k, v in DEFAULTS.items()}


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Sync: fold what is on disk into the durable history
# --------------------------------------------------------------------------- #
def scan_disk() -> dict[str, dict[str, Any]]:
    """key -> render/export dates and paths, read from the filesystem."""
    out_root = resolve_path(load_settings(), "output")
    found: dict[str, dict[str, Any]] = {}

    for meta in out_root.glob("*/*/metadata.json"):
        key, date = meta.parent.name, meta.parent.parent.name
        rec = found.setdefault(key, {"topic_key": key, "output_dirs": []})
        rec["output_dirs"].append(meta.parent)
        if not rec.get("first_rendered_at") or date < rec["first_rendered_at"]:
            rec["first_rendered_at"] = date
        if not rec.get("last_rendered_at") or date > rec["last_rendered_at"]:
            rec["last_rendered_at"] = date

    for key, rel in _exported_keys().items():
        rec = found.setdefault(key, {"topic_key": key, "output_dirs": []})
        rec["export_path"] = rel
        rec["last_exported_at"] = Path(rel).parts[1] if len(Path(rel).parts) > 1 else None

    return found


def sync() -> int:
    """Push today's disk state into topic_lifecycle. Dates only move forward."""
    disk = scan_disk()
    known = {t["key"] for t in load_topics()}
    records = [
        {k: v for k, v in rec.items() if k != "output_dirs"}
        for key, rec in disk.items() if key in known
    ]
    return store.sync_lifecycle(records)


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #
def plan(today: dt.date | None = None) -> dict[str, Any]:
    """Exactly what a purge would delete, with the reason for each item."""
    today = today or dt.date.today()
    p = policy()
    sync()                        # never plan against stale history
    disk = scan_disk()
    log = load_log()
    discarded = load_discarded()
    life = store.load_lifecycle()
    titles = {t["key"]: t.get("title", "") for t in load_topics()}

    output_items: list[dict[str, Any]] = []
    export_items: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    kept_unposted = 0
    known = set(titles)

    for key, rec in sorted(disk.items()):
        # Folders whose key is not a configured topic — leftovers of an older
        # export layout. Reported, never auto-deleted: silently removing things
        # the policy cannot reason about is exactly the wrong default.
        if key not in known:
            rel = rec.get("export_path")
            if rel:
                d = PROJECT_ROOT / rel
                orphans.append({"key": key, "path": rel,
                                "bytes": _dir_size(d) if d.exists() else 0})
            continue
        uploaded_at = _date((log.get(key) or {}).get("uploaded_at"))
        exported_at = _date(rec.get("last_exported_at")
                            or (life.get(key) or {}).get("last_exported_at"))

        # ---- output/: disposable once the topic has been exported ----
        # A topic rendered on several days has one folder per day. Those are
        # generations of the same video, so they collapse into a single row with
        # the total size; `paths` keeps every folder for the delete step.
        if exported_at is not None:
            age = (today - exported_at).days
            if age >= p["output_days_after_export"]:
                dirs = sorted(rec.get("output_dirs", []), key=lambda d: d.parent.name)
                if dirs:
                    dates = [d.parent.name for d in dirs]
                    output_items.append({
                        "key": key, "title": titles.get(key, key),
                        "paths": [str(d.relative_to(PROJECT_ROOT)) for d in dirs],
                        "copies": len(dirs),
                        "dates": dates,
                        "bytes": sum(_dir_size(d) for d in dirs),
                        "reason": (f"{len(dirs)} render{'s' if len(dirs) > 1 else ''}"
                                   f" ({', '.join(dates)}) · exported {exported_at}"
                                   f" ({age}d ago)"),
                    })

        # ---- export/: disposable only once the video is actually live ----
        rel = rec.get("export_path")
        if not rel:
            continue
        if key in discarded:
            continue          # already moved to export/_discarded/ by hand
        if uploaded_at is None:
            kept_unposted += 1
            days_staged = (today - exported_at).days if exported_at else None
            if days_staged is not None and days_staged >= p["stale_warn_days"]:
                stale.append({"key": key, "title": titles.get(key, key),
                              "days": days_staged, "path": rel})
            continue          # NEVER delete something that has not gone live
        age = (today - uploaded_at).days
        if age >= p["export_days_after_upload"]:
            d = PROJECT_ROOT / rel
            export_items.append({
                "key": key, "title": titles.get(key, key),
                "paths": [rel], "copies": 1, "dates": [Path(rel).parts[1]],
                "bytes": _dir_size(d) if d.exists() else 0,
                "reason": f"uploaded {uploaded_at} ({age}d ago)",
            })

    return {
        "policy": p,
        "today": str(today),
        "output": output_items,
        "export": export_items,
        "stale": stale,
        "orphans": orphans,
        "kept_unposted": kept_unposted,
        "bytes": sum(i["bytes"] for i in output_items + export_items),
    }


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
def apply(dry_run: bool = False, today: dt.date | None = None) -> dict[str, Any]:
    """Delete what the plan lists. Records the run either way."""
    p = plan(today)
    deleted: list[dict[str, Any]] = []
    freed = 0

    if not dry_run:
        for kind, items in (("output", p["output"]), ("export", p["export"])):
            root = (PROJECT_ROOT / kind).resolve()
            for item in items:
                gone = []
                for rel in item["paths"]:
                    target = PROJECT_ROOT / rel
                    # Refuse to touch anything outside the two managed roots.
                    if not str(target.resolve()).startswith(str(root)):
                        print(f"  ! refusing to delete outside {kind}/: {rel}")
                        continue
                    if not target.exists():
                        continue
                    size = _dir_size(target)
                    shutil.rmtree(target)
                    freed += size
                    gone.append(rel)
                if gone:
                    store.mark_purged(item["key"], kind)
                    deleted.append({**item, "kind": kind, "paths": gone})

    run_id = store.record_retention_run(
        dry_run=dry_run,
        output_purged=0 if dry_run else sum(1 for d in deleted if d["kind"] == "output"),
        export_purged=0 if dry_run else sum(1 for d in deleted if d["kind"] == "export"),
        bytes_freed=freed,
        detail=deleted if not dry_run else (p["output"] + p["export"]),
    )
    return {**p, "run_id": run_id, "deleted": deleted, "freed": freed, "dry_run": dry_run}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _mb(n: int) -> str:
    return f"{n / 1e6:.0f} MB" if n else "0 MB"


def _print_plan(p: dict[str, Any]) -> None:
    pol = p["policy"]
    print(f"Policy: output/ {pol['output_days_after_export']}d after export ·"
          f" export/ {pol['export_days_after_upload']}d after upload ·"
          f" never delete anything unposted\n")

    for kind, label in (("output", "output/ (working copies)"),
                        ("export", "export/ (published, now on YouTube)")):
        items = p[kind]
        folders = sum(i.get("copies", 1) for i in items)
        print(f"{label}: {len(items)} video(s) / {folders} folder(s),"
              f" {_mb(sum(i['bytes'] for i in items))}")
        for i in items[:12]:
            copies = f" x{i['copies']}" if i.get("copies", 1) > 1 else "   "
            print(f"   {i['bytes']/1e6:6.1f} MB{copies}  {i['title'][:32]:<32} {i['reason']}")
        if len(items) > 12:
            print(f"   … and {len(items) - 12} more")
        print()

    print(f"Kept because not uploaded yet: {p['kept_unposted']} export(s) — never deleted.")
    if p["orphans"]:
        mb = sum(o["bytes"] for o in p["orphans"]) / 1e6
        print(f"\nUnrecognised export folders (not a configured topic):"
              f" {len(p['orphans'])}, {mb:.0f} MB — left alone, delete by hand if stale:")
        for o in p["orphans"][:6]:
            print(f"   {o['bytes']/1e6:6.1f} MB  {o['path']}")
    if p["stale"]:
        print(f"\n⚠ Staged but unposted for {p['policy']['stale_warn_days']}+ days:")
        for s in p["stale"]:
            print(f"   {s['days']:>4}d  {s['title']}")
    print(f"\nTotal reclaimable now: {_mb(p['bytes'])}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.retention")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("plan", help="show what would be deleted (default)")
    ap_apply = sub.add_parser("apply", help="actually delete")
    ap_apply.add_argument("--yes", action="store_true", help="skip the confirmation")
    sub.add_parser("sync", help="fold today's disk state into the lifecycle history")

    args = ap.parse_args()
    cmd = args.cmd or "plan"

    if cmd == "sync":
        print(f"✅ lifecycle synced for {sync()} topic(s)")
        return

    p = plan()
    _print_plan(p)

    if cmd == "plan":
        print("\nNothing deleted. Run `python -m graph_bot.retention apply` to purge.")
        return

    if not p["output"] and not p["export"]:
        print("\nNothing to delete.")
        return
    if not args.yes:
        folders = sum(i.get("copies", 1) for i in p["output"] + p["export"])
        reply = input(f"\nDelete {folders} folder(s) across"
                      f" {len(p['output']) + len(p['export'])} video(s),"
                      f" {_mb(p['bytes'])}? [y/N] ").strip().lower()
        if reply != "y":
            sys.exit("Aborted.")

    r = apply()
    print(f"\n🗑 deleted {len(r['deleted'])} folder(s), freed {_mb(r['freed'])}"
          f" (run #{r['run_id']})")


if __name__ == "__main__":
    main()
