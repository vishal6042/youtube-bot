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
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .. import fetch as fetch_mod
from .. import transform
from ..config import load_settings
from ..render import ffmpeg_exe, h264_args, render
from . import SCENES, EpisodeError, load, out_dir, validate, words
from .history import RenderRecord
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
    "NV.IND.MANF.CD": {"subtitle": "What factories make (manufacturing value added, US dollars)",
                       "value_scale": 1e12, "unit_suffix": "T", "value_decimals": 2},
    "TX.VAL.MRCH.CD.WT": {"subtitle": "Exports of goods (US dollars)",
                          "value_scale": 1e12, "unit_suffix": "T", "value_decimals": 2},
    "NE.EXP.GNFS.CD": {"subtitle": "Exports of goods and services (US dollars)",
                       "value_scale": 1e12, "unit_suffix": "T", "value_decimals": 2},
    "TX.VAL.TECH.CD": {"subtitle": "High-technology exports (US dollars)",
                       "value_scale": 1e9, "unit_suffix": "B", "value_decimals": 0},
    "IP.PAT.RESD": {"subtitle": "Patent applications by residents", "value_fmt": "integer"},
    "IP.JRN.ARTC.SC": {"subtitle": "Scientific and technical papers", "value_fmt": "integer"},
    "BX.KLT.DINV.CD.WD": {"subtitle": "Foreign investment coming in (FDI, US dollars)",
                          "value_scale": 1e9, "unit_suffix": "B", "value_decimals": 1},
    "IS.SHP.GOOD.TU": {"subtitle": "Container traffic through ports (standard containers)",
                       "value_scale": 1e6, "unit_suffix": "M", "value_decimals": 1},
    "NV.IND.MANF.ZS": {"subtitle": "Manufacturing as a share of the economy",
                       "unit_suffix": "%", "value_decimals": 1},
    "SP.POP.TOTL": {"subtitle": "Population",
                    "value_scale": 1e9, "unit_suffix": "B", "value_decimals": 2},
    "SP.DYN.LE00.IN": {"subtitle": "Life expectancy at birth (years)",
                       "unit_suffix": " yrs", "value_decimals": 1},
    "IS.AIR.PSGR": {"subtitle": "Air passengers carried by the country's airlines",
                    "value_fmt": "compact"},
    "IT.CEL.SETS": {"subtitle": "Mobile phone subscriptions", "value_fmt": "compact"},
    "BX.GSR.CCIS.CD": {"subtitle": "Exports of IT and communication services (US dollars)",
                       "value_scale": 1e9, "unit_suffix": "B", "value_decimals": 0},
    "BX.TRF.PWKR.CD.DT": {"subtitle": "Money sent home by workers abroad (remittances, US dollars)",
                          "value_scale": 1e9, "unit_suffix": "B", "value_decimals": 1},
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
    if chart.get("mode") in SCENES:
        raise EpisodeError(f"Chapter '{ch['id']}' is an animated scene, not a data chart")
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
    parts = {"n": " ".join((ch.get("narration") or "").split()), "c": ch.get("chart"),
             "h": ch.get("heading"), "v": ep.get("voice"), "r": ep.get("voice_rate"), "fmt": 6}
    mode = (ch.get("chart") or {}).get("mode")
    if _neon(ep, ch):
        from .neon import VERSION as NEON_VERSION

        parts["neon"] = NEON_VERSION
    if mode in SCENES:
        # The drawing code changes more often than the script, so its version
        # is part of what the chapter was made from.
        parts["sc"] = _scene_module(mode).VERSION
    blob = json.dumps(parts, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _render_chapter(ep: dict[str, Any], ch: dict[str, Any], work: Path,
                    settings: dict[str, Any],
                    on_sub: Callable[..., None] | None = None) -> dict[str, Any]:
    """Voice, then chart, then combine. ``on_sub(sub, **detail)`` reports each."""
    cid = ch["id"]
    began = time.time()
    tell = on_sub or (lambda *a, **k: None)
    tell("voice")
    voice_mp3 = work / f"{cid}.mp3"
    chart_mp4 = work / f"{cid}.chart.mp4"
    final_mp4 = work / f"{cid}.mp4"

    voice_secs, cues = speak(ch.get("narration", ""), ep.get("voice") or DEFAULT_VOICE, voice_mp3,
                             settings, rate=ep.get("voice_rate") or "+0%")
    total = LEAD_IN + voice_secs + LEAD_OUT
    tell("chart", voice_secs=round(voice_secs, 1), frame=0, frames=0)

    if (ch.get("chart") or {}).get("mode") in SCENES:
        chart_secs = _render_scene(ep, ch, voice_mp3, total, chart_mp4, settings)
        return _combine(ep, ch, voice_mp3, chart_mp4, final_mp4, voice_secs, total, chart_secs,
                        cues, began, settings, tell)

    topic, df = chapter_topic(ep, ch, settings)
    rs = copy.deepcopy(settings)
    last = [0.0]

    def on_frame(i: int, n: int) -> None:
        # Hundreds of frames a minute: writing state for each would be the
        # slowest part of the render.
        if time.time() - last[0] >= 1.0 or i + 1 >= (n or 0):
            last[0] = time.time()
            tell("chart", voice_secs=round(voice_secs, 1), frame=i + 1, frames=n or 0)

    rs["_progress"] = on_frame
    rs.setdefault("video", {}).update(
        width=WIDTH, height=HEIGHT,
        # The renderer adds a 1s end hold; aim the motion at the rest.
        target_seconds=max(4.0, total - 1.0))
    mode, data = transform.prepare(df, topic, rs)
    if _neon(ep, ch):
        from . import neon

        footer = (settings.get("branding", {}).get("footer") or "").split("•")[0].strip() or "Data in Motion"
        prefix = INDICATORS.get((ch.get("chart") or {}).get("code"), {}).get("prefix", "")
        chart_secs = neon.render(mode, data, topic, rs, chart_mp4, heading=ch.get("heading") or "",
                                 prefix=prefix, footer=footer, encode_args=h264_args(settings))
    else:
        chart_secs = render(mode, data, topic, rs, chart_mp4)

    return _combine(ep, ch, voice_mp3, chart_mp4, final_mp4, voice_secs, total, chart_secs,
                    cues, began, settings, tell)


def _neon(ep: dict[str, Any], ch: dict[str, Any]) -> bool:
    """Whether this chapter is drawn in the neon look (episode ``style: neon``)."""
    return ep.get("style") == "neon" and (ch.get("chart") or {}).get("mode") in ("bar_race", "line_multi")


def _scene_module(mode: str):
    import importlib

    return importlib.import_module(f".{mode}", __package__)


def _render_scene(ep: dict[str, Any], ch: dict[str, Any], voice_mp3: Path, total: float,
                  chart_mp4: Path, settings: dict[str, Any]) -> float:
    """An animated scene (scorecard.py, podium.py, hook.py), timed from the
    narration's word timings.

    The chapter's audio keeps sentence cues for the subtitles; word timings
    come from a second, identical request whose audio is thrown away.
    """
    from .scorecard import render_scorecard

    probe = voice_mp3.with_suffix(".words.mp3")
    _, word_cues = speak(ch.get("narration", ""), ep.get("voice") or DEFAULT_VOICE, probe, settings,
                         rate=ep.get("voice_rate") or "+0%", words=True)
    probe.unlink(missing_ok=True)
    footer = (settings.get("branding", {}).get("footer") or "").split("•")[0].strip() or "Data in Motion"
    chart = ch["chart"]
    if chart["mode"] == "scorecard":
        return render_scorecard(chart, ch.get("heading") or "", word_cues, LEAD_IN, total, chart_mp4,
                                ffmpeg_exe(settings), footer=footer, encode_args=h264_args(settings))
    render = getattr(_scene_module(chart["mode"]), f"render_{chart['mode']}")
    return render(chart, word_cues, LEAD_IN, total, chart_mp4, ffmpeg_exe(settings), footer=footer,
                  source=chart.get("source", "World Bank"), encode_args=h264_args(settings))


def _combine(ep: dict[str, Any], ch: dict[str, Any], voice_mp3: Path, chart_mp4: Path, final_mp4: Path,
             voice_secs: float, total: float, chart_secs: float, cues: list[dict[str, Any]],
             began: float, settings: dict[str, Any], tell: Callable[..., None]) -> dict[str, Any]:
    cid = ch["id"]
    # The chart's pace is clamped per year, so it can land short or long. Hold
    # the last frame if short; if long, the voice simply finishes first.
    total = max(total, chart_secs)
    pad = max(0.0, total - chart_secs)
    tell("combine", voice_secs=round(voice_secs, 1))
    _run([
        ffmpeg_exe(settings), "-y", "-loglevel", "error",
        "-i", str(chart_mp4), "-i", str(voice_mp3),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f},fps=30,format=yuv420p[v];"
        f"[1:a]adelay={int(LEAD_IN * 1000)}:all=1,apad,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        *h264_args(settings),
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(final_mp4),
    ])
    chart_mp4.unlink(missing_ok=True)
    return {"hash": _chapter_hash(ep, ch), "secs": round(total, 3), "voice_secs": round(voice_secs, 3),
            "words": words(ch.get("narration")), "video": final_mp4.name,
            "took": round(time.time() - began, 1),
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
        + _source_links(ep) +
        "Narration is a synthetic voice; the script is written and checked by the channel.\n\n"
        "Data in Motion: the world's numbers, animated.\n",
        encoding="utf-8")


