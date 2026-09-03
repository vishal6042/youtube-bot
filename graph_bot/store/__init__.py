"""Operational state in Postgres: uploads, discards, queue order, jobs.

Replaces the read-modify-write JSON files under data/. Those files were rewritten
whole on every change, with no lock and no atomic replace, by two writers (the
CLI and the dashboard) — so a concurrent mark could lose an update and a crash
mid-write could truncate the entire upload history.

Every mutation here is one statement, so it either happens or it doesn't.

    python -m graph_bot.store init      # create the tables
    python -m graph_bot.store migrate   # load the existing JSON files
    python -m graph_bot.store status
    python -m graph_bot.store export    # write the tables back out as JSON
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from ..db import connect

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
DATA_DIR = PROJECT_ROOT / "data"

# The JSON files this replaced. Kept on disk as a backup and as the input to
# `migrate`; nothing reads them at runtime any more.
LEGACY_LOG = DATA_DIR / "upload_log.json"
LEGACY_DISCARDED = DATA_DIR / "discarded.json"
LEGACY_ORDER = DATA_DIR / "queue_order.json"
LEGACY_JOBS = DATA_DIR / "dashboard_jobs.json"


def init_schema() -> list[str]:
    with connect() as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            " AND tablename IN ('upload_log','discarded','queue_order','job')"
            " ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]


# --------------------------------------------------------------------------- #
# Timestamps
# --------------------------------------------------------------------------- #
def _iso(ts: dt.datetime | None) -> str | None:
    """Render a stored timestamp the way the JSON files did.

    The legacy values were naive local ISO strings ('2026-08-10T21:54:58') and
    the UI both displays and sorts them as strings, so the read path keeps
    producing exactly that.
    """
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone().replace(tzinfo=None)
    return ts.isoformat(timespec="seconds")


def _parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Upload log
# --------------------------------------------------------------------------- #
def load_log() -> dict[str, Any]:
    """key -> {uploaded_at, url} — the same shape the JSON file had."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT topic_key, uploaded_at, url FROM upload_log"
        ).fetchall()
    out: dict[str, Any] = {}
    for key, at, url in rows:
        entry: dict[str, Any] = {"uploaded_at": _iso(at)}
        if url:
            entry["url"] = url
        out[key] = entry
    return out


def mark_uploaded(key: str, url: str | None = None,
                  uploaded_at: str | None = None) -> None:
    """Record a topic as posted. One statement, so no read-modify-write race."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO upload_log (topic_key, uploaded_at, url)
            VALUES (%s, %s, %s)
            ON CONFLICT (topic_key) DO UPDATE SET
                uploaded_at = EXCLUDED.uploaded_at,
                url         = COALESCE(EXCLUDED.url, upload_log.url),
                updated_at  = now()
            """,
            (key, _parse(uploaded_at) or dt.datetime.now(), (url or "").strip() or None),
        )


def unmark(key: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM upload_log WHERE topic_key = %s", (key,))
        return cur.rowcount > 0


def set_link(key: str, url: str | None) -> bool:
    """Set or clear the YouTube link, leaving uploaded_at alone."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE upload_log SET url = %s, updated_at = now() WHERE topic_key = %s",
            ((url or "").strip() or None, key),
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Discarded
# --------------------------------------------------------------------------- #
def load_discarded() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT topic_key, discarded_at, reason, from_path, moved_to FROM discarded"
        ).fetchall()
    return {
        key: {"discarded_at": _iso(at), "reason": reason,
              "from": from_path, "moved_to": moved_to}
        for key, at, reason, from_path, moved_to in rows
    }


def discard(key: str, reason: str = "", from_path: str | None = None,
            moved_to: str | None = None, discarded_at: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO discarded (topic_key, discarded_at, reason, from_path, moved_to)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (topic_key) DO UPDATE SET
                discarded_at = EXCLUDED.discarded_at,
                reason       = EXCLUDED.reason,
                from_path    = EXCLUDED.from_path,
                moved_to     = EXCLUDED.moved_to
            """,
            (key, _parse(discarded_at) or dt.datetime.now(), (reason or "").strip(),
             from_path, moved_to),
        )


def restore(key: str) -> dict[str, Any] | None:
    """Remove the discard record and return it, atomically."""
    with connect() as conn:
        row = conn.execute(
            "DELETE FROM discarded WHERE topic_key = %s"
            " RETURNING discarded_at, reason, from_path, moved_to",
            (key,),
        ).fetchone()
    if row is None:
        return None
    at, reason, from_path, moved_to = row
    return {"discarded_at": _iso(at), "reason": reason,
            "from": from_path, "moved_to": moved_to}


