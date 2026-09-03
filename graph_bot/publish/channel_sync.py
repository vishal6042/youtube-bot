"""Two-way sync between the local brand copy and the live YouTube channel.

Pull: channel description + subscriber/view counts, the channel's playlists,
and per-video statistics (views, likes, comments, privacy status) for every
video in the upload log. Reads are nearly free — channels.list and
playlists.list are 1 unit each, videos.list is 1 unit per 50 ids — so a full
pull costs ~4 units against the 10,000/day quota.

Push: apply locally edited channel description / playlist name+description to
YouTube (channels.update / playlists.update, 50 units each). Push is always
explicit and per-item: the dashboard sends exactly what the user confirmed.

The privacy statuses that come back with the stats double as the visibility
checker: the posting workflow requires a manual Public flip in Studio that
nothing else verifies, so "uploaded but still private" is surfaced here.
"""
from __future__ import annotations

from typing import Any

from .. import store
from ..analytics.importer import VIDEO_ID_RE
from . import auth

# YouTube Data API v3 costs (units).
COST_LIST = 1
COST_UPDATE = 50


def _video_ids() -> dict[str, str]:
    """topic_key -> video_id, parsed from the upload log's URLs."""
    out: dict[str, str] = {}
    for key, entry in store.load_log().items():
        m = VIDEO_ID_RE.search(entry.get("url") or "")
        if m:
            out[key] = m.group(1)
    return out


def pull() -> dict[str, Any]:
    """Fetch live channel/playlist/video state, snapshot the counts, and
    return everything the dashboard needs to draw a local-vs-live diff."""
    me = auth.assert_right_channel()
    yt = auth.service()
    units = 0

    # ---- channel: description + statistics ----
    resp = yt.channels().list(
        part="snippet,statistics,brandingSettings", mine=True).execute()
    units += COST_LIST
    ch = (resp.get("items") or [{}])[0]
    stats = ch.get("statistics", {})
    channel = {
        "id": ch.get("id"),
        "title": ch.get("snippet", {}).get("title"),
        "description": ch.get("brandingSettings", {}).get("channel", {})
                         .get("description", ch.get("snippet", {}).get("description", "")),
        "subscribers": int(stats.get("subscriberCount") or 0),
        "views": int(stats.get("viewCount") or 0),
        "video_count": int(stats.get("videoCount") or 0),
    }

    # ---- playlists ----
    playlists: list[dict[str, Any]] = []
    req = yt.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50)
    while req is not None:
        resp = req.execute()
        units += COST_LIST
        for item in resp.get("items", []):
            playlists.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "item_count": item.get("contentDetails", {}).get("itemCount"),
            })
        req = yt.playlists().list_next(req, resp)

    # ---- per-video stats + privacy, in batches of 50 ----
    ids = _video_ids()
    by_id = {vid: key for key, vid in ids.items()}
    videos: list[dict[str, Any]] = []
    id_list = list(by_id)
    for i in range(0, len(id_list), 50):
        resp = yt.videos().list(part="statistics,status,snippet",
                                id=",".join(id_list[i:i + 50]),
                                maxResults=50).execute()
        units += COST_LIST
        for item in resp.get("items", []):
            vs = item.get("statistics", {})
            videos.append({
                "video_id": item["id"],
                "topic_key": by_id.get(item["id"]),
                "title": item.get("snippet", {}).get("title"),
                "views": int(vs.get("viewCount") or 0),
                "likes": int(vs.get("likeCount") or 0),
                "comments": int(vs.get("commentCount") or 0),
                "privacy_status": item.get("status", {}).get("privacyStatus"),
            })

    # ---- persist snapshots + remember playlist ids ----
    store.save_channel_stats(channel["subscribers"], channel["views"],
                             channel["video_count"])
    store.save_video_stats(videos)
    local = store.brand_load()
    by_title = {p["title"]: p for p in playlists}
    for series, entry in local.get("playlists", {}).items():
        remote = by_title.get(entry.get("name"))
        if remote and entry.get("yt_playlist_id") != remote["id"]:
            store.brand_save_playlist(series, yt_playlist_id=remote["id"])

    # ---- adopt: on sync, YouTube's copy replaces the local one — UNLESS the
    # local copy was edited since the last sync (that edit is what push sends,
    # so a sync must not silently wipe it). Equal copies just refresh the
    # synced stamp so the edit detection stays accurate.
    adopted: list[str] = []
    ch_local = local.get("channel", {})
    if (ch_local.get("description") or "") == (channel["description"] or ""):
        store.brand_save_channel(synced=True)
    elif not ch_local.get("edited_since_sync"):
        store.brand_save_channel(description=channel["description"] or "", synced=True)
        adopted.append("channel description")
    for series, entry in local.get("playlists", {}).items():
        rp = by_title.get(entry.get("name")) or next(
            (p for p in playlists if p["id"] == entry.get("yt_playlist_id")), None)
        if rp is None:
            continue
        same = (entry.get("description") or "") == (rp["description"] or "") \
            and entry.get("name") == rp["title"]
        if same:
            # Found on YouTube = it exists, whatever the copy says — this drives
            # the "playlist not created on YouTube" warnings and upload auto-add.
            store.brand_save_playlist(series, created=True, synced=True)
        elif not entry.get("edited_since_sync"):
            store.brand_save_playlist(series, name=rp["title"],
                                      description=rp["description"] or "",
                                      created=True, synced=True)
            adopted.append(f"playlist {rp['title']}")
    store.record_api_units(units)

    private = [v for v in videos if v["privacy_status"] == "private"]
    return {
        "channel": channel,
        "playlists": playlists,
        "videos": sorted(videos, key=lambda v: -v["views"]),
        "private": private,
        "adopted": adopted,
        "units_spent": units,
        "me": {"title": me["title"], "channel_id": me["channel_id"]},
    }


