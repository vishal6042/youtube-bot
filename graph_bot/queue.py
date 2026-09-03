"""Track what has been uploaded and what is next in the queue.

Uploads are manual (the YouTube API locks API-uploaded videos to Private), so the
pipeline cannot know what actually went live. This keeps a small log you update
as you post. All state lives in Postgres (graph_bot.store); the dashboard is the
human-readable view — the old UPLOAD_QUEUE.md render was removed 2026-09-04.

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


# Playlist name / "created on YouTube" overrides live in the brand_playlist
# table (moved off data/brand.json 2026-09-04), so both the CLI report and the
# UI agree on which playlists actually exist. The JSON file remains a read-only
# fallback for when the database is down — stale beats broken.
BRAND_JSON = PROJECT_ROOT / "data" / "brand.json"
_BRAND_CACHE: dict[str, Any] = {"at": 0.0, "data": {}}


def _playlist_overrides() -> dict[str, Any]:
    import time
    if time.time() - _BRAND_CACHE["at"] < 5.0:
        return _BRAND_CACHE["data"]
    try:
        from . import store

        data = store.brand_load().get("playlists", {}) or {}
    except Exception:
        try:
            raw = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
            data = raw.get("playlists", {}) or {}
        except Exception:
            return _BRAND_CACHE["data"]
    _BRAND_CACHE.update(at=time.time(), data=data)
    return data


def playlist_of(series: str) -> tuple[str, bool]:
    name, exists = PLAYLISTS.get(series, (series.replace("_", " ").title(), False))
    override = _playlist_overrides().get(series, {})
    if override.get("name"):
        name = str(override["name"])
    if "created" in override:
        exists = bool(override["created"])
    return name, exists

# FALLBACK ONLY: the recommended order is now computed live from the analytics
# warehouse (see next_up / _series_scores). This hand-written list from the
# 2026-08-27 wave-3 analysis is used solely when the database is unreachable —
# a stale ranking beats no ranking, but nothing should be added here.
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
# Analytics-driven ranking
# --------------------------------------------------------------------------- #
# Scores come from the warehouse (video_daily view, filled by both the zip
# importer and the Analytics API sync), so the queue reorders itself whenever
# analytics are pulled. Deliberately a plain formula, not a model: it reruns on
# the hot /api/state path, and every rank must be explainable from the reason
# string alone.
#
# Measured facts the formula encodes (wave-3 analysis, still re-verified by the
# live numbers): median views/day is the fairest series signal (a median so one
# breakout can't carry a series), and length is the killer — <=10s videos held
# a 642 median while 30s+ collapsed to 52.
_RANK_CACHE: dict[str, Any] = {"at": 0.0, "scores": None, "channel": 1.0}
_DUR_CACHE: dict[str, Any] = {"at": 0.0, "data": {}}


def _series_scores(max_age: float = 60.0) -> tuple[dict[str, dict[str, Any]] | None, float]:
    """series -> {vpd, n} (median views/day-live per series) + channel median.

    Returns (None, _) when the warehouse is unreachable or empty, which sends
    next_up down the static-fallback path.
    """
    import time
    if time.time() - _RANK_CACHE["at"] < max_age:
        return _RANK_CACHE["scores"], _RANK_CACHE["channel"]
    try:
        from .db import connect

        with connect() as conn:
            rows = conn.execute(
                """
                WITH per_video AS (
                    SELECT series,
                           sum(views)::float / GREATEST(
                               COALESCE(max(day) - min(published_at),
                                        max(day) - min(day)) + 1, 1) AS vpd
                    FROM video_daily
                    WHERE series IS NOT NULL
                    GROUP BY series, video_id
                )
                SELECT series,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY vpd) AS median_vpd,
                       count(*) AS n
                FROM per_video
                GROUP BY series
                """
            ).fetchall()
        scores = {s: {"vpd": float(v), "n": int(n)} for s, v, n in rows if v is not None}
        if not scores:
            return _RANK_CACHE["scores"], _RANK_CACHE["channel"]
        medians = sorted(x["vpd"] for x in scores.values())
        channel = medians[len(medians) // 2]
    except Exception:
        # DB down: serve whatever we had (possibly None on a cold start).
        return _RANK_CACHE["scores"], _RANK_CACHE["channel"]
    _RANK_CACHE.update(at=time.time(), scores=scores, channel=channel)
    return scores, channel


def _export_durations(max_age: float = 60.0) -> dict[str, float]:
    """key -> duration_sec from the latest render's metadata.json."""
    import time
    if time.time() - _DUR_CACHE["at"] < max_age:
        return _DUR_CACHE["data"]
    latest: dict[str, Path] = {}
    out = resolve_path(load_settings(), "output")
    for p in sorted(out.glob("*/*/metadata.json")):  # date order, later wins
        latest[p.parent.name] = p
    data: dict[str, float] = {}
    for key, path in latest.items():
        try:
            dur = json.loads(path.read_text(encoding="utf-8")).get("duration_sec")
            if dur:
                data[key] = float(dur)
        except Exception:
            pass
    _DUR_CACHE.update(at=time.time(), data=data)
    return data


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def next_up(by_series: dict[str, list[dict[str, Any]]], count: int = 10) -> list[dict[str, Any]]:
    """The recommended upload order, ranked live from the analytics warehouse.

    Series momentum (median views/day of its live videos) carries the ranking;
    30s+ videos are demoted hard; a series never takes more than two consecutive
    slots; and episodes within a series always post in order.
    """
    everything = {e["key"]: e for items in by_series.values() for e in items}
    ready = {
        k: e for k, e in everything.items()
        if not e["uploaded"] and e["exported"] and not e.get("discarded")
    }
    if not ready:
        return []

    scores, channel_median = _series_scores()
    if not scores:
        return _next_up_fallback(ready, count)

    durations = _export_durations()

    # Group by the series each entry actually came from — re-deriving it from
    # the key alone loses explicit `series:` fields (rank_inflation is money,
    # not world_in_data).
    per_series: dict[str, list[dict[str, Any]]] = {}
    for series, items in by_series.items():
        for entry in items:
            if entry["key"] in ready:
                per_series.setdefault(series, []).append(entry)
    for items in per_series.values():
        items.sort(key=lambda e: e["episode"] or 0)  # episodes post in order

    def item_score(series: str, entry: dict[str, Any]) -> float:
        base = scores.get(series, {}).get("vpd", channel_median)
        dur = durations.get(entry["key"])
        if dur and dur >= 30:
            return base * 0.15
        if dur and dur > 15:
            return base * 0.7
        return base

    def reason_for(series: str, entry: dict[str, Any]) -> str:
        stat = scores.get(series)
        name, _ = playlist_of(series)
        dur = durations.get(entry["key"])
        if stat:
            r = f"{name}: {stat['vpd']:.0f} views/day median across {stat['n']} live videos"
        else:
            r = f"{name}: new series with no uploads yet — worth exploring"
        if dur and dur >= 30:
            r += (f" · ⚠ {dur:.0f}s — 30s+ videos median ~52 views vs 642 for ≤10s;"
                  " consider a re-cut")
        elif dur:
            r += f" · {dur:.0f}s"
        return r

    picks: list[dict[str, Any]] = []
    recent: list[str] = []
    while per_series and len(picks) < count:
        # A series may not take three consecutive slots, unless it is all
        # that's left — spacing demotes, it never blocks.
        allowed = [s for s in per_series if recent[-2:].count(s) < 2]
        pool = allowed or list(per_series)
        best = max(pool, key=lambda s: item_score(s, per_series[s][0]))
        entry = per_series[best].pop(0)
        if not per_series[best]:
            del per_series[best]
        # Carry the TRUE series: re-deriving it downstream from the key alone
        # loses explicit `series:` fields (rank_inflation is money, not world).
        picks.append({**entry, "series": best, "reason": reason_for(best, entry)})
        recent.append(best)
    return picks


def _next_up_fallback(ready: dict[str, dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Database-down path: the last hand-curated order, then anything ready."""
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


# ---- what to upload next ----
    picks = next_up(by_series, 10)
    if picks:
        lines += [
            "---",
            "",
            "## 🎯 Upload next — recommended order",
            "",
            "_Ranked live from the analytics warehouse: series views/day medians"
            " carry the order, 30s+ videos are demoted. Re-syncs with every"
            " analytics pull._",
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


def cmd_unmark(args: argparse.Namespace) -> None:
    if unmark(args.key):
        print(f"  ↩️  unmarked: {args.key}")
    else:
        print(f"  (not marked): {args.key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track uploaded videos and the queue.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show the queue")
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