# --------------------------------------------------------------------------- #
# Manual upload order
# --------------------------------------------------------------------------- #
def load_order() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT topic_key FROM queue_order ORDER BY position"
        ).fetchall()
    return [r[0] for r in rows]


def save_order(keys: list[str]) -> None:
    """Replace the whole order in one transaction."""
    with connect() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM queue_order")
            if keys:
                conn.cursor().executemany(
                    "INSERT INTO queue_order (topic_key, position) VALUES (%s, %s)",
                    [(k, i) for i, k in enumerate(keys)],
                )


def clear_order() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM queue_order")


def remove_from_order(key: str) -> None:
    """Drop one key and close the gap, so positions stay contiguous."""
    with connect() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM queue_order WHERE topic_key = %s", (key,))
            conn.execute(
                "UPDATE queue_order o SET position = r.rn - 1 FROM ("
                "  SELECT topic_key, row_number() OVER (ORDER BY position) AS rn"
                "  FROM queue_order) r"
                " WHERE o.topic_key = r.topic_key AND o.position <> r.rn - 1"
            )


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def save_job(d: dict[str, Any]) -> None:
    """Upsert one job record. Called per job, never as a whole-history rewrite."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO job (id, label, status, keys, current_key,
                             created_at, started_at, finished_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                label = EXCLUDED.label, status = EXCLUDED.status,
                keys = EXCLUDED.keys, current_key = EXCLUDED.current_key,
                started_at = EXCLUDED.started_at, finished_at = EXCLUDED.finished_at,
                payload = EXCLUDED.payload
            """,
            (d["id"], d.get("label"), d.get("status", "unknown"),
             list(d.get("keys") or []), d.get("current_key"),
             _parse(d.get("created_at")) or dt.datetime.now(),
             _parse(d.get("started_at")), _parse(d.get("finished_at")),
             json.dumps(d, ensure_ascii=False)),
        )


def load_jobs(limit: int = 40) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM job ORDER BY created_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [r[0] for r in rows]


def job_counts() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute("SELECT status, count(*) FROM job GROUP BY status").fetchall()
    return {s: n for s, n in rows}


# --------------------------------------------------------------------------- #
# Topic lifecycle (survives retention deleting the folders)
# --------------------------------------------------------------------------- #
def load_lifecycle() -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT topic_key, first_rendered_at, last_rendered_at, last_exported_at,"
            " export_path, output_purged_at, export_purged_at FROM topic_lifecycle"
        ).fetchall()
    return {
        key: {"first_rendered_at": str(first) if first else None,
              "last_rendered_at": str(last) if last else None,
              "last_exported_at": str(exp) if exp else None,
              "export_path": path,
              "output_purged_at": _iso(op), "export_purged_at": _iso(ep)}
        for key, first, last, exp, path, op, ep in rows
    }


_LIFECYCLE_CACHE: dict[str, Any] = {"at": 0.0, "dates": {}}


def lifecycle_dates(max_age: float = 5.0) -> dict[str, str]:
    """key -> last_rendered_at, cached briefly.

    Called once per topic in some loops, so it must not be a query each time.
    Returns {} if the database is unreachable: the filesystem answer alone is a
    safe degradation (it under-reports history, it never invents it).
    """
    import time
    if time.time() - _LIFECYCLE_CACHE["at"] < max_age:
        return _LIFECYCLE_CACHE["dates"]
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT topic_key, last_rendered_at FROM topic_lifecycle"
                " WHERE last_rendered_at IS NOT NULL"
            ).fetchall()
        dates = {k: str(d) for k, d in rows}
    except Exception:
        return _LIFECYCLE_CACHE["dates"]
    _LIFECYCLE_CACHE.update(at=time.time(), dates=dates)
    return dates


