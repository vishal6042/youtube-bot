"""Vertical Shorts cut from a long-form episode: one narrated Short per chapter.

Each Short re-renders its chapter's chart at 1080x1920 with the chart lifted to
leave a caption band, speaks the narration with word timings, and burns the
words in a few at a time (most Shorts are watched muted). Music is the slice
of the episode's theme that sits under the same chapter in the long video.

A chapter can carry a ``short:`` block in the episode file:

    short:
      skip: true          # no Short for this chapter (cold opens, outros)
      title: ...          # YouTube title; defaults to the chapter heading
      heading: ...        # on-screen title; defaults to the chapter heading
      narration: ...      # standalone script; defaults to the chapter's own

A chapter's narration often leans on the one before it ("Then comes 1991"), so
the Short's own narration is where it gets a hook that works on its own.

Output goes to ``output/longform/<key>/shorts/``: ``<n>_<chapter>.mp4`` plus a
``.txt`` with the title and description, numbered in posting order.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import matplotlib

from ..config import load_settings
from ..render import ACCENT, ffmpeg_exe, render
from .. import transform
from . import EpisodeError, load, out_dir, validate
from .build import LEAD_IN, LEAD_OUT, chapter_topic
from .narrate import DEFAULT_VOICE, speak

WIDTH, HEIGHT = 1080, 1920
# Fraction of the height kept clear under the chart. YouTube's own title and
# channel name cover roughly the bottom fifth, so captions sit just above that.
CAPTION_BAND = 0.36
CAPTION_MARGIN_V = 430      # px from the bottom edge to the caption baseline
CAPTION_SIZE = 68
MAX_WORDS, MAX_CHARS = 4, 24
FMT = 1                     # bump to re-render every Short after a style change

_PUNCT_BREAK = re.compile(r"[.,;:?!]$")


def _conf(ch: dict[str, Any]) -> dict[str, Any]:
    return dict(ch.get("short") or {})


def _narration(ch: dict[str, Any]) -> str:
    return " ".join((_conf(ch).get("narration") or ch.get("narration") or "").split())


def _hash(ep: dict[str, Any], ch: dict[str, Any]) -> str:
    c = _conf(ch)
    blob = json.dumps({"n": _narration(ch), "c": ch.get("chart"),
                       "h": c.get("heading") or ch.get("heading"), "v": ep.get("voice"),
                       "r": ep.get("voice_rate"), "fmt": FMT}, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return re.sub(r"\W", "", s.lower())


def _with_punctuation(text: str, cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Word cues carrying the script's own spelling, punctuation included.

    Edge reports bare words ("year", not "year."); the punctuation is what
    tells the captions where a phrase ends.
    """
    tokens = text.split()
    i = 0
    out = []
    for cue in cues:
        n = max(1, len(cue["text"].split()))
        shown = cue["text"]
        # Look a few tokens ahead so one odd word does not derail the rest.
        for skip in range(4):
            window = tokens[i + skip:i + skip + n]
            if window and _norm(" ".join(window)) == _norm(cue["text"]):
                shown = " ".join(window)
                i += skip + n
                break
        out.append({**cue, "shown": shown})
    return out


