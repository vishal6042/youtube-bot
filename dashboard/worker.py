"""Orchestrator job worker: produce topic(s) with parallel sub-agents.

Spawned by the dashboard server as a subprocess so heavy renders never block
the API. Runs the pipeline as a small DAG:

    video (fetch -> transform -> render) ──┐
    music (select/generate track)  ──┐     ├─> mixing -> export -> thumbnail
       └> subtitle (title + description)───┘

The music + subtitle branch runs in a side thread, in parallel with the
render — the mux loops the track, so music only needs an estimated duration.
Mixing waits on both branches; export and thumbnail follow.

stdout markers the server parses:
    ::topic::<key>                    starting work on <key>
    ::agent::<name>::<state>          agent state: active | done | failed
    ::exported::<key>::<path>         export folder for <key>
    ::failed::<key>::<err>            <key> failed; the batch continues

Usage:
    python -u -m dashboard.worker --topics population gdp
    python -u -m dashboard.worker --batch 3 --series world_in_data
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from graph_bot import audio, caption, fetch, render, transform
from graph_bot.config import get_topic, load_settings, resolve_path
from graph_bot.pipeline import pick_batch
from graph_bot.publish.manual import export_one


_out_lock = threading.Lock()


def agent(name: str, state: str) -> None:
    """Emit an agent marker as one atomic write.

    The side branch and the render run on different threads, so a plain
    print() can interleave with another thread's partial line and corrupt
    the marker. One locked write, with a leading newline, keeps each marker
    alone on its own line.
    """
    with _out_lock:
        sys.stdout.write(f"\n::agent::{name}::{state}\n")
        sys.stdout.flush()


def _side_branch(topic: dict[str, Any], settings: dict[str, Any], y0: int, y1: int,
                 est_duration: float, out_dir: Path, results: dict[str, Any]) -> None:
    """Music selection + title/description, in parallel with the render."""
    agent("music", "active")
    try:
        track = audio.select_track(settings, topic, est_duration)
        results["track"] = track
        agent("music", "done")
    except Exception:
        agent("music", "failed")
        raise

    agent("subtitle", "active")
    try:
        music_name = results["track"].name if results.get("track") else None
        results["yt_title"] = caption.build_title(topic, y0, y1)
        (out_dir / "caption.txt").write_text(
            caption.build_description(topic, y0, y1, music_name), encoding="utf-8"
        )
        agent("subtitle", "done")
    except Exception:
        agent("subtitle", "failed")
        raise


def produce(key: str, *, refresh: bool = False) -> None:
    topic = get_topic(key)
    settings = load_settings()
    print(f"::topic::{key}", flush=True)

    date = dt.date.today().isoformat()
    out_dir = resolve_path(settings, "output") / date / key
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "video.mp4"
    is_scene = topic.get("mode") == "manim"

    # An estimate is enough for track selection — the mux loops the track and
    # fades are computed from the real duration at mixing time.
    est = float(settings.get("video", {}).get("target_seconds", 24) or 24)

    agent("video", "active")
    results: dict[str, Any] = {}
    try:
        if is_scene:
            from graph_bot import manim_render

            mode, y0, y1 = "manim", 0, 0
            entities = [topic.get("scene", "")]
            with ThreadPoolExecutor(max_workers=1) as ex:
                side = ex.submit(_side_branch, topic, settings, y0, y1, est, out_dir, results)
                print(f"Rendering Manim scene '{topic.get('scene')}' ...", flush=True)
                duration = manim_render.render_scene(topic, settings, video_path)
                agent("video", "done")
                side.result()
        else:
            print(f"Fetching '{key}' via {topic.get('fetcher')} ...", flush=True)
            df = fetch.fetch(topic, settings, refresh=refresh)
            print(f"Transforming ({len(df)} rows) ...", flush=True)
            mode, data = transform.prepare(df, topic, settings)
            y0, y1 = int(data.index.min()), int(data.index.max())
            entities = (list(data.columns) if mode in {"bar_race", "line_multi"}
                        else [topic.get("entity_filter") or "global"])
            with ThreadPoolExecutor(max_workers=1) as ex:
                side = ex.submit(_side_branch, topic, settings, y0, y1, est, out_dir, results)
                print(f"Rendering {mode} -> {video_path} ...", flush=True)
                duration = render.render(mode, data, topic, settings, video_path)
                agent("video", "done")
                side.result()
    except Exception:
        agent("video", "failed")
        raise

    agent("mixing", "active")
    try:
        track = results.get("track")
        music_track = audio.mux_track(video_path, settings, duration, track) if track else None
        agent("mixing", "done")
    except Exception:
        agent("mixing", "failed")
        raise

    now = dt.datetime.now().isoformat(timespec="seconds")
    metadata = {
        "key": key,
        "title": topic.get("title"),
        "yt_title": results.get("yt_title") or caption.build_title(topic, y0, y1),
        "source": topic.get("source"),
        "mode": mode,
        "fetcher": topic.get("fetcher"),
        "year_min": y0,
        "year_max": y1,
        "entities": entities,
        "hashtags": topic.get("hashtags", []),
        "duration_sec": round(duration, 1),
        "music": music_track,
        "generated_at": now,
        "video": str(video_path),
        "status": "approved",
        "approved_at": now,
        "approved_by": "auto (dashboard)",
    }
    meta_path = out_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    agent("exporting", "active")
    try:
        export_root = resolve_path(settings, "export") / date
        export_root.mkdir(parents=True, exist_ok=True)
        dest = export_one(meta_path, metadata, export_root)
        if dest is None:
            raise RuntimeError("export failed: video missing")
        agent("exporting", "done")
    except Exception:
        agent("exporting", "failed")
        raise

    agent("thumbnail", "active")
    try:  # a bad thumbnail must not fail the whole topic
        from graph_bot import thumbnail

        thumbnail.build(topic, dest / "video.mp4", dest / "thumbnail.jpg", settings)
        # The 16:9 one is what YouTube actually shows; the portrait cover is
        # for surfaces that want the Shorts shape.
        thumbnail.build_wide(topic, dest / "video.mp4", dest / "thumbnail_yt.jpg", settings)
        agent("thumbnail", "done")
        print("  🖼 thumbnail.jpg", flush=True)
    except Exception as exc:
        agent("thumbnail", "failed")
        print(f"  ! thumbnail failed: {exc}", flush=True)

    print(f"::exported::{key}::{dest}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render + export topics for the dashboard.")
    parser.add_argument("--topics", nargs="*", default=[], help="Topic keys to produce")
    parser.add_argument("--batch", type=int, help="Render the N least-recently-rendered topics")
    parser.add_argument("--series", help="Limit --batch to one series")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and re-fetch data")
    args = parser.parse_args()

    keys = list(args.topics)
    if args.batch:
        keys += [t["key"] for t in pick_batch(args.batch, args.series)]
    if not keys:
        raise SystemExit("Nothing to do: pass --topics or --batch")

    failed: list[str] = []
    for key in keys:
        try:
            produce(key, refresh=args.refresh)
        except Exception as exc:  # one bad topic must not abort the batch
            print(f"::failed::{key}::{exc}", flush=True)
            failed.append(key)

    print(f"::done::{len(keys) - len(failed)} ok, {len(failed)} failed", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