def sync_lifecycle(records: list[dict[str, Any]]) -> int:
    """Fold what is on disk right now into the history.

    Dates only ever move forward and are never cleared, so a purge cannot make a
    topic look like it was never rendered.
    """
    if not records:
        return 0
    with connect() as conn:
        conn.cursor().executemany(
            """
            INSERT INTO topic_lifecycle (topic_key, first_rendered_at,
                                         last_rendered_at, last_exported_at, export_path)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (topic_key) DO UPDATE SET
                first_rendered_at = LEAST(
                    COALESCE(topic_lifecycle.first_rendered_at, EXCLUDED.first_rendered_at),
                    COALESCE(EXCLUDED.first_rendered_at, topic_lifecycle.first_rendered_at)),
                last_rendered_at  = GREATEST(topic_lifecycle.last_rendered_at,
                                             EXCLUDED.last_rendered_at),
                last_exported_at  = GREATEST(topic_lifecycle.last_exported_at,
                                             EXCLUDED.last_exported_at),
                export_path       = COALESCE(EXCLUDED.export_path, topic_lifecycle.export_path),
                updated_at        = now()
            """,
            [(r["topic_key"], r.get("first_rendered_at"), r.get("last_rendered_at"),
              r.get("last_exported_at"), r.get("export_path")) for r in records],
        )
    return len(records)


def mark_purged(key: str, which: str) -> None:
    """Record that a topic's output/ or export/ folder has been deleted."""
    column = {"output": "output_purged_at", "export": "export_purged_at"}[which]
    with connect() as conn:
        conn.execute(
            f"INSERT INTO topic_lifecycle (topic_key, {column}) VALUES (%s, now())"
            f" ON CONFLICT (topic_key) DO UPDATE SET {column} = now(), updated_at = now()",
            (key,),
        )


def record_retention_run(dry_run: bool, output_purged: int, export_purged: int,
                         bytes_freed: int, detail: list[dict[str, Any]]) -> int:
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO retention_run (dry_run, output_purged, export_purged,"
            " bytes_freed, detail) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (dry_run, output_purged, export_purged, bytes_freed,
             json.dumps(detail, ensure_ascii=False)),
        ).fetchone()
    return row[0]


def retention_runs(limit: int = 10) -> list[tuple]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, ran_at, dry_run, output_purged, export_purged, bytes_freed"
            " FROM retention_run ORDER BY ran_at DESC LIMIT %s", (limit,)
        ).fetchall()


# --------------------------------------------------------------------------- #
# Upload batch + API quota
# --------------------------------------------------------------------------- #
DAILY_UNITS = 10_000        # YouTube Data API v3 default daily quota
UNITS_PER_UPLOAD = 1702     # insert 1600 + thumbnail 50 + playlist 50 + 2 lookups


def pacific_day() -> dt.date:
    """Today's date in US/Pacific — where Google resets the quota."""
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(dt.timezone.utc).astimezone(
            ZoneInfo("America/Los_Angeles")).date()
    except Exception:
        # Without tz data, assume UTC-8; being an hour out is far better than
        # refusing to report quota at all.
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=8)).date()


def quota_status() -> dict[str, Any]:
    day = pacific_day()
    with connect() as conn:
        row = conn.execute(
            "SELECT units, uploads FROM api_quota WHERE day = %s", (day,)
        ).fetchone()
    units, uploads = row or (0, 0)
    left = max(0, DAILY_UNITS - units)
    return {
        "day": str(day),
        "units_used": units,
        "units_left": left,
        "uploads_today": uploads,
        "slots_left": left // UNITS_PER_UPLOAD,
        "slots_total": DAILY_UNITS // UNITS_PER_UPLOAD,
        "per_upload": UNITS_PER_UPLOAD,
        "daily_units": DAILY_UNITS,
    }


def record_upload_units(units: int = UNITS_PER_UPLOAD) -> dict[str, Any]:
    """Bill one upload against today's quota."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO api_quota (day, units, uploads) VALUES (%s, %s, 1)"
            " ON CONFLICT (day) DO UPDATE SET units = api_quota.units + EXCLUDED.units,"
            " uploads = api_quota.uploads + 1, updated_at = now()",
            (pacific_day(), units),
        )
    return quota_status()


def batch_load() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT topic_key, position, added_at, state, stage, pct, url, error, warnings"
            " FROM upload_batch ORDER BY position"
        ).fetchall()
    return [
        {"key": k, "position": pos, "added_at": _iso(at), "state": state,
         "stage": stage, "pct": pct, "url": url, "error": err, "warnings": warns or []}
        for k, pos, at, state, stage, pct, url, err, warns in rows
    ]


def batch_add(key: str) -> None:
    """Append to the batch. Re-adding an existing key is a no-op."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO upload_batch (topic_key, position)"
            " VALUES (%s, COALESCE((SELECT max(position) + 1 FROM upload_batch), 0))"
            " ON CONFLICT (topic_key) DO NOTHING",
            (key,),
        )


