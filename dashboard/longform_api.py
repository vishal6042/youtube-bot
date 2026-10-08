"""Dashboard endpoints for long-form episodes (see graph_bot/longform).

Kept out of server.py: long-form has its own files, its own builder and its
own state, and shares nothing with the Shorts job queue.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from graph_bot import longform
from graph_bot.config import PROJECT_ROOT, load_settings
from graph_bot.longform import EpisodeError
from graph_bot.queue import playlist_of

router = APIRouter(prefix="/api/longform")

# Episode ideas from the long-form plan. Starting one creates an empty episode
# with this title; the chapters and script still have to be written.
IDEAS: list[dict[str, str]] = [
    {"title": "India vs China: The Full Scorecard", "series": "india_in_data",
     "uses": "population, economy, life expectancy, cities, internet, child survival"},
    {"title": "Who Powers the World?", "series": "world_in_data",
     "uses": "oil, gas, coal, nuclear, solar, wind"},
    {"title": "How China Became the World's Factory", "series": "world_in_data",
     "uses": "manufacturing, exports, economy vs the US, patents, papers"},
    {"title": "Why Japan Keeps Slipping Down the Rankings", "series": "country_vs_country",
     "uses": "economy vs China, Germany and India"},
    {"title": "The Richest Countries Aren't the Biggest", "series": "money",
     "uses": "economy vs income per person, real income, tax"},
    {"title": "Who Actually Holds the World's Money?", "series": "money",
     "uses": "stock markets, reserves, foreign investment, debt"},
    {"title": "China's Energy Contradiction", "series": "world_in_data",
     "uses": "solar, wind, electric cars, coal"},
    {"title": "How India Feeds 1.4 Billion People", "series": "india_in_data",
     "uses": "rice, milk"},
    {"title": "The World Cup in Numbers, 1930-2026", "series": "sports",
     "uses": "titles, goals, match wins"},
    {"title": "Who Really Dominates Cricket?", "series": "sports",
     "uses": "Tests, ODIs, T20s, IPL"},
    {"title": "The AI Arms Race in Numbers", "series": "ai_trends",
     "uses": "compute, training cost, who builds the models"},
]

# What the chart picker offers. Codes are World Bank indicators.
INDICATOR_CHOICES = [
    {"code": "NY.GDP.MKTP.CD", "label": "Size of the economy (GDP, US dollars)"},
    {"code": "NY.GDP.MKTP.PP.CD", "label": "Size of the economy by buying power (PPP)"},
    {"code": "NY.GDP.PCAP.CD", "label": "Income per person (GDP per capita)"},
    {"code": "SP.POP.TOTL", "label": "Population"},
    {"code": "SP.DYN.LE00.IN", "label": "Life expectancy"},
    {"code": "SP.URB.TOTL.IN.ZS", "label": "Share of people living in cities"},
    {"code": "IT.NET.USER.ZS", "label": "Share of people online"},
    {"code": "SH.DYN.MORT", "label": "Child deaths per 1,000 births"},
    {"code": "MS.MIL.XPND.CD", "label": "Military spending (US dollars)"},
    {"code": "BX.GSR.GNFS.CD", "label": "Exports (US dollars)"},
]

VOICES = [
    {"id": "en-IN-NeerjaNeural", "label": "Neerja · Indian English"},
    {"id": "en-IN-PrabhatNeural", "label": "Prabhat · Indian English"},
    {"id": "en-US-AriaNeural", "label": "Aria · US English"},
    {"id": "en-US-GuyNeural", "label": "Guy · US English"},
    {"id": "en-GB-SoniaNeural", "label": "Sonia · British English"},
]


class _Builder:
    """Runs one episode build at a time in a child process.

    A child process, not a thread: matplotlib keeps global state, and a crash in
    a render must not take the dashboard down with it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.key: str | None = None
        self.proc: subprocess.Popen | None = None
        self.tail: list[str] = []

    def running(self) -> str | None:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return self.key
            return None

    def start(self, key: str, force: bool) -> None:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                raise HTTPException(409, f"'{self.key}' is already rendering. Wait for it to finish.")
            cmd = [sys.executable, "-u", "-m", "graph_bot.longform", "build", key]
            if force:
                cmd.append("--force")
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            self.key, self.tail = key, []
            self.proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                         errors="replace")
        threading.Thread(target=self._drain, args=(self.proc,), daemon=True).start()

    def _drain(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout or []:
            self.tail = (self.tail + [line.rstrip()])[-40:]
        proc.wait()

    def stop(self) -> bool:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
                return True
            return False


builder = _Builder()


def _summary(key: str) -> dict[str, Any]:
    try:
        s = longform.summary(key)
    except EpisodeError as exc:
        raise HTTPException(404, str(exc))
    ours = builder.running() == key
    build = dict(s.get("build") or {})
    live = ours
    if build.get("status") == "running" and not ours:
        # Either a build started from the command line (its state file is still
        # being written) or one that died without recording a result. The file's
        # age tells them apart: a chapter never takes this long.
        try:
            age = time.time() - (longform.out_dir(key) / "state.json").stat().st_mtime
        except OSError:
            age = 1e9
        if age < 420:
            live = True
        else:
            build["status"] = "stopped"
    s["build"] = {**build, "live": live, "stoppable": ours, "log": builder.tail[-12:] if ours else []}
    s["playlist"] = playlist_of(s.get("series") or "world_in_data")[0]
    s.pop("_ranks", None)
    return s


@router.get("")
def api_list() -> dict[str, Any]:
    episodes = []
    for key in longform.list_keys():
        try:
            episodes.append(_summary(key))
        except HTTPException:
            continue
    titles = {e["title"].lower() for e in episodes}
    return {
        "episodes": episodes,
        "ideas": [{**i, "playlist": playlist_of(i["series"])[0]}
                  for i in IDEAS if i["title"].lower() not in titles],
        "voices": VOICES,
        "indicators": INDICATOR_CHOICES,
        "building": next((e["key"] for e in episodes if e["build"].get("live")), None),
    }


class NewEpisodeReq(BaseModel):
    title: str
    series: str | None = None


@router.post("")
def api_create(req: NewEpisodeReq) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(400, "The episode needs a title")
    key = "_".join("".join(c.lower() if c.isalnum() else " " for c in title).split())[:48].strip("_")
    if not key:
        raise HTTPException(400, "The title needs at least one letter or number")
    if key in longform.list_keys():
        raise HTTPException(400, "An episode with that title already exists")
    try:
        longform.save(key, {"title": title, "series": req.series or "world_in_data",
                            "voice": VOICES[0]["id"], "voice_rate": "+10%",
                            "music_mood": "majestic", "target_minutes": 5, "chapters": []})
    except EpisodeError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "key": key}