def _source_links(ep: dict[str, Any]) -> str:
    """One link per dataset the episode charts, in chapter order, so viewers
    can check every number; plus the map's credit when a scene draws the globe."""
    lines, seen = [], set()
    # Datasets the narration quotes without charting them come from `extra_sources:`.
    codes = [(ch.get("chart") or {}).get("code") for ch in ep.get("chapters") or []]
    for code in codes + list(ep.get("extra_sources") or []):
        if not code or code in seen:
            continue
        seen.add(code)
        label = INDICATORS.get(code, {}).get("subtitle") or code
        # `source_links:` replaces a dataset's page when the standard one is broken.
        url = (ep.get("source_links") or {}).get(code) or f"https://data.worldbank.org/indicator/{code}"
        lines.append(f"{label}: {url}")
    if any((c.get("chart") or {}).get("mode") in ("hook", "podium") for c in ep.get("chapters") or []):
        lines.append("Map: Natural Earth, with India's boundaries as India officially recognises them: "
                     "https://www.naturalearthdata.com")
    return ("\nSources\n" + "\n".join(lines) + "\n\n") if lines else "\n"


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
    record = RenderRecord(key, ep, only, force)
    say = record.say

    def report(**kw: Any) -> None:
        info = {"status": "running", "started_at": started, "total": len(chapters),
                "job_id": record.id, **kw}
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
                base = {"stage": "chapter", "index": i, "chapter": cid, "heading": ch.get("heading"),
                        "chapter_started_at": dt.datetime.now().isoformat(timespec="seconds")}
                report(**base, sub="voice")
                say(f"  [{i + 1}/{len(chapters)}] {cid}: narrating and rendering ...")
                record.chapter(i, "active")
                done_map[cid] = _render_chapter(
                    ep, ch, work, settings,
                    on_sub=lambda sub, _b=base, **kw: report(**_b, sub=sub, **kw))
                record.chapter(i, "rendered", done_map[cid])
            else:
                say(f"  [{i + 1}/{len(chapters)}] {cid}: unchanged, reusing")
                record.chapter(i, "reused", done_map[cid])
            built.append((ch, done_map[cid]))

        report(stage="assembling", index=len(chapters))
        record.stage("assembling")
        say("  joining chapters ...")
        listing = work / "concat.txt"
        listing.write_text("".join(f"file '{d['video']}'\n" for _, d in built), encoding="utf-8")
        joined = out / "joined.mp4"
        _run([ffmpeg_exe(settings), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", str(listing), "-c", "copy", str(joined)])
        total = sum(d["secs"] for _, d in built)

        report(stage="mixing", index=len(chapters))
        record.stage("mixing")
        say("  mixing music under the voice ...")
        from .. import audio as audio_mod

        video = out / "episode.mp4"
        conf = settings.get("audio", {}) or {}
        # The folder tracks are 30-second Shorts beds; looped ten times under
        # five minutes of talking they are very audibly a loop. The synthesised
        # theme is generated to the episode's full length instead.
        track = None
        if conf.get("enabled", False):
            mood = ep.get("music_mood") or audio_mod.infer_mood({"key": f"lf_{key}"})
            track = audio_mod._generated_track(f"lf_{key}", total, mood)
        lufs = conf.get("loudness_lufs") or -14
        peak = conf.get("true_peak_db") or -1.5
        # loudnorm upsamples internally; bring the result back to 48 kHz.
        norm = f"loudnorm=I={lufs}:TP={peak}:LRA=11,aresample=48000"
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
            if ep.get("thumbnail"):
                # The script says what its thumbnail shows (see thumbnail_hero.py).
                from .thumbnail_hero import build_hero

                build_hero(ep, out / "thumbnail.jpg", settings)
            else:
                from .. import thumbnail

                thumbnail.build_wide({"key": key, "title": ep["title"], "series": ep.get("series"),
                                      "source": "World Bank"}, video, out / "thumbnail.jpg", settings)
        except Exception as exc:  # a missing thumbnail must not fail a finished render
            say(f"  thumbnail skipped: {exc}")

        secs = audio_seconds(video, settings)
        state["build"] = {"status": "done", "started_at": started, "total": len(chapters),
                          "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
                          "secs": round(secs, 1), "music": track.name if track else None,
                          "job_id": record.id}
        state["chapters"] = done_map
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if progress:
            progress(state["build"])
        say(f"  done: {video}  ({_stamp(secs)})")
        record.finish("done", secs=round(secs, 1), folder=f"output/longform/{key}")
        return video
    except Exception as exc:
        state["build"] = {"status": "failed", "started_at": started, "total": len(chapters),
                          "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
                          "error": f"{type(exc).__name__}: {exc}", "job_id": record.id}
        state["chapters"] = done_map
        record.finish("failed", error=f"{type(exc).__name__}: {exc}")
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if progress:
            progress(state["build"])
        raise