def batch_remove(key: str) -> None:
    with connect() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM upload_batch WHERE topic_key = %s", (key,))
            conn.execute(
                "UPDATE upload_batch b SET position = r.rn - 1 FROM ("
                "  SELECT topic_key, row_number() OVER (ORDER BY position) AS rn"
                "  FROM upload_batch) r"
                " WHERE b.topic_key = r.topic_key AND b.position <> r.rn - 1"
            )


def batch_clear(done_only: bool = False) -> int:
    with connect() as conn:
        sql = "DELETE FROM upload_batch"
        if done_only:
            sql += " WHERE state = 'done'"
        cur = conn.execute(sql)
        return cur.rowcount


def batch_update(key: str, **fields: Any) -> None:
    """Patch one batch row (state/stage/pct/url/error/warnings)."""
    allowed = {"state", "stage", "pct", "url", "error", "warnings"}
    sets, values = [], []
    for name, value in fields.items():
        if name not in allowed:
            continue
        sets.append(f"{name} = %s")
        values.append(json.dumps(value) if name == "warnings" else value)
    if not sets:
        return
    values.append(key)
    with connect() as conn:
        conn.execute(
            f"UPDATE upload_batch SET {', '.join(sets)} WHERE topic_key = %s", values
        )


# --------------------------------------------------------------------------- #
# Brand: channel copy + playlist descriptions (moved off data/brand.json)
# --------------------------------------------------------------------------- #
LEGACY_BRAND = DATA_DIR / "brand.json"


def brand_load() -> dict[str, Any]:
    """Same shape data/brand.json had, so callers didn't have to change."""
    with connect() as conn:
        ch = conn.execute(
            "SELECT tagline, description, yt_synced_at, updated_at,"
            " updated_at > COALESCE(yt_synced_at, 'epoch') FROM brand_channel WHERE id = 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT series, name, description, created, yt_playlist_id, yt_synced_at,"
            " updated_at, updated_at > COALESCE(yt_synced_at, 'epoch')"
            " FROM brand_playlist"
        ).fetchall()
    out: dict[str, Any] = {
        "channel": {"tagline": ch[0] if ch else "", "description": ch[1] if ch else "",
                    "yt_synced_at": _iso(ch[2]) if ch else None,
                    "edited_since_sync": bool(ch[4]) if ch else False},
        "playlists": {},
    }
    for series, name, desc, created, pid, synced, _updated, edited in rows:
        out["playlists"][series] = {
            "name": name, "description": desc, "created": created,
            "yt_playlist_id": pid, "yt_synced_at": _iso(synced),
            "edited_since_sync": bool(edited),
        }
    return out


def brand_save_channel(tagline: str | None = None, description: str | None = None,
                       synced: bool = False) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO brand_channel (id, tagline, description)
            VALUES (1, COALESCE(%(t)s, ''), COALESCE(%(d)s, ''))
            ON CONFLICT (id) DO UPDATE SET
                tagline      = COALESCE(%(t)s, brand_channel.tagline),
                description  = COALESCE(%(d)s, brand_channel.description),
                updated_at   = now(),
                yt_synced_at = CASE WHEN %(s)s THEN now() ELSE brand_channel.yt_synced_at END
            """,
            {"t": tagline, "d": description, "s": synced},
        )


def brand_save_playlist(series: str, name: str | None = None,
                        description: str | None = None, created: bool | None = None,
                        yt_playlist_id: str | None = None, synced: bool = False) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO brand_playlist (series, name, description, created, yt_playlist_id)
            VALUES (%(k)s, COALESCE(%(n)s, %(k)s), COALESCE(%(d)s, ''),
                    COALESCE(%(c)s, false), %(p)s)
            ON CONFLICT (series) DO UPDATE SET
                name           = COALESCE(%(n)s, brand_playlist.name),
                description    = COALESCE(%(d)s, brand_playlist.description),
                created        = COALESCE(%(c)s, brand_playlist.created),
                yt_playlist_id = COALESCE(%(p)s, brand_playlist.yt_playlist_id),
                updated_at     = now(),
                yt_synced_at   = CASE WHEN %(s)s THEN now() ELSE brand_playlist.yt_synced_at END
            """,
            {"k": series, "n": name, "d": description, "c": created,
             "p": yt_playlist_id, "s": synced},
        )


