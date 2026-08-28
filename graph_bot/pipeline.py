"""Orchestrate a run: pick topic(s) -> fetch -> transform -> render -> queue.

Usage:
    python -m graph_bot.pipeline --list
    python -m graph_bot.pipeline --topic population
    python -m graph_bot.pipeline                       # auto-rotate by date
    python -m graph_bot.pipeline --batch 7             # weekly batch
    python -m graph_bot.pipeline --batch 7 --series ml_concept --auto-approve
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from . import audio, caption, fetch, render, transform
from .config import (
    get_topic,
    load_settings,
    load_topics,
    resolve_path,
    topic_series,
)


def _pick_rotating_topic() -> dict:
    topics = load_topics()
    if not topics:
        raise RuntimeError("No topics configured in config/topics.yaml")
    idx = dt.date.today().toordinal() % len(topics)
    return topics[idx]


def _last_rendered(key: str, output_root: Path) -> str:
    """Most recent date this topic was rendered ('' if never).

    Falls back to the durable lifecycle history, so a working copy deleted by
    retention does not make an old topic look brand new.
    """
    dates = sorted(p.parent.parent.name for p in output_root.glob(f"*/{key}/metadata.json"))
    if dates:
        return dates[-1]
    from . import store
    return store.lifecycle_dates().get(key, "")


def pick_batch(count: int, series: str | None = None) -> list[dict]:
    """Least-recently-rendered topics first, so the catalog rotates evenly."""
    settings = load_settings()
    output_root = resolve_path(settings, "output")

    topics = load_topics()
    if series:
        topics = [t for t in topics if topic_series(t) == series]
        if not topics:
            raise RuntimeError(f"No topics in series '{series}'")

    # '' (never rendered) sorts first, then oldest render date.
    ranked = sorted(topics, key=lambda t: (_last_rendered(t["key"], output_root), t["key"]))
    return ranked[:count]


def run_topic(topic: dict, *, refresh: bool = False, auto_approve: bool = False,
              on_stage=None) -> Path:
    # on_stage: optional callback fired at each pipeline phase ("video",
    # "music", "mixing", "subtitle") — used by the dashboard's agent display.
    stage = on_stage or (lambda name: None)
    settings = load_settings()
    key = topic["key"]
    is_scene = topic.get("mode") == "manim"
    stage("video")

    out_dir = resolve_path(settings, "output") / dt.date.today().isoformat() / key
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "video.mp4"

    if is_scene:
        # Concept videos are authored Manim scenes — no data fetch/transform.
        from . import manim_render

        mode = "manim"
        year_min = year_max = 0
        entities = [topic.get("scene", "")]
        print(f"[1/3] Rendering Manim scene '{topic.get('scene')}' (this takes a minute) ...")
        duration = manim_render.render_scene(topic, settings, video_path)
    else:
        print(f"[1/4] Fetching '{key}' via {topic.get('fetcher')} ...")
        df = fetch.fetch(topic, settings, refresh=refresh)

        print(f"[2/4] Transforming ({len(df)} rows) ...")
        mode, data = transform.prepare(df, topic, settings)
        year_min, year_max = int(data.index.min()), int(data.index.max())
        entities = (list(data.columns) if mode in {"bar_race", "line_multi"}
                    else [topic.get("entity_filter") or "global"])

        print(f"[3/4] Rendering {mode} -> {video_path} ...")
        duration = render.render(mode, data, topic, settings, video_path)

    stage("music")
    music_track = audio.add_music(video_path, settings, duration, topic, on_stage=on_stage)

    stage("subtitle")
    print("[4/4] Writing caption + metadata ...")
    (out_dir / "caption.txt").write_text(
        caption.build_description(topic, year_min, year_max, music_track), encoding="utf-8"
    )
    metadata = {
        "key": key,
        "title": topic.get("title"),
        "yt_title": caption.build_title(topic, year_min, year_max),
        "source": topic.get("source"),
        "mode": mode,
        "fetcher": topic.get("fetcher"),
        "year_min": year_min,
        "year_max": year_max,
        "entities": entities,
        "hashtags": topic.get("hashtags", []),
        "duration_sec": round(duration, 1),
        "music": music_track,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "video": str(video_path),
        # draft -> awaiting your approval; auto-approve is for unattended batches.
        "status": "approved" if auto_approve else "draft",
    }
    if auto_approve:
        metadata["approved_at"] = dt.datetime.now().isoformat(timespec="seconds")
        metadata["approved_by"] = "auto (batch)"
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\n✅ Done: {video_path}")
    return video_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate statistics/concept videos.")
    parser.add_argument("--topic", help="Topic key (see --list). Omit to auto-rotate by date.")
    parser.add_argument("--batch", type=int, metavar="N",
                        help="Render the N least-recently-rendered topics.")
    parser.add_argument("--series", help="Limit --batch to one series "
                                         "(world_in_data | ai_trends | ml_concept).")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Mark output approved immediately (for unattended runs).")
    parser.add_argument("--list", action="store_true", help="List available topics and exit.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and re-fetch data.")
    args = parser.parse_args()

    if args.list:
        for t in load_topics():
            print(f"  {t['key']:<20} {topic_series(t):<14} {t.get('title','')}")
        return

    if args.batch:
        topics = pick_batch(args.batch, args.series)
        print(f"Batch of {len(topics)}: {', '.join(t['key'] for t in topics)}\n")
        failed: list[str] = []
        for i, topic in enumerate(topics, 1):
            print(f"--- [{i}/{len(topics)}] {topic['key']} ---")
            try:
                run_topic(topic, refresh=args.refresh, auto_approve=args.auto_approve)
            except Exception as exc:
                # One bad topic must not abort an unattended weekly run.
                print(f"❌ {topic['key']} failed: {exc}")
                failed.append(topic["key"])
        print(f"\nBatch complete: {len(topics) - len(failed)} ok, {len(failed)} failed")
        if failed:
            print(f"  failed: {', '.join(failed)}")
        return

    topic = get_topic(args.topic) if args.topic else _pick_rotating_topic()
    run_topic(topic, refresh=args.refresh, auto_approve=args.auto_approve)


if __name__ == "__main__":
    main()
