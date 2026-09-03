"""Pull analytics straight from the YouTube Analytics API into the warehouse.

This replaces the manual Studio-zip workflow for everything the public API
serves: daily views (channel + per video), watch time, average view duration /
percentage, subscribers gained, likes. What the API does NOT expose is
thumbnail impressions and CTR — those exist only in Studio's exports, so the
zip import stays as the occasional backfill for the two ctr/impressions
columns (which is why they are nullable).

Costs: the Analytics API has its own quota, separate from the Data API's
10,000 units/day that uploads spend — a full sync here costs the upload
pipeline nothing. Requires the yt-analytics.readonly scope; tokens issued
before that scope was added need one re-auth (python -m graph_bot.publish.auth).

Rows land through the same guarded upserts the zip importer uses: an
analytics_import row records the window, and the daily upsert refuses to let
an earlier-ending window overwrite a later one, so API syncs and zip imports
can be mixed in any order without fighting.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ..config import load_topics
from ..db import connect
from ..publish import auth
from .importer import topic_map

# YouTube analytics lag ~48h behind real time; asking for fresher days returns
# zeros that would then be "settled" by the range guard, so stay behind it.
LAG_DAYS = 2


def service():
    from googleapiclient.discovery import build

    return build("youtubeAnalytics", "v2", credentials=auth.credentials(),
                 cache_discovery=False)


def _rows(resp: dict[str, Any]) -> list[list[Any]]:
    return resp.get("rows") or []


def sync(days: int = 90) -> dict[str, Any]:
    """Fetch the last `days` days and upsert into the warehouse."""
    info = auth.token_info()
    if any("yt-analytics" in s for s in info.get("missing_scopes", [])):
        raise auth.AuthError(
            "The cached YouTube token predates the analytics scope. Re-authorise "
            "once to grant it:  python -m graph_bot.publish.auth"
        )
    me = auth.assert_right_channel()
    ids = f"channel=={me['channel_id']}"
    yta = service()

    from googleapiclient.errors import HttpError
    try:
        return _sync(yta, ids, days)
    except HttpError as exc:
        if "accessNotConfigured" in str(exc) or "has not been used" in str(exc):
            raise auth.AuthError(
                "The YouTube Analytics API is not enabled in the Google Cloud "
                "project. Enable it (one click, no re-auth) at: "
                "https://console.developers.google.com/apis/api/"
                "youtubeanalytics.googleapis.com/overview — then retry."
            ) from exc
        raise auth.AuthError(f"YouTube Analytics API error: {str(exc)[:300]}") from exc


def _sync(yta: Any, ids: str, days: int) -> dict[str, Any]:

    end = dt.date.today() - dt.timedelta(days=LAG_DAYS)
    start = end - dt.timedelta(days=days)
    s, e = start.isoformat(), end.isoformat()
    mapping = topic_map()
    vids = list(mapping)

    # ---- fetch ----
    ch_daily = _rows(yta.reports().query(
        ids=ids, startDate=s, endDate=e, dimensions="day",
        metrics="views").execute())
    # subscribersGained alone overstates: Studio's "Subscribers" column (which
    # the zip importer fills this table from) is NET gained-lost, so fetch both.
    ch_period = _rows(yta.reports().query(
        ids=ids, startDate=s, endDate=e,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,"
                "averageViewDuration,averageViewPercentage").execute())
    vid_period: list[list[Any]] = []
    for i in range(0, len(vids), 50):
        chunk = vids[i:i + 50]
        vid_period += _rows(yta.reports().query(
            ids=ids, startDate=s, endDate=e, dimensions="video",
            filters="video==" + ",".join(chunk), maxResults=200,
            metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,"
                    "averageViewDuration,averageViewPercentage").execute())
    vid_daily: list[tuple[str, str, int]] = []
    for vid in vids:
        for day, views in _rows(yta.reports().query(
                ids=ids, startDate=s, endDate=e, dimensions="day",
                filters=f"video=={vid}", metrics="views").execute()):
            if views:
                vid_daily.append((vid, day, int(views)))

    # ---- load, through the same guarded shapes as the zip importer ----
    titles = {t["key"]: t.get("title") for t in load_topics()}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO analytics_import (source, range_start, range_end)"
                " VALUES (%s, %s, %s) RETURNING id",
                (f"api-sync {dt.datetime.now().isoformat(timespec='seconds')}",
                 start, end),
            )
            import_id = cur.fetchone()[0]

            # Videos must exist for the FK; never blank out zip-sourced detail.
            cur.executemany(
                """
                INSERT INTO video (video_id, topic_key, series, playlist, title)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (video_id) DO UPDATE SET
                    topic_key = COALESCE(video.topic_key, EXCLUDED.topic_key),
                    series    = COALESCE(video.series,    EXCLUDED.series),
                    playlist  = COALESCE(video.playlist,  EXCLUDED.playlist),
                    title     = COALESCE(video.title,     EXCLUDED.title),
                    last_seen = now()
                """,
                [(vid, m.get("topic_key"), m.get("series"), m.get("playlist"),
                  titles.get(m.get("topic_key"))) for vid, m in mapping.items()],
            )

            months = {dt.date.fromisoformat(d).replace(day=1) for _, d, _ in vid_daily}
            for m in sorted(months):
                cur.execute("SELECT ensure_daily_partition(%s)", (m,))
            if vid_daily:
                cur.executemany(
                    """
                    INSERT INTO video_daily_stats (video_id, day, views, import_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (video_id, day) DO UPDATE SET
                        views = EXCLUDED.views, import_id = EXCLUDED.import_id
                    WHERE COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = EXCLUDED.import_id),
                              '-infinity'::date) >=
                          COALESCE(
                              (SELECT range_end FROM analytics_import WHERE id = video_daily_stats.import_id),
                              '-infinity'::date)
                    """,
                    [(vid, day, views, import_id) for vid, day, views in vid_daily],
                )

            if ch_daily:
                cur.executemany(
                    "INSERT INTO channel_daily_stats (day, views, import_id)"
                    " VALUES (%s, %s, %s)"
                    " ON CONFLICT (day) DO UPDATE SET"
                    "   views = EXCLUDED.views, import_id = EXCLUDED.import_id",
                    [(day, int(views), import_id) for day, views in ch_daily],
                )

            if vid_period:
                cur.executemany(
                    """
                    INSERT INTO video_period_stats (
                        video_id, range_start, range_end, views, watch_hours,
                        subscribers, avg_view_sec, avg_pct_viewed, import_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (video_id, range_start, range_end) DO UPDATE SET
                        views          = COALESCE(EXCLUDED.views, video_period_stats.views),
                        watch_hours    = COALESCE(EXCLUDED.watch_hours, video_period_stats.watch_hours),
                        subscribers    = COALESCE(EXCLUDED.subscribers, video_period_stats.subscribers),
                        avg_view_sec   = COALESCE(EXCLUDED.avg_view_sec, video_period_stats.avg_view_sec),
                        avg_pct_viewed = COALESCE(EXCLUDED.avg_pct_viewed, video_period_stats.avg_pct_viewed),
                        import_id      = EXCLUDED.import_id
                    """,
                    [(vid, start, end, int(views), round(float(mins) / 60, 4),
                      int(gained) - int(lost), int(avd), round(float(avp), 3), import_id)
                     for vid, views, mins, gained, lost, avd, avp in vid_period],
                )

            if ch_period:
                views, mins, gained, lost, avd, avp = ch_period[0]
                subs = int(gained) - int(lost)
                cur.execute(
                    """
                    INSERT INTO channel_period_stats (
                        range_start, range_end, views, watch_hours, subscribers,
                        avg_view_sec, avg_pct_viewed, import_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (range_start, range_end) DO UPDATE SET
                        views          = EXCLUDED.views,
                        watch_hours    = EXCLUDED.watch_hours,
                        subscribers    = EXCLUDED.subscribers,
                        avg_view_sec   = EXCLUDED.avg_view_sec,
                        avg_pct_viewed = EXCLUDED.avg_pct_viewed,
                        import_id      = EXCLUDED.import_id
                    """,
                    (start, end, int(views), round(float(mins) / 60, 4),
                     int(subs), int(avd), round(float(avp), 3), import_id),
                )

            cur.execute(
                "UPDATE analytics_import SET rows_daily = %s, rows_period = %s,"
                " rows_channel = %s WHERE id = %s",
                (len(vid_daily), len(vid_period), len(ch_daily), import_id),
            )

    return {
        "range": [s, e],
        "videos": len(vids),
        "daily_rows": len(vid_daily),
        "period_rows": len(vid_period),
        "channel_days": len(ch_daily),
    }
