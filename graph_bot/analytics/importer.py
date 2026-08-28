"""Load YouTube Studio analytics exports into Postgres.

YouTube Studio only retains rolling windows, so these zips are the only
long-term history that will ever exist. Two rules follow from that:

  * every source line is kept verbatim in raw_analytics_row, so a metric nobody
    thought to model today can still be derived tomorrow;
  * imports are idempotent — the same zip, or an overlapping date range, can be
    loaded any number of times without duplicating or double-counting.

Usage:
    python -m graph_bot.analytics init                 # create the schema
    python -m graph_bot.analytics import               # load analytics_data/*.zip
    python -m graph_bot.analytics import <file.zip>    # load one export
    python -m graph_bot.analytics status               # what is in the warehouse
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

from ..config import PROJECT_ROOT, load_topics, topic_series
from ..db import connect
from ..queue import load_log, playlist_of

ANALYTICS_DIR = PROJECT_ROOT / "analytics_data"
SCHEMA_SQL = Path(__file__).with_name("schema.sql")

# "Content 2026-05-29_2026-08-27 Data in Motion.zip"
RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[_ ](\d{4}-\d{2}-\d{2})")
# https://youtube.com/shorts/hEwUtHgfxi4?feature=share -> hEwUtHgfxi4
VIDEO_ID_RE = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/|/live/|embed/)([A-Za-z0-9_-]{11})")


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _int(v: str | None) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v.replace(",", "")))
    except ValueError:
        return None


def _num(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None


def _date(v: str | None) -> dt.date | None:
    """Parse either an ISO date or YouTube's 'Aug 9, 2026' publish format."""
    if not v:
        return None
    v = v.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _hms(v: str | None) -> int | None:
    """'0:00:18' -> 18 seconds."""
    if not v:
        return None
    parts = v.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    secs = 0
    for n in nums:
        secs = secs * 60 + n
    return secs


def topic_map() -> dict[str, dict[str, str]]:
    """YouTube video id -> topic metadata, taken from the upload log's URLs.

    The upload log is the only place that knows which topic became which video,
    because uploads are manual.
    """
    by_key = {t["key"]: t for t in load_topics()}
    out: dict[str, dict[str, str]] = {}
    for key, entry in load_log().items():
        url = entry.get("url") if isinstance(entry, dict) else None
        if not url:
            continue
        m = VIDEO_ID_RE.search(url)
        if not m:
            continue
        topic = by_key.get(key)
        series = topic_series(topic) if topic else None
        out[m.group(1)] = {
            "topic_key": key,
            "series": series,
            "playlist": playlist_of(series)[0] if series else None,
        }
    return out


def read_export(path: Path) -> dict[str, list[dict[str, str]]]:
    """Return {csv name: rows} for one exported zip."""
    files: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            text = zf.read(name).decode("utf-8-sig")
            files[name] = list(csv.DictReader(io.StringIO(text)))
    return files