def brand_migrate_from_json() -> int:
    """Load data/brand.json into the tables. Safe to re-run: everything upserts."""
    data = _read_json(LEGACY_BRAND) or {}
    n = 0
    ch = data.get("channel") or {}
    if ch:
        brand_save_channel(ch.get("tagline"), ch.get("description"))
        n += 1
    for series, entry in (data.get("playlists") or {}).items():
        brand_save_playlist(series, entry.get("name"), entry.get("description"),
                            entry.get("created"))
        n += 1
    return n


# --------------------------------------------------------------------------- #
# Live YouTube counts (snapshots — history is cheap and shows growth)
# --------------------------------------------------------------------------- #
def save_channel_stats(subscribers: int | None, views: int | None,
                       video_count: int | None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO channel_stats_live (subscribers, views, video_count)"
            " VALUES (%s, %s, %s)",
            (subscribers, views, video_count),
        )


def save_video_stats(rows: list[dict[str, Any]]) -> int:
    """rows: [{video_id, views, likes, comments, privacy_status}]"""
    if not rows:
        return 0
    with connect() as conn:
        conn.cursor().executemany(
            "INSERT INTO video_stats_live (video_id, views, likes, comments, privacy_status)"
            " VALUES (%s, %s, %s, %s, %s)",
            [(r["video_id"], r.get("views"), r.get("likes"), r.get("comments"),
              r.get("privacy_status")) for r in rows],
        )
    return len(rows)


def latest_channel_stats() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT fetched_at, subscribers, views, video_count FROM channel_stats_live"
            " ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    at, subs, views, count = row
    return {"fetched_at": _iso(at), "subscribers": subs, "views": views,
            "video_count": count}


def latest_video_stats() -> dict[str, dict[str, Any]]:
    """video_id -> latest snapshot."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ON (video_id) video_id, fetched_at, views, likes,"
            " comments, privacy_status FROM video_stats_live"
            " ORDER BY video_id, fetched_at DESC"
        ).fetchall()
    return {
        vid: {"fetched_at": _iso(at), "views": views, "likes": likes,
              "comments": comments, "privacy_status": privacy}
        for vid, at, views, likes, comments, privacy in rows
    }


def record_api_units(units: int) -> None:
    """Bill read/update calls against today's quota without counting an upload."""
    if units <= 0:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO api_quota (day, units, uploads) VALUES (%s, %s, 0)"
            " ON CONFLICT (day) DO UPDATE SET units = api_quota.units + EXCLUDED.units,"
            " updated_at = now()",
            (pacific_day(), units),
        )


# --------------------------------------------------------------------------- #
# Migration in / out
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def migrate_from_json() -> dict[str, int]:
    """Load the legacy JSON files. Safe to re-run: everything upserts."""
    counts = {"uploads": 0, "discarded": 0, "order": 0, "jobs": 0}

    log = _read_json(LEGACY_LOG) or {}
    for key, entry in log.items():
        if isinstance(entry, str):          # very old format: bare timestamp
            entry = {"uploaded_at": entry}
        mark_uploaded(key, entry.get("url"), entry.get("uploaded_at"))
        counts["uploads"] += 1

    for key, entry in (_read_json(LEGACY_DISCARDED) or {}).items():
        discard(key, entry.get("reason", ""), entry.get("from"),
                entry.get("moved_to"), entry.get("discarded_at"))
        counts["discarded"] += 1

    order = _read_json(LEGACY_ORDER) or []
    if order:
        save_order(order)
        counts["order"] = len(order)

    for d in (_read_json(LEGACY_JOBS) or []):
        if d.get("id"):
            save_job(d)
            counts["jobs"] += 1

    counts["brand"] = brand_migrate_from_json()
    return counts


def export_to_json(dest: Path | None = None) -> dict[str, str]:
    """Write the tables back out in the legacy shapes — the escape hatch."""
    dest = dest or DATA_DIR / "export"
    dest.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, payload in (
        ("upload_log.json", load_log()),
        ("discarded.json", load_discarded()),
        ("queue_order.json", load_order()),
        ("dashboard_jobs.json", load_jobs(1000)),
        ("brand.json", brand_load()),
    ):
        p = dest / name
        p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
                     encoding="utf-8")
        written[name] = str(p.relative_to(PROJECT_ROOT))
    return written