def caption_chunks(text: str, cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group word cues into short on-screen phrases with start/end times."""
    words = _with_punctuation(text, cues)
    # Phrases end at punctuation or an audible pause...
    phrases: list[list[dict[str, Any]]] = []
    for w in words:
        prev = phrases[-1][-1] if phrases else None
        if prev and not (_PUNCT_BREAK.search(prev["shown"]) or w["start"] - prev["end"] > 0.35):
            phrases[-1].append(w)
        else:
            phrases.append([w])
    # ...and a long phrase is cut into even pieces, so no word is left alone.
    chunks: list[list[dict[str, Any]]] = []
    for ph in phrases:
        lens = [len(w["shown"]) + 1 for w in ph]
        total = sum(lens)
        n = max(-(-len(ph) // MAX_WORDS), -(-total // MAX_CHARS), 1)
        pieces: list[list[dict[str, Any]]] = [[] for _ in range(n)]
        pos = 0.0
        for w, ln in zip(ph, lens):
            pieces[min(n - 1, int((pos + ln / 2) / total * n))].append(w)
            pos += ln
        chunks.extend(p for p in pieces if p)
    out = []
    for i, ch in enumerate(chunks):
        start = ch[0]["start"]
        end = ch[-1]["end"] + 0.5
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0]["start"])
        text_ = " ".join(w["shown"] for w in ch).rstrip(".,;:")
        out.append({"start": start, "end": max(end, start + 0.2), "text": text_})
    return out


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_colour(hex_rgb: str) -> str:
    r, g, b = hex_rgb.lstrip("#")[0:2], hex_rgb.lstrip("#")[2:4], hex_rgb.lstrip("#")[4:6]
    return f"&H00{b}{g}{r}".upper()


def write_ass(chunks: list[dict[str, Any]], path: Path, offset: float) -> None:
    accent = _ass_colour(ACCENT)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,DejaVu Sans,{CAPTION_SIZE},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,"
        f"-1,0,0,0,100,100,0,0,1,5,2,2,70,70,{CAPTION_MARGIN_V},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for c in chunks:
        words = []
        for w in c["text"].replace("\\", "").replace("{", "").replace("}", "").split():
            # Figures are the point of the channel; make them stand out.
            words.append(f"{{\\c{accent}&}}{w}{{\\c&H00FFFFFF&}}" if re.search(r"\d", w) else w)
        lines.append(f"Dialogue: 0,{_ass_time(c['start'] + offset)},{_ass_time(c['end'] + offset)},"
                     f"Cap,,0,0,0,,{' '.join(words)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fonts_dir(work: Path) -> Path:
    """The chart font, copied next to the captions so libass can find it."""
    fonts = work / "fonts"
    target = fonts / "DejaVuSans-Bold.ttf"
    if not target.exists():
        fonts.mkdir(parents=True, exist_ok=True)
        src = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"
        shutil.copyfile(src, target)
    return fonts


def _music_offset(key: str, ep: dict[str, Any], cid: str) -> float:
    """Where this chapter starts in the long video, so its Short gets the same music."""
    from . import read_state

    done = read_state(key).get("chapters", {})
    t = 0.0
    for ch in ep["chapters"]:
        if ch["id"] == cid:
            return t
        t += float((done.get(ch["id"]) or {}).get("secs") or 0)
    return 0.0


def _render_short(ep: dict[str, Any], ch: dict[str, Any], stem: str, work: Path,
                  settings: dict[str, Any]) -> dict[str, Any]:
    cid = ch["id"]
    began = time.time()
    text = _narration(ch)
    voice_mp3 = work / f"{stem}.mp3"
    chart_mp4 = work / f"{stem}.chart.mp4"
    ass = work / f"{stem}.ass"
    final_mp4 = work / f"{stem}.mp4"

    voice_secs, cues = speak(text, ep.get("voice") or DEFAULT_VOICE, voice_mp3, settings,
                             rate=ep.get("voice_rate") or "+0%", words=True)
    total = LEAD_IN + voice_secs + LEAD_OUT

    topic, df = chapter_topic(ep, ch, settings)
    if _conf(ch).get("heading"):
        topic["title"] = _conf(ch)["heading"]
    rs = copy.deepcopy(settings)
    rs.setdefault("video", {}).update(width=WIDTH, height=HEIGHT, caption_band=CAPTION_BAND,
                                      target_seconds=max(4.0, total - 1.0))
    mode, data = transform.prepare(df, topic, rs)
    chart_secs = render(mode, data, topic, rs, chart_mp4)
    total = max(total, chart_secs)
    pad = max(0.0, total - chart_secs)

    write_ass(caption_chunks(text, cues), ass, LEAD_IN)
    fonts = _fonts_dir(work)

    conf = settings.get("audio", {}) or {}
    lufs = conf.get("loudness_lufs") or -14
    peak = conf.get("true_peak_db") or -1.5
    norm = f"loudnorm=I={lufs}:TP={peak}:LRA=11,aresample=48000"
    voice = f"[1:a]adelay={int(LEAD_IN * 1000)}:all=1,apad"
    cmd = [ffmpeg_exe(settings), "-y", "-loglevel", "error",
           "-i", chart_mp4.name, "-i", voice_mp3.name]
    if conf.get("enabled", False):
        from .. import audio as audio_mod

        offset = _music_offset(ep["key"], ep, cid)
        mood = ep.get("music_mood") or audio_mod.infer_mood({"key": f"lf_{ep['key']}"})
        track = audio_mod._generated_track(f"lf_{ep['key']}", offset + total + 1.0, mood)
        vol = float(conf.get("volume_under_voice", 0.15))
        cmd += ["-ss", f"{offset:.3f}", "-i", str(track)]
        audio_graph = (f"{voice}[vo];"
                       f"[2:a]volume={vol},afade=t=in:st=0:d=1,"
                       f"afade=t=out:st={max(0.0, total - 1.5):.2f}:d=1.5[m];"
                       f"[vo][m]amix=inputs=2:duration=first:normalize=0,{norm}[a]")
    else:
        audio_graph = f"{voice},{norm}[a]"
    # Relative names with cwd=work: Windows drive colons break the subtitles
    # filter's own option parsing.
    cmd += [
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f},fps=30,"
        f"subtitles=filename={ass.name}:fontsdir={fonts.name},format=yuv420p[v];{audio_graph}",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", final_mp4.name,
    ]
    proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-600:]}")
    chart_mp4.unlink(missing_ok=True)
    voice_mp3.unlink(missing_ok=True)
    return {"hash": _hash(ep, ch), "secs": round(total, 3), "video": final_mp4.name,
            "took": round(time.time() - began, 1)}


def _description(ep: dict[str, Any], ch: dict[str, Any], title: str) -> str:
    source = (ch.get("chart") or {}).get("source", "World Bank")
    full = ep.get("yt_url") or "watch the full video on the channel"
    tags = list(ep.get("hashtags") or [])
    if "shorts" not in [t.lower().lstrip("#") for t in tags]:
        tags.append("Shorts")
    return (f"{title}\n\n"
            f"📺 Full story: {ep.get('yt_title') or ep['title']} — {full}\n"
            f"📊 Data: {source}. Latest-year figures are first estimates and get revised.\n"
            "🎙️ Narration is a synthetic voice; the script is written and checked by the channel.\n"
            "🔔 Data in Motion: the world's numbers, animated.\n\n"
            + " ".join(f"#{t.lstrip('#')}" for t in tags) + "\n")


def build_shorts(key: str, *, only: list[str] | None = None, force: bool = False) -> list[Path]:
    """Render (or update) the episode's Shorts. Returns the finished videos."""
    ep = load(key)
    validate(ep)
    picked = [ch for ch in ep["chapters"] if not _conf(ch).get("skip")]
    if not picked:
        raise EpisodeError("Every chapter is marked short.skip; there are no Shorts to make")
    settings = load_settings()
    work = out_dir(key) / "shorts"
    work.mkdir(parents=True, exist_ok=True)
    state_path = work / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    videos = []
    for n, ch in enumerate(picked, start=1):
        cid = ch["id"]
        stem = f"{n:02d}_{cid}"
        cached = state.get(cid) or {}
        fresh = (cached.get("hash") == _hash(ep, ch) and cached.get("video") == f"{stem}.mp4"
                 and (work / cached["video"]).exists())
        wanted = (only is None or cid in only) and (force or not fresh)
        if wanted or not fresh:
            print(f"  [{n}/{len(picked)}] {cid}: narrating and rendering ...", flush=True)
            # A chapter that moved in the order leaves its old numbered files behind.
            for old in work.glob(f"[0-9][0-9]_{cid}.*"):
                old.unlink(missing_ok=True)
            state[cid] = _render_short(ep, ch, stem, work, settings)
            state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        else:
            print(f"  [{n}/{len(picked)}] {cid}: unchanged, reusing", flush=True)
        title = (_conf(ch).get("title") or ch.get("heading") or cid)[:100]
        (work / f"{stem}.txt").write_text(f"{title}\n\n{_description(ep, ch, title)}",
                                          encoding="utf-8")
        videos.append(work / state[cid]["video"])

    print(f"  done: {len(videos)} Shorts in {work}", flush=True)
    return videos