def diff(remote: dict[str, Any]) -> dict[str, Any]:
    """Compare the local brand copy against what pull() found on YouTube."""
    local = store.brand_load()
    ch_local = (local.get("channel") or {}).get("description", "") or ""
    ch_remote = remote["channel"].get("description", "") or ""
    by_title = {p["title"]: p for p in remote["playlists"]}

    items = []
    for series, entry in local.get("playlists", {}).items():
        rp = by_title.get(entry.get("name"))
        if rp is None and entry.get("yt_playlist_id"):
            rp = next((p for p in remote["playlists"]
                       if p["id"] == entry["yt_playlist_id"]), None)
        items.append({
            "series": series,
            "name": entry.get("name"),
            "found": rp is not None,
            "yt_playlist_id": (rp or {}).get("id") or entry.get("yt_playlist_id"),
            "item_count": (rp or {}).get("item_count"),
            "local_description": entry.get("description", "") or "",
            "remote_description": (rp or {}).get("description", "") or "",
            "remote_title": (rp or {}).get("title"),
            "differs": rp is not None and (
                (entry.get("description", "") or "") != (rp.get("description", "") or "")
                or entry.get("name") != rp.get("title")),
        })
    return {
        "channel": {
            "local_description": ch_local,
            "remote_description": ch_remote,
            "differs": ch_local.strip() != ch_remote.strip(),
        },
        "playlists": items,
    }


def push(channel: bool = False, playlists: list[str] | None = None) -> dict[str, Any]:
    """Apply local edits to YouTube. Only touches what was asked for."""
    auth.assert_right_channel()
    yt = auth.service()
    local = store.brand_load()
    units = 0
    applied: list[str] = []
    errors: list[str] = []

    if channel:
        try:
            # Read-modify-write: brandingSettings is replaced whole, so start
            # from what the channel has and change only the description.
            resp = yt.channels().list(part="brandingSettings", mine=True).execute()
            units += COST_LIST
            item = (resp.get("items") or [{}])[0]
            branding = item.get("brandingSettings", {})
            branding.setdefault("channel", {})["description"] = \
                (local["channel"].get("description") or "")
            yt.channels().update(
                part="brandingSettings",
                body={"id": item["id"], "brandingSettings": branding},
            ).execute()
            units += COST_UPDATE
            store.brand_save_channel(synced=True)
            applied.append("channel description")
        except Exception as exc:
            errors.append(f"channel: {str(exc).splitlines()[0]}")

    for series in playlists or []:
        entry = local.get("playlists", {}).get(series)
        if not entry:
            errors.append(f"{series}: not in local settings")
            continue
        pid = entry.get("yt_playlist_id")
        if not pid:
            errors.append(f"{series}: no YouTube playlist id — run a sync first")
            continue
        try:
            yt.playlists().update(
                part="snippet",
                body={"id": pid, "snippet": {
                    # title is mandatory on playlists.update, so the local name
                    # is always sent — this is also what renames a playlist.
                    "title": entry.get("name") or series,
                    "description": entry.get("description") or "",
                }},
            ).execute()
            units += COST_UPDATE
            store.brand_save_playlist(series, synced=True)
            applied.append(f"playlist {entry.get('name')}")
        except Exception as exc:
            errors.append(f"{series}: {str(exc).splitlines()[0]}")

    store.record_api_units(units)
    return {"applied": applied, "errors": errors, "units_spent": units}