@router.get("/{key}")
def api_get(key: str) -> dict[str, Any]:
    return _summary(key)


class SaveReq(BaseModel):
    episode: dict[str, Any]


# Fields the editor may change. Everything else in the file is left as it is.
_EDITABLE = ("title", "yt_title", "series", "voice", "voice_rate", "music_mood",
             "target_minutes", "reviewed")
_CHAPTER_FIELDS = ("id", "heading", "chart", "narration", "check")


@router.post("/{key}")
def api_save(key: str, req: SaveReq) -> dict[str, Any]:
    try:
        ep = longform.load(key)
    except EpisodeError as exc:
        raise HTTPException(404, str(exc))
    for f in _EDITABLE:
        if f in req.episode:
            ep[f] = req.episode[f]
    if "chapters" in req.episode:
        ep["chapters"] = [
            {f: ch[f] for f in _CHAPTER_FIELDS if ch.get(f) not in (None, "")}
            for ch in req.episode["chapters"]
        ]
    try:
        longform.save(key, ep)
    except EpisodeError as exc:
        raise HTTPException(400, str(exc))
    return _summary(key)


class BuildReq(BaseModel):
    force: bool = False


@router.post("/{key}/build")
def api_build(key: str, req: BuildReq) -> dict[str, Any]:
    try:
        ep = longform.load(key)
        longform.validate(ep)
    except EpisodeError as exc:
        raise HTTPException(400, str(exc))
    if not ep["chapters"]:
        raise HTTPException(400, "Add at least one chapter before rendering")
    builder.start(key, req.force)
    return {"ok": True}


@router.post("/{key}/build/stop")
def api_build_stop(key: str) -> dict[str, Any]:
    if builder.running() != key:
        raise HTTPException(400, "This episode is not rendering")
    return {"ok": builder.stop()}