def date_range(path: Path, files: dict[str, list[dict[str, str]]]) -> tuple[dt.date | None, dt.date | None]:
    """The window this export covers: from the filename, else from the data."""
    m = RANGE_RE.search(path.name)
    if m:
        return _date(m.group(1)), _date(m.group(2))
    days = [
        d for rows in files.values() for r in rows
        if (d := _date(r.get("Date"))) is not None
    ]
    return (min(days), max(days)) if days else (None, None)


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def init_schema() -> list[str]:
    """Create the warehouse. Safe to run repeatedly."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]


def _upsert_videos(cur: Any, rows: Iterable[dict[str, str]], mapping: dict[str, dict[str, str]]) -> int:
    """Insert or refresh every video seen in this export."""
    seen: dict[str, tuple] = {}
    for r in rows:
        vid = (r.get("Content") or "").strip()
        # "Total" is a summary line, not a video; ids are always 11 chars.
        if not vid or vid == "Total" or len(vid) != 11:
            continue
        meta = mapping.get(vid, {})
        seen[vid] = (
            vid,
            meta.get("topic_key"),
            meta.get("series"),
            meta.get("playlist"),
            (r.get("Video title") or "").strip() or None,
            _date(r.get("Video publish time")),
            _int(r.get("Duration")),
        )
    if not seen:
        return 0
    cur.executemany(
        """
        INSERT INTO video (video_id, topic_key, series, playlist, title,
                           published_at, duration_sec)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (video_id) DO UPDATE SET
            -- Never let a later export blank out something we already know.
            topic_key    = COALESCE(EXCLUDED.topic_key,    video.topic_key),
            series       = COALESCE(EXCLUDED.series,       video.series),
            playlist     = COALESCE(EXCLUDED.playlist,     video.playlist),
            title        = COALESCE(EXCLUDED.title,        video.title),
            published_at = COALESCE(EXCLUDED.published_at, video.published_at),
            duration_sec = COALESCE(EXCLUDED.duration_sec, video.duration_sec),
            last_seen    = now()
        """,
        list(seen.values()),
    )
    return len(seen)


def import_export(path: Path) -> dict[str, Any]:
    """Load one zip. Re-importing the same file updates it in place."""
    files = read_export(path)
    start, end = date_range(path, files)
    mapping = topic_map()

    table_rows = files.get("Table data.csv", [])
    chart_rows = files.get("Chart data.csv", [])
    total_rows = files.get("Totals.csv", [])

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics_import (source, range_start, range_end)
                VALUES (%s, %s, %s)
                ON CONFLICT (source) DO UPDATE SET
                    range_start = EXCLUDED.range_start,
                    range_end   = EXCLUDED.range_end,
                    imported_at = now()
                RETURNING id
                """,
                (path.name, start, end),
            )
            import_id = cur.fetchone()[0]

            # Re-import replaces this import's raw rows rather than stacking them.
            cur.execute("DELETE FROM raw_analytics_row WHERE import_id = %s", (import_id,))
            raw = [
                (import_id, name, i, json.dumps(row, ensure_ascii=False))
                for name, rows in files.items()
                for i, row in enumerate(rows, 1)
            ]
            cur.executemany(
                "INSERT INTO raw_analytics_row (import_id, source_file, row_no, payload)"
                " VALUES (%s, %s, %s, %s)",
                raw,
            )

            n_videos = _upsert_videos(cur, table_rows + chart_rows, mapping)

            # Daily views. Partitions must exist before the insert, so make one
            # for every distinct month present in this file.
            daily = []
            months = set()
            for r in chart_rows:
                day = _date(r.get("Date"))
                vid = (r.get("Content") or "").strip()
                if not day or len(vid) != 11:
                    continue
                months.add(day.replace(day=1))
                daily.append((vid, day, _int(r.get("Views")) or 0, import_id))
            for m in sorted(months):
                cur.execute("SELECT ensure_daily_partition(%s)", (m,))
            if daily:
                cur.executemany(
                    """
                    INSERT INTO video_daily_stats (video_id, day, views, import_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (video_id, day) DO UPDATE SET
                        views = EXCLUDED.views, import_id = EXCLUDED.import_id
                    -- Overlapping exports disagree about recent days because
                    -- YouTube keeps revising them. The export whose window ends
                    -- later is the settled one, so a staler file can never
                    -- overwrite it — whatever order the files are imported in.
                    WHERE COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = EXCLUDED.import_id),
                              '-infinity'::date) >=
                          COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = video_daily_stats.import_id),
                              '-infinity'::date)
                    """,
                    daily,
                )

            # Per-window aggregates. Column sets vary between exports, so every
            # metric is looked up defensively and left NULL when absent.
            period = []
            for r in table_rows:
                vid = (r.get("Content") or "").strip()
                if len(vid) != 11 or start is None or end is None:
                    continue
                period.append((
                    vid, start, end,
                    _int(r.get("Views")),
                    _num(r.get("Watch time (hours)")),
                    _int(r.get("Subscribers")),
                    _int(r.get("Thumbnail impressions")),
                    _num(r.get("Thumbnail click-through rate (%)")),
                    _hms(r.get("Average view duration")),
                    _num(r.get("Average percentage viewed (%)")),
                    import_id,
                ))
            if period:
                cur.executemany(
                    """
                    INSERT INTO video_period_stats (
                        video_id, range_start, range_end, views, watch_hours,
                        subscribers, impressions, ctr_pct, avg_view_sec,
                        avg_pct_viewed, import_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (video_id, range_start, range_end) DO UPDATE SET
                        views          = COALESCE(EXCLUDED.views, video_period_stats.views),
                        watch_hours    = COALESCE(EXCLUDED.watch_hours, video_period_stats.watch_hours),
                        subscribers    = COALESCE(EXCLUDED.subscribers, video_period_stats.subscribers),
                        impressions    = COALESCE(EXCLUDED.impressions, video_period_stats.impressions),
                        ctr_pct        = COALESCE(EXCLUDED.ctr_pct, video_period_stats.ctr_pct),
                        avg_view_sec   = COALESCE(EXCLUDED.avg_view_sec, video_period_stats.avg_view_sec),
                        avg_pct_viewed = COALESCE(EXCLUDED.avg_pct_viewed, video_period_stats.avg_pct_viewed),
                        import_id      = EXCLUDED.import_id
                    """,
                    period,
                )

            # The "Total" row is the channel's own figure for this window.
            total_row = next(
                (r for r in table_rows if (r.get("Content") or "").strip() == "Total"), None
            )
            if total_row is not None and start and end:
                cur.execute(
                    """
                    INSERT INTO channel_period_stats (
                        range_start, range_end, views, watch_hours, subscribers,
                        impressions, ctr_pct, avg_view_sec, avg_pct_viewed, import_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (range_start, range_end) DO UPDATE SET
                        views          = COALESCE(EXCLUDED.views, channel_period_stats.views),
                        watch_hours    = COALESCE(EXCLUDED.watch_hours, channel_period_stats.watch_hours),
                        subscribers    = COALESCE(EXCLUDED.subscribers, channel_period_stats.subscribers),
                        impressions    = COALESCE(EXCLUDED.impressions, channel_period_stats.impressions),
                        ctr_pct        = COALESCE(EXCLUDED.ctr_pct, channel_period_stats.ctr_pct),
                        avg_view_sec   = COALESCE(EXCLUDED.avg_view_sec, channel_period_stats.avg_view_sec),
                        avg_pct_viewed = COALESCE(EXCLUDED.avg_pct_viewed, channel_period_stats.avg_pct_viewed),
                        import_id      = EXCLUDED.import_id
                    """,
                    (start, end,
                     _int(total_row.get("Views")),
                     _num(total_row.get("Watch time (hours)")),
                     _int(total_row.get("Subscribers")),
                     _int(total_row.get("Thumbnail impressions")),
                     _num(total_row.get("Thumbnail click-through rate (%)")),
                     _hms(total_row.get("Average view duration")),
                     _num(total_row.get("Average percentage viewed (%)")),
                     import_id),
                )

            channel = [
                (day, _int(r.get("Views")) or 0, import_id)
                for r in total_rows
                if (day := _date(r.get("Date"))) is not None
            ]
            if channel:
                cur.executemany(
                    """
                    INSERT INTO channel_daily_stats (day, views, import_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (day) DO UPDATE SET
                        views = EXCLUDED.views, import_id = EXCLUDED.import_id
                    -- Overlapping exports disagree about recent days because
                    -- YouTube keeps revising them. The export whose window ends
                    -- later is the settled one, so a staler file can never
                    -- overwrite it — whatever order the files are imported in.
                    WHERE COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = EXCLUDED.import_id),
                              '-infinity'::date) >=
                          COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = channel_daily_stats.import_id),
                              '-infinity'::date)
                    """,
                    channel,
                )

            cur.execute(
                "UPDATE analytics_import SET rows_daily = %s, rows_period = %s,"
                " rows_channel = %s WHERE id = %s",
                (len(daily), len(period), len(channel), import_id),
            )

    unmapped = sorted({
        (r.get("Content") or "").strip()
        for r in table_rows
        if len((r.get("Content") or "").strip()) == 11
        and (r.get("Content") or "").strip() not in mapping
    })
    return {
        "source": path.name,
        "range": (start, end),
        "videos": n_videos,
        "daily": len(daily),
        "period": len(period),
        "channel": len(channel),
        "raw": len(raw),
        "unmapped": unmapped,
    }


