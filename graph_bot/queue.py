"""Track what has been uploaded and what is next in the queue.

Uploads are manual (the YouTube API locks API-uploaded videos to Private), so the
pipeline cannot know what actually went live. This keeps a small log you update
as you post, and regenerates a human-readable UPLOAD_QUEUE.md.

Usage:
    python -m graph_bot.queue status                 # print + refresh the file
    python -m graph_bot.queue mark india_gdp         # mark one as uploaded
    python -m graph_bot.queue mark india_gdp --url https://youtu.be/xxxx
    python -m graph_bot.queue mark --series ml_concept --all
    python -m graph_bot.queue unmark india_gdp
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import store
from .config import (
    PROJECT_ROOT,
    load_settings,
    load_topics,
    resolve_path,
    topic_episode,
    topic_series,
)

QUEUE_MD = PROJECT_ROOT / "UPLOAD_QUEUE.md"

# Order series appear in the report.
SERIES_ORDER = ["india_in_data", "ml_concept", "world_in_data",
                "money", "ai_trends", "charts_lie", "sports"]

# series -> (YouTube playlist name, does that playlist exist yet?)
# Flip the flag to True once you have created the playlist on the channel.
PLAYLISTS: dict[str, tuple[str, bool]] = {
    "world_in_data": ("World in Data", True),
    "ml_concept": ("ML Concepts", True),
    "ai_trends": ("AI Trends", True),
    "money": ("Money & Cost of Living", True),
    "india_in_data": ("India in Data", True),
    "charts_lie": ("How Charts Lie", True),
    "sports": ("Sports in Data", False),
}


# The dashboard writes playlist name / "created on YouTube" overrides here, so
# both the CLI report and the UI agree on which playlists actually exist.
BRAND_JSON = PROJECT_ROOT / "data" / "brand.json"
_BRAND_CACHE: dict[str, Any] = {"stamp": None, "data": {}}


def _playlist_overrides() -> dict[str, Any]:
    try:
        st = BRAND_JSON.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _BRAND_CACHE["stamp"] != stamp:
        try:
            data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
            _BRAND_CACHE["data"] = data.get("playlists", {}) or {}
        except Exception:
            _BRAND_CACHE["data"] = {}
        _BRAND_CACHE["stamp"] = stamp
    return _BRAND_CACHE["data"]


def playlist_of(series: str) -> tuple[str, bool]:
    name, exists = PLAYLISTS.get(series, (series.replace("_", " ").title(), False))
    override = _playlist_overrides().get(series, {})
    if override.get("name"):
        name = str(override["name"])
    if "created" in override:
        exists = bool(override["created"])
    return name, exists

# Wave 3, re-cut 2026-08-27 against the 2026-05-29..08-27 export
# (49 videos, 20.6k views, +72 subs, 2.52% channel CTR).
#
#   pillar          n   med views   med v/day   %viewed   CTR      subs/1k
#   sports          2         849       609.1       23%   4.37%       0.00
#   world_in_data   8         603        75.2       25%   3.21%       0.32
#   ai_trends      12         362        27.1       30%   2.52%       0.38
#   money           8         251        26.1       26%   1.99%       0.00
#   india_in_data   7         189        48.8       17%   2.21%       0.99
#   ml_concept     10          52         2.7       22%   1.23%       4.10
#
# Sports is the breakout: 4.37% CTR against a 2.52% channel average, and
# "Most World Cup Titles" took 1,058 views on day one. Only two are live, so
# the sample is thin, but CTR that far above the channel is a real signal, not
# a launch spike. Sports therefore leads this wave.
#
# ML Concepts inverts the usual trade-off: worst reach (52 median views, 1.23%
# CTR) but by far the best subscriber conversion at 4.10 subs per 1,000 views,
# 4-12x every other pillar. It earns its place as an occasional release, not as
# a reach play — and its 32s median length is the main thing holding it back.
#
# Length still matters and is partly confounded with pillar: <=10s videos hold
# 33.8% viewed at 642 median views, while 30s+ collapses to 21.2% and 52 views.
# Anything over ~30s should be re-cut before posting.
RECOMMENDED: list[tuple[str, str]] = [
    ("cricket_odi_wins", "Sports leads on CTR (4.4% vs 2.5%) — India rivalry drives comments"),
    ("meat", "World in Data is the workhorse: 603 median views at 3.2% CTR"),
    ("cricket_t20_wins", "Completes the cricket set while the pillar is hot"),
    ("world_population", "Population videos are two of your top three all-time"),
    ("india_life", "India pulls 48.8 views/day — second-best reach after sports"),
    ("forest", "Broad-appeal World in Data ranking"),
    ("football_goals", "Sports again, spaced after the cricket run"),
    ("co2", "Climate heavyweight; pairs with the per-capita cut already live"),
    ("patents", "Dry ranking — kept late, these stall around 50 views"),
    ("science", "Dry ranking — same shape as patents"),
    ("football_intl_wins", "41.8s — re-cut shorter before posting; 30s+ videos halve retention"),
]


# --------------------------------------------------------------------------- #
# Log storage
# --------------------------------------------------------------------------- #
# Upload state lives in Postgres (see graph_bot.store): both the CLI and the
# dashboard write it, so a whole-file JSON rewrite could lose an update. These
# are thin re-exports so every caller keeps talking to graph_bot.queue.
def load_log() -> dict[str, Any]:
    """key -> {uploaded_at, url} for everything posted to YouTube."""
    return store.load_log()


def mark_uploaded(key: str, url: str | None = None,
                  uploaded_at: str | None = None) -> None:
    store.mark_uploaded(key, url, uploaded_at)


def unmark(key: str) -> bool:
    return store.unmark(key)


def set_link(key: str, url: str | None) -> bool:
    return store.set_link(key, url)


def load_discarded() -> dict[str, Any]:
    """key -> {discarded_at, reason, from, moved_to} for exports deliberately dropped.

    A discarded video was rendered and exported but will never be posted. It is
    kept out of the upload queue without being marked uploaded, which would
    otherwise put a video that never went live into the upload history.
    """
    return store.load_discarded()


# --------------------------------------------------------------------------- #
# Status derivation
# --------------------------------------------------------------------------- #
def _rendered_keys() -> set[str]:
    """Topics that have ever been rendered.

    Files on disk UNION the durable history, because retention deletes working
    copies once they have been exported. Without the union, a purged topic would
    read as "never rendered" and Launch Control would offer to remake it.
    """
    out = resolve_path(load_settings(), "output")
    on_disk = {p.parent.name for p in out.glob("*/*/metadata.json")}
    return on_disk | set(store.lifecycle_dates())


def _exported_keys() -> dict[str, str]:
    """key -> export folder path (most recent date wins)."""
    root = PROJECT_ROOT / "export"
    found: dict[str, str] = {}
    if not root.exists():
        return found
    for date_dir in sorted(root.iterdir()):
        # _discarded/ (and any other _-prefixed bin) is not a date folder.
        if not date_dir.is_dir() or date_dir.name.startswith("_"):
            continue
        for series_dir in date_dir.iterdir():
            if not series_dir.is_dir():
                continue
            for item in series_dir.iterdir():
                if item.is_dir():
                    # Folders are NN_key; strip the episode prefix.
                    key = item.name.split("_", 1)[1] if "_" in item.name else item.name
                    found[key] = str(item.relative_to(PROJECT_ROOT))
    return found


def build_status() -> dict[str, list[dict[str, Any]]]:
    log = load_log()
    discarded = load_discarded()
    rendered = _rendered_keys()
    exported = _exported_keys()

    by_series: dict[str, list[dict[str, Any]]] = {}
    for topic in load_topics():
        key = topic["key"]
        series = topic_series(topic)
        entry = {
            "key": key,
            "episode": topic_episode(topic),
            "title": topic.get("title", ""),
            "uploaded": key in log,
            "uploaded_at": log.get(key, {}).get("uploaded_at"),
            "url": log.get(key, {}).get("url"),
            "exported": exported.get(key),
            "rendered": key in rendered,
            "discarded": key in discarded,
            "discarded_at": discarded.get(key, {}).get("discarded_at"),
            "discard_reason": discarded.get(key, {}).get("reason"),
        }
        by_series.setdefault(series, []).append(entry)

    for items in by_series.values():
        items.sort(key=lambda e: e["episode"])
    return by_series


def _state(entry: dict[str, Any]) -> tuple[str, str]:
    if entry["uploaded"]:
        return "✅", "uploaded"
    if entry.get("discarded"):
        return "🗑", "discarded"
    if entry["exported"]:
        return "⏳", "ready to upload"
    if entry["rendered"]:
        return "🎬", "rendered (not exported)"
    return "⬜", "not made yet"


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def next_up(by_series: dict[str, list[dict[str, Any]]], count: int = 10) -> list[dict[str, Any]]:
    """The recommended upload order: curated picks first, then anything else ready."""
    everything = {e["key"]: e for items in by_series.values() for e in items}
    ready = {
        k: e for k, e in everything.items()
        if not e["uploaded"] and e["exported"] and not e.get("discarded")
    }

    picks: list[dict[str, Any]] = []
    for key, reason in RECOMMENDED:
        entry = ready.get(key)
        if entry:
            picks.append({**entry, "reason": reason})
        if len(picks) >= count:
            return picks

    chosen = {p["key"] for p in picks}
    for key, entry in ready.items():
        if key in chosen:
            continue
        picks.append({**entry, "reason": "ready to upload"})
        if len(picks) >= count:
            break
    return picks


def write_report(by_series: dict[str, list[dict[str, Any]]]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        "# Upload queue — Data in Motion",
        "",
        f"_Last refreshed {today} · `python -m graph_bot.queue status`_",
        "",
        "✅ uploaded  ⏳ ready to upload  🗑 discarded  🎬 rendered, not exported  ⬜ not made yet",
        "",
    ]

    total = sum(len(v) for v in by_series.values())
    done = sum(1 for v in by_series.values() for e in v if e["uploaded"])
    ready = sum(1 for v in by_series.values() for e in v
                if not e["uploaded"] and e["exported"] and not e.get("discarded"))
    lines += [f"**{done} uploaded · {ready} ready to upload · {total} topics total**", ""]

    # ---- what to upload next ----
    picks = next_up(by_series, 10)
    if picks:
        lines += [
            "---",
            "",
            "## 🎯 Upload next — recommended order",
            "",
            "_Ranked on how the channel is actually performing: money topics and"
            " counter-intuitive rankings first, technical topics later._",
            "",
            "| ▶ | Title | Add to playlist | Why | Folder |",
            "|---|---|---|---|---|",
        ]
        for i, p in enumerate(picks, 1):
            name, exists = playlist_of(topic_series({"key": p["key"]}))
            playlist = name if exists else f"{name} ⚠️"
            lines.append(
                f"| {i} | **{p['title']}** | {playlist} | {p['reason']} | `{p['exported']}` |"
            )
        todo = sorted({topic_series({"key": p["key"]}) for p in picks})
        missing = [playlist_of(s)[0] for s in todo if not playlist_of(s)[1]]
        if missing:
            lines += ["", "⚠️ = playlist does not exist yet — create it before uploading.", ""]
            lines += ["### Playlists to create first", ""]
            lines += [f"- **{m}**" for m in missing]
        lines += ["", "---", ""]

    ordered = [s for s in SERIES_ORDER if s in by_series]
    ordered += [s for s in sorted(by_series) if s not in SERIES_ORDER]

    for series in ordered:
        items = by_series[series]
        up = sum(1 for e in items if e["uploaded"])
        name, exists = playlist_of(series)
        badge = "" if exists else "  ⚠️ _playlist not created yet_"
        lines += [
            f"## {series}  ({up}/{len(items)} uploaded)",
            "",
            f"**Playlist:** {name}{badge}",
            "",
        ]
        lines += ["| # | Status | Title | Key |", "|---|---|---|---|"]
        for e in items:
            icon, _ = _state(e)
            title = e["title"]
            if e["url"]:
                title = f"[{title}]({e['url']})"
            lines.append(f"| {e['episode']:02d} | {icon} | {title} | `{e['key']}` |")
        lines.append("")

        nxt = [e for e in items
               if not e["uploaded"] and e["exported"] and not e.get("discarded")]
        if nxt:
            lines += [f"**Next up:** {nxt[0]['title']} — `{nxt[0]['exported']}`", ""]

    text = "\n".join(lines)
    QUEUE_MD.write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def cmd_status(_: argparse.Namespace) -> None:
    by_series = build_status()
    write_report(by_series)

    picks = next_up(by_series, 10)
    if picks:
        print("\n🎯 UPLOAD NEXT")
        for i, p in enumerate(picks, 1):
            print(f"  {i:>2}. {p['title']}")
            print(f"      {p['reason']}")

    ordered = [s for s in SERIES_ORDER if s in by_series]
    ordered += [s for s in sorted(by_series) if s not in SERIES_ORDER]
    for series in ordered:
        items = by_series[series]
        up = sum(1 for e in items if e["uploaded"])
        print(f"\n{series}  ({up}/{len(items)} uploaded)")
        for e in items:
            icon, _ = _state(e)
            print(f"  {e['episode']:02d} {icon}  {e['title']}")
        nxt = [e for e in items
               if not e["uploaded"] and e["exported"] and not e.get("discarded")]
        if nxt:
            print(f"   → next: {nxt[0]['key']}")
    print(f"\n📄 Written to {QUEUE_MD.relative_to(PROJECT_ROOT)}")


def cmd_mark(args: argparse.Namespace) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")

    if args.all:
        if not args.series:
            raise SystemExit("--all requires --series")
        keys = [t["key"] for t in load_topics() if topic_series(t) == args.series]
    elif args.key:
        keys = [args.key]
    else:
        raise SystemExit("Provide a topic key, or --series X --all")

    valid = {t["key"] for t in load_topics()}
    for key in keys:
        if key not in valid:
            print(f"  ! unknown topic: {key}")
            continue
        mark_uploaded(key, args.url if (args.url and len(keys) == 1) else None, now)
        print(f"  ✅ marked uploaded: {key}")

    write_report(build_status())


def cmd_unmark(args: argparse.Namespace) -> None:
    if unmark(args.key):
        write_report(build_status())
        print(f"  ↩️  unmarked: {args.key}")
    else:
        print(f"  (not marked): {args.key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track uploaded videos and the queue.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show the queue and refresh UPLOAD_QUEUE.md")
    p_status.set_defaults(func=cmd_status)

    p_mark = sub.add_parser("mark", help="Mark topic(s) as uploaded")
    p_mark.add_argument("key", nargs="?")
    p_mark.add_argument("--url", help="YouTube URL (single topic only)")
    p_mark.add_argument("--series", help="Series for bulk marking")
    p_mark.add_argument("--all", action="store_true", help="Mark the whole series")
    p_mark.set_defaults(func=cmd_mark)

    p_un = sub.add_parser("unmark", help="Undo an upload mark")
    p_un.add_argument("key")
    p_un.set_defaults(func=cmd_unmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