def _stream(path: Path, request: Request, media_type: str) -> Response:
    """Serve a file with Range support, which browsers need to scrub media."""
    size = path.stat().st_size
    header = request.headers.get("range")
    if not header:
        return FileResponse(path, media_type=media_type,
                            headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"})
    try:
        _, _, rng = header.partition("=")
        start_s, _, end_s = rng.partition("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else size - 1
    except ValueError:
        raise HTTPException(416, "Bad Range header")
    start, end = max(0, start), min(end, size - 1)
    if start > end:
        raise HTTPException(416, "Range not satisfiable")

    def chunks(chunk_size: int = 1024 * 512):
        with path.open("rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                data = fh.read(min(chunk_size, left))
                if not data:
                    break
                left -= len(data)
                yield data

    return StreamingResponse(chunks(), status_code=206, media_type=media_type, headers={
        "Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1), "Cache-Control": "no-store"})


@router.get("/{key}/video")
def api_video(key: str, request: Request) -> Response:
    try:
        path = longform.out_dir(key) / "episode.mp4"
    except EpisodeError as exc:
        raise HTTPException(404, str(exc))
    if not path.exists():
        raise HTTPException(404, "This episode has not been rendered yet")
    return _stream(path, request, "video/mp4")


@router.get("/{key}/chapter/{chapter_id}/video")
def api_chapter_video(key: str, chapter_id: str, request: Request) -> Response:
    try:
        done = longform.read_state(key).get("chapters", {}).get(chapter_id) or {}
        path = longform.out_dir(key) / "chapters" / str(done.get("video", "missing"))
    except EpisodeError as exc:
        raise HTTPException(404, str(exc))
    if not path.exists():
        raise HTTPException(404, "This chapter has not been rendered yet")
    return _stream(path, request, "video/mp4")


@router.get("/{key}/chapter/{chapter_id}/voice")
def api_chapter_voice(key: str, chapter_id: str, request: Request) -> Response:
    """The narration for one chapter as it is written now, spoken on demand.

    Cached by the words, voice and pace, so listening twice costs one call.
    """
    try:
        ep = longform.load(key)
    except EpisodeError as exc:
        raise HTTPException(404, str(exc))
    ch = next((c for c in ep["chapters"] if c.get("id") == chapter_id), None)
    if ch is None:
        raise HTTPException(404, "No such chapter")
    text = " ".join((ch.get("narration") or "").split())
    if not text:
        raise HTTPException(400, "This chapter has no narration yet")
    voice = ep.get("voice") or VOICES[0]["id"]
    rate = ep.get("voice_rate") or "+0%"
    digest = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:16]
    path = longform.out_dir(key) / "preview" / f"{digest}.mp3"
    if not path.exists():
        from graph_bot.longform.narrate import speak

        try:
            speak(text, voice, path, load_settings(), rate=rate)
        except Exception as exc:
            raise HTTPException(502, str(exc))
    return _stream(path, request, "audio/mpeg")


@router.get("/{key}/chapter/{chapter_id}/figures")
def api_chapter_figures(key: str, chapter_id: str) -> dict[str, Any]:
    """The numbers behind a chapter's chart, for checking the script against."""
    from graph_bot.longform.build import INDICATORS, chapter_topic
    from graph_bot.render import _fmt

    try:
        ep = longform.load(key)
        ch = next((c for c in ep["chapters"] if c.get("id") == chapter_id), None)
        if ch is None:
            raise HTTPException(404, "No such chapter")
        longform.validate({**ep, "chapters": [ch]})
        topic, df = chapter_topic(ep, ch, load_settings())
    except EpisodeError as exc:
        return {"ok": False, "error": str(exc), "figures": []}
    except HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "error": f"Could not load the data: {exc}", "figures": []}

    prefix = INDICATORS.get(ch["chart"]["code"], {}).get("prefix", "")
    fmt = lambda v: prefix + _fmt(float(v), topic)  # noqa: E731
    wide = df.pivot_table(index="year", columns="entity", values="value")
    lo, hi = int(wide.index.min()), int(wide.index.max())
    figures: list[str] = []
    mode = ch["chart"]["mode"]

    if mode == "line_grow":
        s = wide[topic["entity_filter"]].dropna()
        figures.append(f"{int(s.index[0])}: {fmt(s.iloc[0])}")
        figures.append(f"{int(s.index[-1])}: {fmt(s.iloc[-1])}")
        figures.append(f"Lowest: {fmt(s.min())} in {int(s.idxmin())}; highest: {fmt(s.max())} in {int(s.idxmax())}")
    elif mode == "line_multi":
        names = topic["entities"]
        both = wide[names].dropna()
        for y in (int(both.index[0]), int(both.index[-1])):
            figures.append(f"{y}: " + ", ".join(f"{n} {fmt(both.loc[y, n])}" for n in names))
        if len(names) == 2:
            a, b = names
            lead = both[a] > both[b]
            flips = [(int(y), a if v else b) for i, (y, v) in enumerate(lead.items())
                     if i > 0 and v != lead.iloc[i - 1]]
            figures.append("Lead changes: " + (", ".join(f"{w} ahead from {y}" for y, w in flips)
                                               if flips else "none in this period"))
    else:
        ranks = topic.get("_ranks")
        for y in (lo, hi):
            top = wide.loc[y].dropna().sort_values(ascending=False).head(3)
            figures.append(f"{y}: " + ", ".join(f"{e} {fmt(v)}" for e, v in top.items()))
        hero = topic.get("highlight")
        if hero and hero in wide:
            if ranks is not None and hero in ranks:
                r = ranks[hero]
                figures.append(f"{hero}: {fmt(wide.loc[lo, hero])} in {lo} (#{int(r.loc[lo])}), "
                               f"{fmt(wide.loc[hi, hero])} in {hi} (#{int(r.loc[hi])})")
                figures.append(f"{hero}'s lowest rank: #{int(r.max())} in {int(r.idxmax())}; "
                               f"highest: #{int(r.min())} in {int(r.idxmin())}")
            else:
                figures.append(f"{hero}: {fmt(wide.loc[lo, hero])} in {lo}, {fmt(wide.loc[hi, hero])} in {hi}")
    return {"ok": True, "figures": figures, "source": topic.get("source"), "years": [lo, hi]}