def import_all(paths: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    files = list(paths) if paths else list(ANALYTICS_DIR.glob("*.zip"))
    # Oldest window first: newer exports then land last and win on overlaps.
    # (The upserts also guard against this, so order is belt-and-braces.)
    files.sort(key=lambda p: (date_range(p, {})[1] or dt.date.min, p.name))
    return [import_export(p) for p in files]


def status() -> dict[str, Any]:
    with connect() as conn:
        imports = conn.execute(
            "SELECT source, range_start, range_end, imported_at, rows_daily"
            " FROM analytics_import ORDER BY range_start"
        ).fetchall()
        counts = {}
        for table in ("video", "video_daily_stats", "video_period_stats",
                      "channel_period_stats", "channel_daily_stats",
                      "raw_analytics_row"):
            counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        parts = conn.execute(
            "SELECT c.relname FROM pg_class c"
            " JOIN pg_inherits i ON i.inhrelid = c.oid"
            " JOIN pg_class p ON p.oid = i.inhparent"
            " WHERE p.relname = 'video_daily_stats' ORDER BY 1"
        ).fetchall()
        mapped = conn.execute(
            "SELECT count(*) FILTER (WHERE topic_key IS NOT NULL), count(*) FROM video"
        ).fetchone()
        span = conn.execute(
            "SELECT min(day), max(day) FROM video_daily_stats"
        ).fetchone()
    return {
        "imports": imports,
        "counts": counts,
        "partitions": [p[0] for p in parts],
        "mapped": mapped,
        "span": span,
    }
