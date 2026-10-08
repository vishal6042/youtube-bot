"""Render a long-form episode: one narrated chart per chapter, stitched together.

For each chapter: speak the narration, render the chart at 1920x1080 paced to
the narration's length, and mux the two. Then concatenate the chapters, lay a
quiet music bed under the voice, normalise loudness, and write the subtitle
file, description (with chapter timestamps), title and thumbnail.

Chapters are cached by a hash of what produced them, so editing one chapter's
script re-renders that chapter only.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .. import fetch as fetch_mod
from .. import transform
from ..config import load_settings
from ..render import ffmpeg_exe, render
from . import EpisodeError, load, out_dir, validate, words
from .narrate import DEFAULT_VOICE, audio_seconds, speak

WIDTH, HEIGHT = 1920, 1080
LEAD_IN = 0.35    # silence before the voice starts in each chapter
LEAD_OUT = 0.9    # the chart holds its final frame this long after the voice

# World Bank's formal names read badly on a chart and miss the flag lookup.
RENAME = {
    "Russian Federation": "Russia", "Korea, Rep.": "South Korea", "Viet Nam": "Vietnam",
    "Turkiye": "Turkey", "Egypt, Arab Rep.": "Egypt", "Iran, Islamic Rep.": "Iran",
    "Hong Kong SAR, China": "Hong Kong", "Venezuela, RB": "Venezuela",
}

# How each indicator is labelled and formatted. Anything not listed falls back
# to plain numbers and the chapter's own `subtitle` / `unit_suffix`.
INDICATORS: dict[str, dict[str, Any]] = {
    "NY.GDP.MKTP.CD": {"subtitle": "Size of the economy (GDP, US dollars)",
                       "value_scale": 1e12, "unit_suffix": "T", "value_decimals": 2, "prefix": "$"},
    "NY.GDP.MKTP.PP.CD": {"subtitle": "Size of the economy by buying power (GDP, PPP)",
                          "value_scale": 1e12, "unit_suffix": "T", "value_decimals": 1, "prefix": "$"},
    "NY.GDP.PCAP.CD": {"subtitle": "Income per person (GDP per capita, US dollars)",
                       "value_fmt": "integer", "prefix": "$"},
}

Progress = Callable[[dict[str, Any]], None]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-600:]}")


def _indicator(code: str, settings: dict[str, Any]) -> pd.DataFrame:
    """One World Bank indicator, cached once per code (not per chapter)."""
    key = "lf_" + code.lower().replace(".", "_")
    df = fetch_mod.fetch({"key": key, "fetcher": "worldbank", "code": code}, settings)
    return df.assign(entity=df["entity"].replace(RENAME))


def _covered(df: pd.DataFrame, lo: int, hi: int) -> list[str]:
    """Entities with a real figure at BOTH ends of the window.

    The renderers back- and forward-fill gaps, so a country that only appears
    part-way through (Russia before 1988) would otherwise get an invented flat
    bar for the years it has no data.
    """
    first = df.groupby("entity")["year"].min()
    last = df.groupby("entity")["year"].max()
    return [e for e in first.index if first[e] <= lo and last[e] >= hi]


def chapter_topic(ep: dict[str, Any], ch: dict[str, Any], settings: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame]:
    """The render-ready topic dict and data frame for one chapter."""
    chart = dict(ch.get("chart") or {})
    code = chart["code"]
    mode = chart["mode"]
    df = _indicator(code, settings)

    lo = int(chart.get("year_min") or df["year"].min())
    hi = int(chart.get("year_max") or df["year"].max())
    df = df[(df["year"] >= lo) & (df["year"] <= hi)]
    if df.empty:
        raise EpisodeError(f"Chapter '{ch['id']}': no data between {lo} and {hi}")

    rn = lambda name: RENAME.get(name, name)  # noqa: E731
    info = INDICATORS.get(code, {})
    topic: dict[str, Any] = {
        "key": f"lf_{ep['key']}_{ch['id']}",
        "title": ch.get("heading") or ep.get("title", ""),
        "subtitle": chart.get("subtitle") or info.get("subtitle", ""),
        "mode": mode,
        "source": chart.get("source", "World Bank"),
        "years_window": 500,     # the chapter's own year range is the window
        "top_n": int(chart.get("top_n") or 10),
        **{k: v for k, v in info.items() if k not in ("subtitle", "prefix")},
        **{k: chart[k] for k in ("value_scale", "unit_suffix", "value_decimals", "value_fmt", "flags")
           if k in chart},
    }
    if chart.get("highlight"):
        topic["highlight"] = rn(chart["highlight"])

    if mode == "line_grow":
        topic["entity_filter"] = rn(chart["entity"])
    elif mode == "line_multi":
        topic["entities"] = [rn(e) for e in chart["entities"]]
    else:
        keep = _covered(df, lo, hi)
        if chart.get("entities"):
            wanted = [rn(e) for e in chart["entities"]]
            missing = [e for e in wanted if e not in keep]
            if missing:
                raise EpisodeError(
                    f"Chapter '{ch['id']}': no complete data for {', '.join(missing)} "
                    f"between {lo} and {hi}")
            keep = wanted
            topic["top_n"] = len(keep)
        if mode == "bump_race":
            # Rank against every country with a figure that year, not just the
            # lines on screen: India was 18th in 1991, not 12th of the 12 shown.
            wide_all = df.pivot_table(index="year", columns="entity", values="value")
            ranks = wide_all.rank(axis=1, ascending=False, method="min")
            shown = df[df["entity"].isin(keep)]
            final = shown[shown["year"] == hi].nlargest(topic["top_n"], "value")["entity"].tolist()
            topic["_ranks"] = ranks[final].interpolate(limit_direction="both")
            topic["rank_max"] = int(min(20, max(topic["top_n"], ranks[final].max().max())))
        df = df[df["entity"].isin(keep)]

    return topic, df


def _chapter_hash(ep: dict[str, Any], ch: dict[str, Any]) -> str:
    blob = json.dumps({"n": " ".join((ch.get("narration") or "").split()), "c": ch.get("chart"),
                       "h": ch.get("heading"), "v": ep.get("voice"), "r": ep.get("voice_rate"), "fmt": 4}, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _render_chapter(ep: dict[str, Any], ch: dict[str, Any], work: Path,
                    settings: dict[str, Any]) -> dict[str, Any]:
    cid = ch["id"]
    voice_mp3 = work / f"{cid}.mp3"
    chart_mp4 = work / f"{cid}.chart.mp4"
    final_mp4 = work / f"{cid}.mp4"

    voice_secs, cues = speak(ch.get("narration", ""), ep.get("voice") or DEFAULT_VOICE, voice_mp3,
                             settings, rate=ep.get("voice_rate") or "+0%")
    total = LEAD_IN + voice_secs + LEAD_OUT

    topic, df = chapter_topic(ep, ch, settings)
    rs = copy.deepcopy(settings)
    rs.setdefault("video", {}).update(
        width=WIDTH, height=HEIGHT,
        # The renderer adds a 1s end hold; aim the motion at the rest.
        target_seconds=max(4.0, total - 1.0))
    mode, data = transform.prepare(df, topic, rs)
    chart_secs = render(mode, data, topic, rs, chart_mp4)

    # The chart's pace is clamped per year, so it can land short or long. Hold
    # the last frame if short; if long, the voice simply finishes first.
    total = max(total, chart_secs)
    pad = max(0.0, total - chart_secs)
    _run([
        ffmpeg_exe(settings), "-y", "-loglevel", "error",
        "-i", str(chart_mp4), "-i", str(voice_mp3),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f},fps=30,format=yuv420p[v];"
        f"[1:a]adelay={int(LEAD_IN * 1000)}:all=1,apad,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(final_mp4),
    ])
    chart_mp4.unlink(missing_ok=True)
    return {"hash": _chapter_hash(ep, ch), "secs": round(total, 3), "voice_secs": round(voice_secs, 3),
            "words": words(ch.get("narration")), "video": final_mp4.name,
            "cues": [{**c, "start": c["start"] + LEAD_IN, "end": c["end"] + LEAD_IN} for c in cues]}


def _stamp(secs: float, srt: bool = False) -> str:
    if srt:
        ms = int(round(secs * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def _write_text_assets(ep: dict[str, Any], built: list[tuple[dict[str, Any], dict[str, Any]]],
                       out: Path) -> None:
    srt: list[str] = []
    stamps: list[str] = []
    t = 0.0
    n = 0
    for ch, done in built:
        stamps.append(f"{_stamp(t)} {ch.get('heading') or ch['id']}")
        for cue in done.get("cues", []):
            n += 1
            srt.append(f"{n}\n{_stamp(t + cue['start'], True)} --> {_stamp(t + cue['end'], True)}\n{cue['text']}\n")
        t += done["secs"]
    (out / "episode.srt").write_text("\n".join(srt), encoding="utf-8")
    (out / "title.txt").write_text(ep.get("yt_title") or ep["title"], encoding="utf-8")
    sources = sorted({(c.get("chart") or {}).get("source", "World Bank") for c, _ in built})
    (out / "description.txt").write_text(
        f"{ep['title']}\n\n"
        "Chapters\n" + "\n".join(stamps) + "\n\n"
        f"Data: {', '.join(sources)}. Latest-year figures are first estimates and get revised.\n"
        "Narration is a synthetic voice; the script is written and checked by the channel.\n\n"
        "Data in Motion: the world's numbers, animated.\n",
        encoding="utf-8")


def build(key: str, *, only: list[str] | None = None, force: bool = False,
          progress: Progress | None = None) -> Path:
    """Build (or update) an episode. Returns the path of the finished video."""
    ep = load(key)
    validate(ep)
    chapters = ep["chapters"]
    if not chapters:
        raise EpisodeError("The episode has no chapters")
    empty = [c["id"] for c in chapters if not (c.get("narration") or "").strip()]
    if empty:
        raise EpisodeError(f"These chapters have no narration: {', '.join(empty)}")

    settings = load_settings()
    out = out_dir(key)
    work = out / "chapters"
    work.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    done_map: dict[str, Any] = state.get("chapters", {})
    started = dt.datetime.now().isoformat(timespec="seconds")

    def report(**kw: Any) -> None:
        info = {"status": "running", "started_at": started, "total": len(chapters), **kw}
        state["build"] = info
        state["chapters"] = done_map
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if progress:
            progress(info)

    try:
        built: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for i, ch in enumerate(chapters):
            cid = ch["id"]
            cached = done_map.get(cid)
            fresh = (cached and cached.get("hash") == _chapter_hash(ep, ch)
                     and (work / cached.get("video", "")).exists())
            wanted = (only is None or cid in only) and (force or not fresh)
            if wanted or not fresh:
                report(stage="chapter", index=i, chapter=cid, heading=ch.get("heading"))
                print(f"  [{i + 1}/{len(chapters)}] {cid}: narrating and rendering ...", flush=True)
                done_map[cid] = _render_chapter(ep, ch, work, settings)
            else:
                print(f"  [{i + 1}/{len(chapters)}] {cid}: unchanged, reusing", flush=True)
            built.append((ch, done_map[cid]))

        report(stage="assembling", index=len(chapters))
        print("  joining chapters ...", flush=True)
        listing = work / "concat.txt"
        listing.write_text("".join(f"file '{d['video']}'\n" for _, d in built), encoding="utf-8")
        joined = out / "joined.mp4"
        _run([ffmpeg_exe(settings), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", str(listing), "-c", "copy", str(joined)])
        total = sum(d["secs"] for _, d in built)

        report(stage="mixing", index=len(chapters))
        print("  mixing music under the voice ...", flush=True)
        from .. import audio as audio_mod

        video = out / "episode.mp4"
        conf = settings.get("audio", {}) or {}
        track = audio_mod.select_track(
            settings, {"key": f"lf_{key}", "mood": ep.get("music_mood")}, total)
        lufs = conf.get("loudness_lufs") or -14
        peak = conf.get("true_peak_db") or -1.5
        norm = f"loudnorm=I={lufs}:TP={peak}:LRA=11"
        if track is not None:
            vol = float(conf.get("volume_under_voice", 0.15))
            _run([
                ffmpeg_exe(settings), "-y", "-loglevel", "error",
                "-i", str(joined), "-stream_loop", "-1", "-i", str(track),
                "-filter_complex",
                f"[1:a]volume={vol},afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, total - 3):.2f}:d=3[m];"
                f"[0:a][m]amix=inputs=2:duration=first:normalize=0,{norm}[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", f"{total:.3f}", str(video),
            ])
        else:
            _run([ffmpeg_exe(settings), "-y", "-loglevel", "error", "-i", str(joined),
                  "-af", norm, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(video)])
        joined.unlink(missing_ok=True)

        _write_text_assets(ep, built, out)
        try:
            from .. import thumbnail

            thumbnail.build_wide({"key": key, "title": ep["title"], "series": ep.get("series"),
                                  "source": "World Bank"}, video, out / "thumbnail.jpg", settings)
        except Exception as exc:  # a missing thumbnail must not fail a finished render
            print(f"  thumbnail skipped: {exc}", flush=True)

        secs = audio_seconds(video, settings)
        state["build"] = {"status": "done", "started_at": started, "total": len(chapters),
                          "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
                          "secs": round(secs, 1), "music": track.name if track else None}
        state["chapters"] = done_map
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if progress:
            progress(state["build"])
        print(f"  done: {video}  ({_stamp(secs)})", flush=True)
        return video
    except Exception as exc:
        state["build"] = {"status": "failed", "started_at": started, "total": len(chapters),
                          "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
                          "error": f"{type(exc).__name__}: {exc}"}
        state["chapters"] = done_map
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if progress:
            progress(state["build"])
        raise
