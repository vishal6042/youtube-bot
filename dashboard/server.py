"""FastAPI server for the Data in Motion mission-control dashboard.

Run from the project root:

    .venv\\Scripts\\python.exe -m dashboard.server            # http://127.0.0.1:8787

State comes straight from the pipeline's own sources of truth (output/, export/,
data/upload_log.json via graph_bot.queue), so the dashboard can never drift from
the CLI. Render jobs run as one-at-a-time subprocesses of dashboard.worker;
finished-job history persists to data/dashboard_jobs.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg
import uvicorn
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from graph_bot.config import (  # noqa: E402
    CONFIG_DIR,
    load_settings,
    load_topics,
    resolve_path,
    topic_episode,
    topic_series,
)
from graph_bot.pipeline import _last_rendered  # noqa: E402
from graph_bot import store  # noqa: E402
from graph_bot.queue import (  # noqa: E402
    PLAYLISTS,
    SERIES_ORDER,
    _exported_keys,
    build_status,
    load_discarded,
    load_log,
    next_up,
    playlist_of,
)

LOG_TAIL_PERSISTED = 120  # lines of log kept per finished job on disk
HISTORY_KEPT = 40

# Agent states arrive as ::agent::<name>::<state> markers from dashboard.worker.
# Typical seconds per agent, used only to estimate an in-flight percentage —
# capped at 95% so a bar never claims done before the marker says so.
AGENT_RE = re.compile(r"::agent::(\w+)::(active|done|failed)\b")

AGENT_EST_SEC = {
    "video": 110.0,
    "music": 6.0,
    "mixing": 10.0,
    "subtitle": 2.0,
    "exporting": 4.0,
    "thumbnail": 6.0,
}


class Job:
    def __init__(self, keys: list[str], label: str, args: list[str]):
        self.id = uuid.uuid4().hex[:10]
        self.keys = keys
        self.label = label
        self.args = args
        self.status = "queued"  # queued | running | done | failed | cancelled
        self.created_at = _now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.current_key: str | None = None
        self.stage: str | None = None
        self.agents: dict[str, str] = {}  # agent name -> active | done | failed
        self.agent_started: dict[str, float] = {}  # agent name -> epoch seconds
        self.steps: list[dict[str, Any]] = []  # ordered agent timeline for the whole job
        self.log: list[str] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.proc: subprocess.Popen | None = None

    def to_dict(self, log_tail: int | None = None) -> dict[str, Any]:
        d = {
            "id": self.id,
            "keys": self.keys,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_key": self.current_key,
            "stage": self.stage,
            "agents": self.agents,
            "progress": self._progress(),
            "steps": self.steps,
            "results": self.results,
            "log_len": len(self.log),
        }
        if log_tail:
            d["log"] = self.log[-log_tail:]
        return d

    def _progress(self) -> dict[str, dict[str, Any]]:
        """Per-agent completion estimate for the current topic."""
        prog: dict[str, dict[str, Any]] = {}
        for name, est in AGENT_EST_SEC.items():
            st = self.agents.get(name)
            if st in ("done", "failed"):
                prog[name] = {"state": st, "pct": 100}
            elif st == "active":
                elapsed = time.time() - self.agent_started.get(name, time.time())
                prog[name] = {"state": "active", "pct": min(95, int(elapsed / est * 100))}
            else:
                prog[name] = {"state": "idle", "pct": 0}
        return prog


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class JobManager:
    """Runs render jobs strictly one at a time (renders are CPU-heavy)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.queue: list[Job] = []
        self.current: Job | None = None
        self.history: list[dict[str, Any]] = self._load_history()
        threading.Thread(target=self._run_loop, daemon=True).start()

    # ---- persistence ----
    def _load_history(self) -> list[dict[str, Any]]:
        # The dashboard must still start when Postgres is down; job history is
        # a background concern, not a reason to refuse to boot.
        try:
            return store.load_jobs(HISTORY_KEPT)
        except Exception as exc:
            print(f"job history unavailable: {exc}")
            return []

    def _save_job(self, d: dict[str, Any]) -> None:
        try:
            store.save_job(d)
        except Exception as exc:  # never let persistence kill the run loop
            print(f"could not persist job {d.get('id')}: {exc}")

    # ---- public API ----
    def submit(self, keys: list[str], label: str, args: list[str]) -> Job:
        job = Job(keys, label, args)
        with self.lock:
            self.queue.append(job)
        return job

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            for i, j in enumerate(self.queue):
                if j.id == job_id:
                    j.status = "cancelled"
                    j.finished_at = _now()
                    self.queue.pop(i)
                    self._finish(j)
                    return True
            j = self.current
            if j and j.id == job_id and j.proc:
                j.status = "cancelled"
                j.proc.terminate()
                return True
        return False

    def find(self, job_id: str) -> Job | None:
        with self.lock:
            if self.current and self.current.id == job_id:
                return self.current
            for j in self.queue:
                if j.id == job_id:
                    return j
        return None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "job": self.current.to_dict(log_tail=40) if self.current else None,
                "queue": [j.to_dict() for j in self.queue],
                "history": self.history[:HISTORY_KEPT],
                "failures": self._failures(),
            }

    def _failures(self) -> list[dict[str, Any]]:
        """Topics whose most recent outcome was a failure (newest first)."""
        pending = {k for j in self.queue for k in j.keys}
        if self.current:
            pending.update(self.current.keys)
            if self.current.current_key:
                pending.add(self.current.current_key)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        if self.current:
            sources.append({"results": self.current.results, "id": self.current.id,
                            "at": self.current.started_at})
        sources += self.history
        for j in sources:
            for key, res in (j.get("results") or {}).items():
                if key in seen:
                    continue
                seen.add(key)
                if res.get("status") == "failed" and key not in pending:
                    out.append({"key": key, "error": res.get("error", ""),
                                "job_id": j.get("id"),
                                "at": j.get("finished_at") or j.get("at") or ""})
        return out

    # ---- worker loop ----
    def _run_loop(self) -> None:
        while True:
            job: Job | None = None
            with self.lock:
                if self.current is None and self.queue:
                    job = self.queue.pop(0)
                    self.current = job
            if job is None:
                threading.Event().wait(0.5)
                continue
            self._run(job)
            with self.lock:
                self.current = None
                self._finish(job)

    def _run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = _now()
        job.stage = "starting"
        cmd = [sys.executable, "-u", "-m", "dashboard.worker"] + job.args
        try:
            creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            # The pipeline prints ♪/✅/📦; without UTF-8 mode a Windows pipe
            # defaults to cp1252 and those prints crash the worker.
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            job.proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation,
                env=env,
            )
        except Exception as exc:
            job.status = "failed"
            job.log.append(f"failed to start worker: {exc}")
            job.finished_at = _now()
            return

        assert job.proc.stdout is not None
        for raw in job.proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            self._ingest(job, line)
            if len(job.log) > 4000:
                del job.log[:1000]
        code = job.proc.wait()
        job.finished_at = _now()
        if job.status != "cancelled":
            job.status = "done" if code == 0 else "failed"
        job.stage = None

    def _ingest(self, job: Job, line: str) -> None:
        # Markers are matched anywhere in the line: the worker's threads can
        # still leave a partial line in front of one.
        marker = AGENT_RE.search(line)
        if line.startswith("::topic::"):
            job.current_key = line.split("::topic::", 1)[1].strip()
            job.stage = "video"
            job.agents = {}
            job.results.setdefault(job.current_key, {"status": "working"})
        elif marker:
            name, state = marker.group(1), marker.group(2)
            job.agents[name] = state
            if state == "active":
                job.agent_started[name] = time.time()
                job.stage = name
                job.steps.append({"agent": name, "topic": job.current_key,
                                  "at": _now(), "state": "active", "secs": None})
            else:
                started = job.agent_started.get(name)
                for step in reversed(job.steps):
                    if step["agent"] == name and step["state"] == "active":
                        step["state"] = state
                        step["secs"] = round(time.time() - started, 1) if started else None
                        break
                if job.stage == name:
                    # Keep the headline on whatever is still running, if anything.
                    still = [a for a, s in job.agents.items() if s == "active"]
                    job.stage = still[0] if still else name
        elif line.startswith("::exported::"):
            _, key, path = line.split("::", 3)[1:]  # exported, key, path
            job.results[key] = {"status": "ok", "export": path}
            job.stage = "exported"
        elif line.startswith("::failed::"):
            parts = line.split("::", 3)
            key, err = parts[2], parts[3] if len(parts) > 3 else ""
            job.results[key] = {"status": "failed", "error": err}
        job.log.append(line)

    def _finish(self, job: Job) -> None:
        d = job.to_dict(log_tail=LOG_TAIL_PERSISTED)
        self.history.insert(0, d)
        del self.history[HISTORY_KEPT:]
        self._save_job(d)


manager = JobManager()
app = FastAPI(title="Data in Motion — Mission Control")


@app.exception_handler(psycopg.OperationalError)
def _db_down(_request: Request, exc: psycopg.OperationalError) -> Response:
    """Operational state lives in Postgres now, so say so plainly when it is
    unreachable — a raw 500 with a driver traceback helps nobody."""
    detail = str(exc).splitlines()[0] if str(exc) else "connection failed"
    return Response(
        content=json.dumps({"detail": f"Database unavailable — {detail}"}),
        status_code=503,
        media_type="application/json",
    )


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def _series_payload() -> dict[str, Any]:
    by_series = build_status()
    ordered = [s for s in SERIES_ORDER if s in by_series]
    ordered += [s for s in sorted(by_series) if s not in SERIES_ORDER]

    def state_of(e: dict[str, Any]) -> str:
        if e["uploaded"]:
            return "uploaded"
        if e.get("discarded"):
            return "discarded"
        if e["exported"]:
            return "ready"
        if e["rendered"]:
            return "rendered"
        return "missing"

    brand_copy = load_brand()["playlists"]
    series_list = []
    counts = {"uploaded": 0, "ready": 0, "rendered": 0, "discarded": 0,
              "missing": 0, "total": 0}
    for s in ordered:
        items = []
        for e in by_series[s]:
            st = state_of(e)
            counts[st] += 1
            counts["total"] += 1
            has_thumb = bool(
                e["exported"] and (PROJECT_ROOT / e["exported"] / "thumbnail.jpg").exists()
            )
            items.append({**e, "state": st, "has_thumb": has_thumb})
        name, exists = playlist_of(s)  # already honours brand.json overrides
        copy = brand_copy.get(s, {})
        series_list.append(
            {
                "series": s,
                "playlist": name,
                "description": copy.get("description", ""),
                "playlist_exists": exists,
                "created_manually": "created" in copy,
                "uploaded": sum(1 for i in items if i["state"] == "uploaded"),
                "total": len(items),
                "items": items,
            }
        )

    # ---- upload queue: everything staged, richest form ----
    meta_by_key = {}
    for key, (_, path) in _latest_renders().items():
        try:
            meta_by_key[key] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    by_key = {i["key"]: i for s in series_list for i in s["items"]}
    uploaded_by_series: dict[str, list[dict[str, Any]]] = {}
    for s in series_list:
        uploaded_by_series[s["series"]] = [i for i in s["items"] if i["state"] == "uploaded"]

    picks = []
    for p in next_up(by_series, 60):
        # next_up carries the true series; deriving from the key alone loses
        # explicit `series:` fields (fallback path only).
        series = p.get("series") or topic_series({"key": p["key"]})
        name, exists = playlist_of(series)
        item = by_key.get(p["key"], {})
        meta = meta_by_key.get(p["key"], {})
        prev = uploaded_by_series.get(series, [])
        picks.append({
            **p,
            "series": series,
            "playlist": name,
            "playlist_exists": exists,
            "blocked": not exists,
            "episode": item.get("episode"),
            "series_total": len(by_series.get(series, [])),
            "duration_sec": meta.get("duration_sec"),
            "has_thumb": item.get("has_thumb", False),
            "rendered_on": (meta.get("generated_at") or "")[:10] or None,
            "source": meta.get("source"),
            "prev_uploaded": prev[-1]["title"] if prev else None,
        })

    # A saved manual order wins; anything not in it keeps recommended order.
    order = load_order()
    if order:
        rank = {k: i for i, k in enumerate(order)}
        picks.sort(key=lambda p: (rank.get(p["key"], len(rank)),))
    for i, p in enumerate(picks):
        nxt = next((q for q in picks[i + 1:] if q["series"] == p["series"]), None)
        p["next_in_playlist"] = nxt["title"] if nxt else None

    discarded = []
    for s in series_list:
        for i in s["items"]:
            if i["state"] != "discarded":
                continue
            discarded.append({
                **i,
                "series": s["series"],
                "playlist": s["playlist"],
                "duration_sec": meta_by_key.get(i["key"], {}).get("duration_sec"),
            })
    discarded.sort(key=lambda d: d.get("discarded_at") or "", reverse=True)

    return {
        "series": series_list,
        "next_up": picks,
        "counts": counts,
        "custom_order": bool(order),
        "discarded": discarded,
    }


def load_order() -> list[str]:
    return store.load_order()


class PlaylistCreatedReq(BaseModel):
    series: str
    created: bool = True


@app.post("/api/playlist-created")
def api_playlist_created(req: PlaylistCreatedReq) -> dict[str, Any]:
    """Record that a playlist now exists on YouTube (clears the ⚠ warning)."""
    data = load_brand()
    entry = data["playlists"].setdefault(
        req.series, {"name": playlist_of(req.series)[0], "description": ""}
    )
    entry["created"] = bool(req.created)
    save_brand(data)
    return {"ok": True, "series": req.series, "created": req.created}


class OrderReq(BaseModel):
    keys: list[str]


@app.post("/api/queue-order")
def api_queue_order(req: OrderReq) -> dict[str, Any]:
    """Persist a manual upload order (drag & drop)."""
    store.save_order(req.keys)
    return {"ok": True}


@app.post("/api/queue-order/reset")
def api_queue_order_reset() -> dict[str, Any]:
    store.clear_order()
    return {"ok": True}


@app.get("/api/state")
def api_state() -> dict[str, Any]:
    return {**_series_payload(), **manager.snapshot(),
            "upload_batch": store.batch_load(), "upload_run": runner.snapshot(),
            "upload_quota": store.quota_status(), "now": _now()}


# --------------------------------------------------------------------------- #
# Topic catalog + review phase
# --------------------------------------------------------------------------- #
def _latest_renders() -> dict[str, tuple[str, Path]]:
    """key -> (date, metadata path) of the most recent render."""
    out_root = resolve_path(load_settings(), "output")
    latest: dict[str, tuple[str, Path]] = {}
    for p in out_root.glob("*/*/metadata.json"):
        key, date = p.parent.name, p.parent.parent.name
        if key not in latest or date > latest[key][0]:
            latest[key] = (date, p)
    return latest


@app.get("/api/topics")
def api_topics() -> dict[str, Any]:
    """Every configured topic with its lifecycle phase.

    planned -> draft (in review) / rejected -> approved -> ready (exported)
    -> uploaded. Later phases win when several apply.
    """
    log = load_log()
    exported = _exported_keys()
    latest = _latest_renders()

    topics = []
    for t in load_topics():
        key = t["key"]
        meta: dict[str, Any] | None = None
        render_date: str | None = None
        if key in latest:
            render_date, p = latest[key]
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                meta = None
        status = (meta or {}).get("status")

        if key in log:
            phase = "uploaded"
        elif key in exported:
            phase = "ready"
        elif status == "approved":
            phase = "approved"
        elif status == "rejected":
            phase = "rejected"
        elif status:
            phase = "draft"
        else:
            phase = "planned"

        series = topic_series(t)
        topics.append({
            "key": key,
            "title": t.get("title", ""),
            "subtitle": t.get("subtitle", ""),
            "series": series,
            "playlist": playlist_of(series)[0],
            "episode": topic_episode(t),
            "mode": t.get("mode", "bar_race"),
            "source": t.get("source", ""),
            "phase": phase,
            "render_date": render_date,
            "duration_sec": (meta or {}).get("duration_sec"),
            "video": (meta or {}).get("video"),
            "note": (meta or {}).get("note"),
            "approved_by": (meta or {}).get("approved_by"),
            "exported": exported.get(key),
            "uploaded_at": log.get(key, {}).get("uploaded_at"),
            "url": log.get(key, {}).get("url"),
        })
    return {"topics": topics}


class ReviewReq(BaseModel):
    key: str
    action: str  # approve | reject
    note: str | None = None


@app.post("/api/review")
def api_review(req: ReviewReq) -> dict[str, Any]:
    if req.action not in {"approve", "reject"}:
        raise HTTPException(400, "action must be approve or reject")
    latest = _latest_renders()
    if req.key not in latest:
        raise HTTPException(404, f"No render found for '{req.key}'")
    _, path = latest[req.key]
    meta = json.loads(path.read_text(encoding="utf-8"))
    status = "approved" if req.action == "approve" else "rejected"
    meta["status"] = status
    meta[f"{status}_at"] = _now()
    if req.action == "approve":
        meta["approved_by"] = "dashboard"
    if req.note:
        meta["note"] = req.note
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "phase": status}


class ExportReq(BaseModel):
    key: str


@app.post("/api/export")
def api_export(req: ExportReq) -> dict[str, Any]:
    """Stage the latest approved render of a topic for manual upload."""
    from graph_bot.publish.manual import export_one

    latest = _latest_renders()
    if req.key not in latest:
        raise HTTPException(404, f"No render found for '{req.key}'")
    _, path = latest[req.key]
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("status") != "approved":
        raise HTTPException(400, "Only approved drafts can be exported — approve it first")
    export_root = resolve_path(load_settings(), "export") / dt.date.today().isoformat()
    export_root.mkdir(parents=True, exist_ok=True)
    dest = export_one(path, meta, export_root)
    if dest is None:
        raise HTTPException(500, "Video file missing on disk")
    return {"ok": True, "exported": str(dest.relative_to(PROJECT_ROOT))}


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def _typical_secs_per_topic() -> float:
    """Median wall-clock per topic from recent successful jobs (fallback 130s)."""
    samples: list[float] = []
    for j in manager.history[:12]:
        if j.get("status") != "done" or not j.get("started_at") or not j.get("finished_at"):
            continue
        n = max(1, len(j.get("results") or {}))
        try:
            dur = (dt.datetime.fromisoformat(j["finished_at"])
                   - dt.datetime.fromisoformat(j["started_at"])).total_seconds()
        except Exception:
            continue
        if dur > 0:
            samples.append(dur / n)
    if not samples:
        return 130.0
    samples.sort()
    return samples[len(samples) // 2]


@app.get("/api/plan")
def api_plan(batch: int = 3, series: str | None = None, mode: str = "new") -> dict[str, Any]:
    """Dry run: exactly which topics a launch with these options would render.

    Strategies map to real intents rather than raw ordering:
      new    -> never rendered (genuinely new content)
      staged -> rendered, not yet uploaded (safe to improve before posting)
      recut  -> oldest first, including already-published videos (re-cuts)
    """
    settings = load_settings()
    out_root = resolve_path(settings, "output")
    exported = _exported_keys()
    log = load_log()

    topics = load_topics()
    if series:
        topics = [t for t in topics if topic_series(t) == series]

    # Same ordering the batch runner uses: never-rendered first, then oldest.
    ranked = sorted(topics, key=lambda t: (_last_rendered(t["key"], out_root), t["key"]))
    if mode == "new":
        ranked = [t for t in ranked if not _last_rendered(t["key"], out_root)]
    elif mode == "staged":
        # Not yet public, so re-rendering costs nothing but improves the post.
        ranked = [t for t in ranked
                  if t["key"] not in log and exported.get(t["key"])]
    elif mode == "recut":
        ranked = [t for t in ranked if t["key"] in log]

    busy = {k for j in manager.queue for k in j.keys}
    if manager.current:
        busy.update(manager.current.keys)
        if manager.current.current_key:
            busy.add(manager.current.current_key)

    # Metadata of the newest render, for the length/thumbnail of what exists today.
    meta_by_key: dict[str, dict[str, Any]] = {}
    for key, (_, path) in _latest_renders().items():
        try:
            meta_by_key[key] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    picked = []
    for t in ranked[: max(0, batch)]:
        key = t["key"]
        last = _last_rendered(key, out_root)
        s = topic_series(t)
        name, exists = playlist_of(s)
        meta = meta_by_key.get(key, {})
        export_rel = exported.get(key)
        picked.append({
            "key": key,
            "staged_new": not last,   # added but never rendered -> revertible
            "title": t.get("title", ""),
            "subtitle": t.get("subtitle", ""),
            "series": s,
            "playlist": name,
            "playlist_exists": exists,
            "episode": topic_episode(t),
            "chart_mode": t.get("mode"),
            "source": t.get("source"),
            "fetcher": t.get("fetcher") or ("curated" if t.get("file") else
                                            "csv" if t.get("url") else None),
            "mood": t.get("mood"),
            "narrated": bool(t.get("scene")),
            "duration_sec": meta.get("duration_sec"),
            "has_thumb": bool(
                export_rel and (PROJECT_ROOT / export_rel / "thumbnail.jpg").exists()
            ),
            "last_rendered": last or None,
            "uploaded": key in log,
            "exported": bool(export_rel),
            "already_queued": key in busy,
        })

    per = _typical_secs_per_topic()
    all_topics = load_topics()
    ready = sum(1 for t in all_topics
                if t["key"] not in log and exported.get(t["key"]))
    by_playlist: dict[str, int] = {}
    for t in ranked:
        by_playlist[playlist_of(topic_series(t))[0]] = (
            by_playlist.get(playlist_of(topic_series(t))[0], 0) + 1
        )

    return {
        "topics": picked,
        "secs_each": round(per),
        "secs_total": round(per * len(picked)),
        "ready_count": ready,
        "available": len(ranked),
        "available_by_playlist": by_playlist,
        # So the UI can pick a sensible default strategy and label the tabs.
        "counts": {
            "new": sum(1 for t in all_topics if not _last_rendered(t["key"], out_root)),
            "staged": ready,
            "recut": sum(1 for t in all_topics if t["key"] in log),
        },
    }


class RenderReq(BaseModel):
    keys: list[str] = []
    batch: int | None = None
    series: str | None = None
    refresh: bool = False


@app.post("/api/render")
def api_render(req: RenderReq) -> dict[str, Any]:
    valid = {t["key"] for t in load_topics()}
    bad = [k for k in req.keys if k not in valid]
    if bad:
        raise HTTPException(400, f"Unknown topic(s): {', '.join(bad)}")
    if not req.keys and not req.batch:
        raise HTTPException(400, "Pass keys or batch")

    # One job per video: each gets its own history entry, progress and retry.
    jobs = []
    for key in req.keys:
        args = ["--topics", key]
        if req.refresh:
            args.append("--refresh")
        jobs.append(manager.submit([key], key, args))

    if req.batch:
        args = ["--batch", str(req.batch)]
        if req.series:
            args += ["--series", req.series]
        if req.refresh:
            args.append("--refresh")
        label = f"next {req.batch}" + (f" of {req.series}" if req.series else "")
        jobs.append(manager.submit([], label, args))

    return {"jobs": [j.to_dict() for j in jobs], "job": jobs[0].to_dict() if jobs else None}


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel(job_id: str) -> dict[str, Any]:
    if not manager.cancel(job_id):
        raise HTTPException(404, "Job not found or already finished")
    return {"ok": True}


@app.get("/api/jobs/{job_id}/log")
def api_log(job_id: str, offset: int = 0) -> dict[str, Any]:
    job = manager.find(job_id)
    if job:
        return {"lines": job.log[offset:], "next": len(job.log), "status": job.status}
    for h in manager.history:
        if h["id"] == job_id:
            return {"lines": h.get("log", []), "next": h.get("log_len", 0),
                    "status": h["status"]}
    raise HTTPException(404, "Job not found")


# --------------------------------------------------------------------------- #
# Upload log
# --------------------------------------------------------------------------- #
class MarkReq(BaseModel):
    key: str
    url: str | None = None


@app.post("/api/mark")
def api_mark(req: MarkReq) -> dict[str, Any]:
    valid = {t["key"] for t in load_topics()}
    if req.key not in valid:
        raise HTTPException(400, f"Unknown topic: {req.key}")
    store.mark_uploaded(req.key, req.url, _now())
    return {"ok": True}


class DiscardReq(BaseModel):
    key: str
    reason: str = ""


@app.post("/api/discard")
def api_discard(req: DiscardReq) -> dict[str, Any]:
    """Drop a staged video that will never be posted.

    Deliberately NOT the same as marking it uploaded: the upload history must
    only ever contain videos that actually went live. The export folder is moved
    to export/_discarded/ rather than erased, so this is reversible.
    """
    valid = {t["key"] for t in load_topics()}
    if req.key not in valid:
        raise HTTPException(400, f"Unknown topic: {req.key}")
    if req.key in load_log():
        raise HTTPException(400, "Already uploaded — unmark it first if that was wrong")

    exported = _exported_keys().get(req.key)
    moved_to = None
    if exported:
        src = PROJECT_ROOT / exported
        if src.exists():
            bin_dir = PROJECT_ROOT / "export" / "_discarded"
            bin_dir.mkdir(parents=True, exist_ok=True)
            dest = bin_dir / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{src.name}"
            shutil.move(str(src), str(dest))
            moved_to = str(dest.relative_to(PROJECT_ROOT))

    store.discard(
        req.key, req.reason,
        from_path=exported,   # where it came from, so restore is exact
        moved_to=moved_to,    # where it now sits under export/_discarded/
        discarded_at=_now(),
    )
    # Drop it out of any saved manual order so ranks stay contiguous.
    store.remove_from_order(req.key)
    return {"ok": True, "key": req.key, "moved_to": moved_to}


@app.post("/api/discard/restore")
def api_discard_restore(req: DiscardReq) -> dict[str, Any]:
    """Put a discarded video back in the queue, moving its export folder back."""
    entry = store.restore(req.key)
    if entry is None:
        raise HTTPException(404, f"'{req.key}' is not discarded")

    src = PROJECT_ROOT / entry["moved_to"] if entry.get("moved_to") else None
    dest = PROJECT_ROOT / entry["from"] if entry.get("from") else None
    if src and dest and src.exists() and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    return {"ok": True, "key": req.key}


@app.post("/api/unmark")
def api_unmark(req: MarkReq) -> dict[str, Any]:
    store.unmark(req.key)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Settings: channel copy, playlist descriptions, brand images
# --------------------------------------------------------------------------- #
BRAND_DIR = PROJECT_ROOT / "assets" / "brand"
BRAND_JSON = PROJECT_ROOT / "data" / "brand.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# What each brand image is for, plus YouTube's recommended size.
IMAGE_ROLES = {
    "channel_avatar": ("Profile picture", "800 × 800"),
    "channel_banner": ("Channel banner", "2560 × 1440 (safe area 1546 × 423)"),
    "watermark": ("Video watermark", "150 × 150"),
    "community": ("Community post", "—"),
}


def _role_of(name: str) -> tuple[str, str]:
    for prefix, role in IMAGE_ROLES.items():
        if name.startswith(prefix):
            return role
    return ("Brand asset", "—")


def load_brand() -> dict[str, Any]:
    """Brand copy from the brand_channel/brand_playlist tables.

    data/brand.json is only the read fallback for when the database is down
    (stale beats broken); nothing writes it any more.
    """
    data: dict[str, Any] = {"channel": {"description": "", "tagline": ""}, "playlists": {}}
    try:
        data = store.brand_load()
    except Exception:
        if BRAND_JSON.exists():
            try:
                data.update(json.loads(BRAND_JSON.read_text(encoding="utf-8")))
            except Exception:
                pass
    # Seed any playlist that has no saved copy yet.
    for series, (name, _) in PLAYLISTS.items():
        data["playlists"].setdefault(series, {"name": name, "description": ""})
    return data


def _image_info(path: Path) -> dict[str, Any]:
    role, recommended = _role_of(path.stem)
    info: dict[str, Any] = {
        "name": path.name,
        "role": role,
        "recommended": recommended,
        "size_kb": round(path.stat().st_size / 1024),
        "modified": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "dimensions": None,
    }
    try:
        from PIL import Image

        with Image.open(path) as im:
            info["dimensions"] = f"{im.width} × {im.height}"
    except Exception:
        pass
    return info


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    brand = load_brand()
    # Surface the effective "exists on YouTube" state, not just saved overrides,
    # so the toggle reflects reality on first load.
    for series, entry in brand["playlists"].items():
        entry.setdefault("created", playlist_of(series)[1])
    images = []
    if BRAND_DIR.exists():
        images = [_image_info(p) for p in sorted(BRAND_DIR.iterdir())
                  if p.suffix.lower() in IMAGE_EXTS]
    docs = []
    if BRAND_DIR.exists():
        for p in sorted(BRAND_DIR.glob("*.txt")):
            docs.append({"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)})
    return {**brand, "images": images, "docs": docs}


class SettingsReq(BaseModel):
    channel: dict[str, str] | None = None
    # values are str | bool ("created"), so keep this loose
    playlists: dict[str, dict[str, Any]] | None = None


@app.post("/api/settings")
def api_settings_save(req: SettingsReq) -> dict[str, Any]:
    if req.channel:
        store.brand_save_channel(req.channel.get("tagline"),
                                 req.channel.get("description"))
    if req.playlists:
        for series, vals in req.playlists.items():
            store.brand_save_playlist(
                series, vals.get("name"), vals.get("description"),
                vals.get("created") if "created" in vals else None)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# YouTube sync: pull live channel/playlist/video state, push local edits
# --------------------------------------------------------------------------- #
@app.post("/api/yt/sync")
def api_yt_sync() -> dict[str, Any]:
    """Pull from YouTube (~4 quota units) and return a local-vs-live diff."""
    from graph_bot.publish import channel_sync
    from graph_bot.publish.auth import AuthError

    try:
        remote = channel_sync.pull()
        d = channel_sync.diff(remote)
    except AuthError as exc:
        raise HTTPException(400, str(exc))
    return {
        "channel": {**remote["channel"], **d["channel"]},
        "playlists": d["playlists"],
        "videos": remote["videos"],
        "private": remote["private"],
        "adopted": remote["adopted"],
        "units_spent": remote["units_spent"],
        "fetched_at": store.now(),
    }


class YtPushReq(BaseModel):
    channel: bool = False
    playlists: list[str] = []


@app.post("/api/yt/push")
def api_yt_push(req: YtPushReq) -> dict[str, Any]:
    """Apply confirmed local edits to YouTube (50 quota units per item)."""
    from graph_bot.publish import channel_sync
    from graph_bot.publish.auth import AuthError

    if not req.channel and not req.playlists:
        raise HTTPException(400, "Nothing selected to push")
    try:
        result = channel_sync.push(req.channel, req.playlists)
    except AuthError as exc:
        raise HTTPException(400, str(exc))
    return result


@app.post("/api/queue/ai-review")
def api_queue_ai_review() -> dict[str, Any]:
    """Review of the formula-ranked top picks, fully local and free: rule
    checks always (stale series, long titles, repeated hooks, pending Private
    flips), plus judgment from the Ollama model in OLLAMA_MODEL when the local
    server is up — rules stand alone when it isn't. graph_bot/ai_review.py
    holds a dormant Claude-API version if hosted-model quality is ever wanted."""
    from graph_bot.queue_review import review

    state = api_state()
    picks = [p for p in state["next_up"] if not p.get("blocked")][:10]
    if not picks:
        raise HTTPException(400, "Nothing in the queue to review")
    return review(picks)


class AnalyticsSyncReq(BaseModel):
    days: int = 90


@app.post("/api/analytics/sync")
def api_analytics_sync(req: AnalyticsSyncReq) -> dict[str, Any]:
    """Pull daily analytics from the YouTube Analytics API (own quota pool,
    costs the upload pipeline nothing). Impressions/CTR still come only from
    Studio zip exports — the API does not serve them."""
    from graph_bot.analytics.api_sync import sync
    from graph_bot.publish.auth import AuthError

    try:
        return sync(days=max(7, min(365, req.days)))
    except AuthError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/yt/stats")
def api_yt_stats() -> dict[str, Any]:
    """Latest stored snapshots — no quota spent, safe to call on page load."""
    return {
        "channel": store.latest_channel_stats(),
        "videos": store.latest_video_stats(),
    }


@app.get("/api/brand/{name}")
def api_brand_image(name: str) -> FileResponse:
    path = (BRAND_DIR / name).resolve()
    if path.parent != BRAND_DIR.resolve() or not path.exists():
        raise HTTPException(404, "No such brand asset")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.post("/api/brand/upload")
async def api_brand_upload(name: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    """Replace (or add) a brand image. Existing files are backed up first."""
    safe = Path(name).name
    if Path(safe).suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(400, "Only png/jpg/webp images are allowed")
    dest = (BRAND_DIR / safe).resolve()
    if dest.parent != BRAND_DIR.resolve():
        raise HTTPException(400, "Invalid destination")
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():  # never silently destroy an existing asset
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BRAND_DIR / "_backup" / f"{dest.stem}-{stamp}{dest.suffix}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, backup)
    dest.write_bytes(await file.read())
    return {"ok": True, "image": _image_info(dest)}


# --------------------------------------------------------------------------- #
# Analytics warehouse (Postgres)
# --------------------------------------------------------------------------- #
def _analytics_payload() -> dict[str, Any]:
    """Everything the analytics screen needs, in one round trip.

    The warehouse is optional: the dashboard has to keep working when Postgres
    is down or was never configured, so every failure returns a reason instead
    of raising.
    """
    from graph_bot.db import NotConfigured, connect

    try:
        with connect() as conn:
            latest = conn.execute(
                "SELECT range_start, range_end, source, imported_at"
                " FROM analytics_import ORDER BY range_end DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                return {"available": False,
                        "reason": "No analytics imported yet. Run:"
                                  " python -m graph_bot.analytics import"}
            lo, hi, source, imported_at = latest

            # Channel figures come from YouTube's own "Total" row, never from
            # summing the per-video rows: unattributed views and subscribers
            # would otherwise vanish (49 videos sum to 14 subs against 72).
            totals = conn.execute(
                """
                SELECT views, watch_hours, subscribers, impressions, ctr_pct,
                       avg_view_sec, avg_pct_viewed
                FROM channel_period_stats WHERE range_start = %s AND range_end = %s
                """, (lo, hi)).fetchone()
            tracked = conn.execute(
                "SELECT count(*) FROM video_period_stats"
                " WHERE range_start = %s AND range_end = %s", (lo, hi)).fetchone()[0]

            by_series = conn.execute(
                """
                SELECT v.series, v.playlist, count(*) AS videos,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY p.views) AS median_views,
                       sum(p.views) AS total_views,
                       avg(p.ctr_pct) AS ctr,
                       CASE WHEN sum(p.views) > 0
                            THEN 1000.0 * sum(p.subscribers) / sum(p.views) END AS subs_per_1k
                FROM video_period_stats p JOIN video v USING (video_id)
                WHERE p.range_start = %s AND p.range_end = %s AND v.series IS NOT NULL
                GROUP BY v.series, v.playlist
                ORDER BY median_views DESC NULLS LAST
                """, (lo, hi)).fetchall()

            buckets = conn.execute(
                """
                SELECT CASE WHEN v.duration_sec <= 10 THEN '<=10s'
                            WHEN v.duration_sec < 30  THEN '11-29s'
                            ELSE '30s+' END AS bucket,
                       count(*),
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY p.views)
                FROM video_period_stats p JOIN video v USING (video_id)
                WHERE p.range_start = %s AND p.range_end = %s AND v.duration_sec IS NOT NULL
                GROUP BY 1
                """, (lo, hi)).fetchall()

            channel = conn.execute(
                "SELECT day, views FROM channel_daily_stats ORDER BY day"
            ).fetchall()

            top = conn.execute(
                """
                SELECT p.video_id, v.title, v.topic_key, v.series, v.playlist,
                       v.duration_sec, v.published_at, p.views, p.ctr_pct
                FROM video_period_stats p JOIN video v USING (video_id)
                WHERE p.range_start = %s AND p.range_end = %s
                ORDER BY p.views DESC NULLS LAST LIMIT 10
                """, (lo, hi)).fetchall()
    except NotConfigured as exc:
        return {"available": False, "reason": str(exc)}
    except Exception as exc:  # driver missing, server down, schema not created
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}".split(chr(10))[0]}

    order = {"<=10s": 0, "11-29s": 1, "30s+": 2}
    views, watch, subs, impressions, ctr, avg_sec, avg_pct = totals or (None,) * 7
    return {
        "available": True,
        "range": {"start": str(lo), "end": str(hi), "source": source,
                  "imported_at": imported_at.isoformat(timespec="seconds")},
        "totals": {
            "videos": tracked,
            "views": views,
            "watch_hours": round(float(watch), 1) if watch is not None else None,
            "subscribers": subs,
            "impressions": impressions,
            "ctr": round(float(ctr), 2) if ctr is not None else None,
            "avg_view_sec": avg_sec,
            "avg_pct_viewed": round(float(avg_pct), 1) if avg_pct is not None else None,
        },
        "by_series": [
            {"series": s, "playlist": pl, "videos": vids,
             "median_views": float(med) if med is not None else None,
             "total_views": tv,
             "ctr": round(float(c), 2) if c is not None else None,
             "subs_per_1k": round(float(sp), 2) if sp is not None else None}
            for s, pl, vids, med, tv, c, sp in by_series
        ],
        "length_buckets": sorted(
            [{"bucket": b, "videos": cnt,
              "median_views": float(med) if med is not None else None}
             for b, cnt, med in buckets],
            key=lambda x: order.get(x["bucket"], 9),
        ),
        "channel_daily": [{"day": str(d), "views": v} for d, v in channel],
        "top_videos": [
            {"video_id": vid, "title": title, "topic_key": key, "series": s,
             "playlist": pl, "duration_sec": dur,
             "published_at": str(pub) if pub else None, "views": views_,
             "ctr": round(float(c), 2) if c is not None else None}
            for vid, title, key, s, pl, dur, pub, views_, c in top
        ],
    }


# --------------------------------------------------------------------------- #
# Disk retention
# --------------------------------------------------------------------------- #
SETTINGS_YAML = CONFIG_DIR / "settings.yaml"


class RetentionPolicyReq(BaseModel):
    output_days_after_export: int
    export_days_after_upload: int
    stale_warn_days: int


def _write_policy(values: dict[str, int]) -> None:
    """Patch the three numbers in place.

    A yaml.dump round-trip would strip every comment in settings.yaml, and the
    comments there explain *why* the durations are measured from the lifecycle
    event rather than the folder date — that is the part worth keeping.
    """
    text = SETTINGS_YAML.read_text(encoding="utf-8")
    for key, value in values.items():
        pattern = re.compile(rf"^(\s*{key}\s*:\s*)(\d+)", re.M)
        if not pattern.search(text):
            raise HTTPException(500, f"settings.yaml has no '{key}' under retention:")
        text = pattern.sub(lambda m: f"{m.group(1)}{value}", text, count=1)
    yaml.safe_load(text)          # never write a file we cannot read back
    SETTINGS_YAML.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# YouTube upload
# --------------------------------------------------------------------------- #
class UploadRunner:
    """Runs a staged batch of uploads, one at a time, on a background thread.

    Sequential on purpose: uploading is the slow, quota-billed, outward-facing
    step, and a failure is usually systemic (expired token, wrong channel, quota
    gone) rather than specific to one video. So a run stops on the first failure
    instead of spending another 1,702 units proving the same point.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.current: str | None = None
        self.stage: str | None = None
        self.pct = 0
        self.stopped_reason: str | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"running": self.running, "current": self.current,
                    "stage": self.stage, "pct": self.pct,
                    "stopped_reason": self.stopped_reason}

    def _stop(self, reason: str) -> None:
        with self.lock:
            self.stopped_reason = reason

    def start(self) -> dict[str, Any]:
        from graph_bot.publish import upload as up

        with self.lock:
            if self.running:
                raise HTTPException(409, "An upload run is already in progress")
            self.running, self.stopped_reason = True, None

        queued = [b for b in store.batch_load() if b["state"] in ("queued", "failed")]
        if not queued:
            with self.lock:
                self.running = False
            raise HTTPException(400, "Nothing staged to upload")

        def run() -> None:
            try:
                for item in queued:
                    key = item["key"]
                    if store.quota_status()["slots_left"] < 1:
                        self._stop("Daily API quota is spent - try again after the Pacific reset")
                        return
                    with self.lock:
                        self.current, self.stage, self.pct = key, "starting", 0
                    store.batch_update(key, state="running", stage="starting", pct=0, error=None)

                    def progress(pct: int, stage: str, _k=key) -> None:
                        with self.lock:
                            self.stage, self.pct = stage, pct
                        store.batch_update(_k, stage=stage, pct=pct)

                    try:
                        r = up.upload(key, on_progress=progress)
                    except Exception as exc:
                        msg = str(exc).splitlines()[0]
                        store.batch_update(key, state="failed", stage="failed", error=msg)
                        self._stop(f"{key}: {msg}")
                        return
                    # Billed only for an upload that actually happened.
                    store.record_upload_units()
                    store.batch_update(key, state="done", stage="done", pct=100,
                                       url=r["url"], warnings=r["warnings"])
            finally:
                with self.lock:
                    self.running, self.current, self.stage = False, None, None

        threading.Thread(target=run, daemon=True).start()
        return self.snapshot()


runner = UploadRunner()


class BatchReq(BaseModel):
    key: str


def _preflight() -> dict[str, Any]:
    """Everything that would make a run fail, checked before spending quota."""
    from graph_bot.publish import upload as up
    from graph_bot.publish.auth import token_info, whoami

    checks: list[dict[str, Any]] = []
    info = token_info()
    auth_ok = bool(info.get("present")) and not info.get("needs_reauth")
    checks.append({
        "name": "YouTube authorisation", "ok": auth_ok,
        "detail": "valid" if auth_ok else (
            info.get("reason") or "expired or missing scopes - run: python -m graph_bot.publish.auth"),
    })

    channel_ok, channel_detail = False, "skipped - not authorised"
    if auth_ok:
        try:
            me = whoami()
            channel_ok = me["matches"]
            channel_detail = me["title"] if me["matches"] else (
                f"WRONG: {me['title']} - expected {me['expected_name']}")
        except Exception as exc:
            channel_detail = str(exc).splitlines()[0]
    checks.append({"name": "Upload channel", "ok": channel_ok, "detail": channel_detail})

    missing = []
    for b in store.batch_load():
        if b["state"] == "done":
            continue
        try:
            up.read_export(up.find_export(b["key"]))
        except Exception as exc:
            missing.append(f"{b['key']}: {exc}")
    checks.append({"name": "Export files", "ok": not missing,
                   "detail": "all present" if not missing else "; ".join(missing[:3])})

    q = store.quota_status()
    pending = sum(1 for b in store.batch_load() if b["state"] in ("queued", "failed"))
    checks.append({"name": "Daily quota", "ok": q["slots_left"] >= pending,
                   "detail": f"{q['slots_left']} slot(s) left, {pending} staged"})
    return {"checks": checks, "ok": all(c["ok"] for c in checks)}


@app.get("/api/upload/auth")
def api_upload_auth() -> dict[str, Any]:
    """Is YouTube authorisation usable right now? Never opens a browser."""
    from graph_bot.publish.auth import token_info

    info = token_info()
    return {**info, "hint": ("Run:  python -m graph_bot.publish.auth"
                             if info.get("needs_reauth", True) else None)}


@app.get("/api/upload/batch")
def api_upload_batch() -> dict[str, Any]:
    topics = {t["key"]: t for t in load_topics()}
    exported = _exported_keys()
    items = []
    for b in store.batch_load():
        topic = topics.get(b["key"], {})
        series = topic_series(topic) if topic else None
        rel = exported.get(b["key"])
        size = 0
        if rel:
            v = PROJECT_ROOT / rel / "video.mp4"
            size = v.stat().st_size if v.exists() else 0
        items.append({**b, "title": topic.get("title", b["key"]), "series": series,
                      "playlist": playlist_of(series)[0] if series else None,
                      "bytes": size,
                      "has_thumb": bool(rel and (PROJECT_ROOT / rel / "thumbnail.jpg").exists())})
    return {"batch": items, "quota": store.quota_status(), "run": runner.snapshot()}


@app.get("/api/upload/preflight")
def api_upload_preflight() -> dict[str, Any]:
    return _preflight()


@app.post("/api/upload/batch/add")
def api_batch_add(req: BatchReq) -> dict[str, Any]:
    if req.key not in {t["key"] for t in load_topics()}:
        raise HTTPException(400, f"Unknown topic: {req.key}")
    if req.key in load_log():
        raise HTTPException(400, f"'{req.key}' is already marked uploaded")
    if not _exported_keys().get(req.key):
        raise HTTPException(400, f"'{req.key}' has no export folder")
    q = store.quota_status()
    staged = sum(1 for b in store.batch_load() if b["state"] in ("queued", "failed"))
    if staged >= q["slots_left"]:
        raise HTTPException(
            400,
            f"Only {q['slots_left']} upload slot(s) left today "
            f"({q['uploads_today']} of {q['slots_total']} used). "
            "The quota resets at midnight US Pacific.")
    store.batch_add(req.key)
    return {"ok": True}


@app.post("/api/upload/batch/remove")
def api_batch_remove(req: BatchReq) -> dict[str, Any]:
    store.batch_remove(req.key)
    return {"ok": True}


@app.post("/api/upload/batch/clear")
def api_batch_clear() -> dict[str, Any]:
    return {"ok": True, "removed": store.batch_clear(done_only=True)}


@app.post("/api/upload/batch/run")
def api_batch_run() -> dict[str, Any]:
    pre = _preflight()
    if not pre["ok"]:
        failed = [c["name"] for c in pre["checks"] if not c["ok"]]
        raise HTTPException(400, f"Preflight failed: {', '.join(failed)}")
    return runner.start()


@app.get("/api/retention")
def api_retention() -> dict[str, Any]:
    """Dry-run plan plus the recent run history. Never deletes anything."""
    from graph_bot import retention

    try:
        plan = retention.plan()
        runs = [
            {"id": rid, "ran_at": ran_at.isoformat(timespec="seconds"), "dry_run": dry,
             "output_purged": op, "export_purged": ep, "bytes_freed": freed}
            for rid, ran_at, dry, op, ep, freed in store.retention_runs(5)
        ]
    except Exception as exc:
        return {"available": False,
                "reason": f"{type(exc).__name__}: {exc}".splitlines()[0]}
    return {"available": True, **plan, "runs": runs}


@app.post("/api/retention/policy")
def api_retention_policy(req: RetentionPolicyReq) -> dict[str, Any]:
    for name, value in req.model_dump().items():
        if not 0 <= value <= 3650:
            raise HTTPException(400, f"{name} must be between 0 and 3650 days")
    _write_policy(req.model_dump())
    return {"ok": True, **req.model_dump()}


@app.post("/api/retention/apply")
def api_retention_apply() -> dict[str, Any]:
    """Actually delete. The UI confirms with the real list first."""
    from graph_bot import retention

    r = retention.apply()
    return {
        "ok": True,
        "run_id": r["run_id"],
        "deleted": len(r["deleted"]),
        "freed": r["freed"],
        "output_purged": sum(1 for d in r["deleted"] if d["kind"] == "output"),
        "export_purged": sum(1 for d in r["deleted"] if d["kind"] == "export"),
    }


@app.get("/api/analytics")
def api_analytics() -> dict[str, Any]:
    return _analytics_payload()


@app.get("/api/uploads")
def api_uploads() -> dict[str, Any]:
    """Everything marked uploaded, newest first, with its details and link."""
    log = load_log()
    exported = _exported_keys()
    meta_by_key: dict[str, dict[str, Any]] = {}
    for key, (_, path) in _latest_renders().items():
        try:
            meta_by_key[key] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Live counts from the last YouTube sync, keyed back to topics by video id.
    live: dict[str, dict[str, Any]] = {}
    try:
        from graph_bot.analytics.importer import VIDEO_ID_RE

        by_id = store.latest_video_stats()
        for key, entry in log.items():
            m = VIDEO_ID_RE.search(entry.get("url") or "")
            if m and m.group(1) in by_id:
                live[key] = by_id[m.group(1)]
    except Exception:
        pass

    rows = []
    for t in load_topics():
        key = t["key"]
        entry = log.get(key)
        if not entry:
            continue
        series = topic_series(t)
        meta = meta_by_key.get(key, {})
        rel = exported.get(key)
        rows.append({
            "key": key,
            "title": t.get("title", ""),
            "subtitle": t.get("subtitle", ""),
            "series": series,
            "playlist": playlist_of(series)[0],
            "episode": topic_episode(t),
            "uploaded_at": entry.get("uploaded_at"),
            "url": entry.get("url"),
            "duration_sec": meta.get("duration_sec"),
            "source": t.get("source") or meta.get("source"),
            "rendered_on": (meta.get("generated_at") or "")[:10] or None,
            "exported": rel,
            "has_thumb": bool(rel and (PROJECT_ROOT / rel / "thumbnail.jpg").exists()),
            "live": live.get(key),
        })

    rows.sort(key=lambda r: (r["uploaded_at"] or ""), reverse=True)
    return {
        "uploads": rows,
        "total": len(rows),
        "with_link": sum(1 for r in rows if r["url"]),
    }


class LinkReq(BaseModel):
    key: str
    url: str | None = None


@app.post("/api/upload-link")
def api_upload_link(req: LinkReq) -> dict[str, Any]:
    """Set or clear the YouTube link on an already-uploaded topic."""
    if not store.set_link(req.key, req.url):
        raise HTTPException(404, f"'{req.key}' is not marked uploaded")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Music library
# --------------------------------------------------------------------------- #
MUSIC_DIR = PROJECT_ROOT / "assets" / "music"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
MOODS = ["calm", "hopeful", "reflective", "majestic", "serene", "lofi"]


@app.get("/api/music")
def api_music() -> dict[str, Any]:
    """Tracks in assets/music, grouped by mood folder."""
    from graph_bot import audio as audio_mod

    settings = load_settings()
    groups: dict[str, list[dict[str, Any]]] = {m: [] for m in MOODS}
    groups["untagged"] = []

    if MUSIC_DIR.exists():
        for path in sorted(MUSIC_DIR.rglob("*")):
            if path.suffix.lower() not in AUDIO_EXTS:
                continue
            rel = path.relative_to(MUSIC_DIR)
            mood = rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in MOODS else "untagged"
            try:
                secs = audio_mod._track_duration(path, settings)
            except Exception:
                secs = None
            groups[mood].append({
                "name": path.name,
                "rel": str(rel).replace("\\", "/"),
                "mood": mood,
                "size_kb": round(path.stat().st_size / 1024),
                "duration_sec": round(secs, 1) if secs else None,
                "synth": path.stem.endswith(("-30s", "-40s")) and path.suffix == ".wav",
            })

    conf = settings.get("audio", {}) or {}
    return {
        "moods": MOODS,
        "groups": groups,
        "total": sum(len(v) for v in groups.values()),
        "source": conf.get("source", "generate"),
        "enabled": bool(conf.get("enabled", False)),
    }


@app.post("/api/music/upload")
async def api_music_upload(mood: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    """Add a track to assets/music/<mood>/ (your own royalty-free files only)."""
    if mood not in MOODS:
        raise HTTPException(400, f"Unknown mood '{mood}'. Use one of: {', '.join(MOODS)}")
    safe = Path(file.filename or "").name
    if not safe or Path(safe).suffix.lower() not in AUDIO_EXTS:
        raise HTTPException(400, "Audio files only (mp3, wav, m4a, aac, ogg, flac, opus)")
    dest_dir = MUSIC_DIR / mood
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    if dest.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"{Path(safe).stem}-{stamp}{Path(safe).suffix}"
    dest.write_bytes(await file.read())
    return {"ok": True, "saved": str(dest.relative_to(MUSIC_DIR)).replace("\\", "/")}


class MusicDelReq(BaseModel):
    rel: str


@app.post("/api/music/delete")
def api_music_delete(req: MusicDelReq) -> dict[str, Any]:
    """Remove a track. Moves it to assets/music/_removed/ rather than erasing it."""
    target = (MUSIC_DIR / req.rel).resolve()
    if not str(target).startswith(str(MUSIC_DIR.resolve())) or not target.exists():
        raise HTTPException(404, "No such track")
    bin_dir = MUSIC_DIR / "_removed"
    bin_dir.mkdir(parents=True, exist_ok=True)
    dest = bin_dir / target.name
    if dest.exists():
        dest = bin_dir / f"{target.stem}-{dt.datetime.now():%Y%m%d-%H%M%S}{target.suffix}"
    shutil.move(str(target), str(dest))
    return {"ok": True, "moved_to": str(dest.relative_to(PROJECT_ROOT))}


@app.get("/api/music/play/{rel:path}")
def api_music_play(rel: str) -> FileResponse:
    target = (MUSIC_DIR / rel).resolve()
    if not str(target).startswith(str(MUSIC_DIR.resolve())) or not target.exists():
        raise HTTPException(404, "No such track")
    return FileResponse(target)


# --------------------------------------------------------------------------- #
# New topics
# --------------------------------------------------------------------------- #
class NewTopicReq(BaseModel):
    key: str
    title: str
    subtitle: str = ""
    fetcher: str
    mode: str = "bar_race"
    series: str | None = None
    source: str = ""
    code: str | None = None       # worldbank indicator
    slug: str | None = None       # owid grapher slug
    url: str | None = None        # csv_url
    file: str | None = None       # curated_csv
    unit: str | None = None
    unit_suffix: str | None = None
    value_scale: float | None = None
    mood: str | None = None
    hashtags: list[str] = []


REQUIRED_BY_FETCHER = {
    "worldbank": "code", "owid": "slug", "csv_url": "url", "curated_csv": "file",
}

# Order fields are written in, so generated blocks read like the hand-written ones.
# Only an ordering — fields not listed here are still written, after these.
_FIELD_ORDER = [
    "key", "title", "subtitle", "fetcher", "code", "slug", "url", "file",
    "agg", "mode", "scene", "entities", "entity_filter", "years_window",
    "series", "source", "unit", "unit_suffix", "value_scale",
    "value_decimals", "value_fmt", "top_n", "flags", "mood",
]


def _check_mode_fields(topic: dict[str, Any]) -> None:
    """Reject topics the renderer would fail on, before they reach topics.yaml."""
    from graph_bot.scenes import SCENES

    mode, key = topic.get("mode"), topic.get("key")
    if mode == "manim" and topic.get("scene") not in SCENES:
        raise HTTPException(400, f"'{key}': mode 'manim' needs a `scene:` from {', '.join(SCENES)}")
    if mode == "line_multi" and not topic.get("entities"):
        raise HTTPException(400, f"'{key}': mode 'line_multi' needs an `entities:` list")


def _append_topic_block(topic: dict[str, Any]) -> int:
    """Append one topic to config/topics.yaml, validating before writing."""
    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            if float(v).is_integer():
                return str(int(v))
            # PyYAML only reads exponent floats with a dot ("1.0e-06", not "1e-06").
            mant, _, exp = repr(float(v)).partition("e")
            return f"{mant if '.' in mant else mant + '.0'}{'e' + exp if exp else ''}"
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)  # JSON is valid YAML flow style
        return '"' + str(v).replace('"', '\\"') + '"'

    _check_mode_fields(topic)
    tags = [str(t).strip().lstrip("#") for t in (topic.get("hashtags") or []) if str(t).strip()]
    fields = {k: v for k, v in topic.items() if k != "hashtags" and v not in (None, "", [], {})}
    rank = {k: i for i, k in enumerate(_FIELD_ORDER)}
    ordered = sorted(fields.items(), key=lambda kv: rank.get(kv[0], len(rank)))
    lines = [f"\n  # added via dashboard {dt.date.today().isoformat()}"]
    lines.append(f"  - {ordered[0][0]}: {fmt(ordered[0][1])}")
    lines += [f"    {k}: {fmt(v)}" for k, v in ordered[1:]]
    if tags:
        lines.append("    hashtags: " + fmt(tags))

    path = CONFIG_DIR / "topics.yaml"
    updated = path.read_text(encoding="utf-8").rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    try:
        parsed = yaml.safe_load(updated)
        keys = [t.get("key") for t in parsed.get("topics", [])]
        written = next((t for t in parsed["topics"] if t.get("key") == topic["key"]), None)
        if written is None:
            raise ValueError("new topic did not parse into the catalog")
        # A field that silently fails to round-trip yields a topic that renders
        # wrong (or not at all), so compare every field, not just the key.
        expected = {**fields, **({"hashtags": tags} if tags else {})}
        if written != expected:
            raise ValueError(f"topic did not round-trip: wrote {written}, expected {expected}")
    except Exception as exc:
        raise HTTPException(500, f"Refusing to write invalid YAML: {exc}")
    path.write_text(updated, encoding="utf-8")
    return len(keys)


@app.post("/api/topics")
def api_create_topic(req: NewTopicReq) -> dict[str, Any]:
    """Append a new topic block to config/topics.yaml."""
    key = req.key.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9_]+", key or ""):
        raise HTTPException(400, "Key must be lowercase letters, numbers and underscores")
    if any(t.get("key") == key for t in load_topics()):
        raise HTTPException(400, f"Topic '{key}' already exists")
    if not req.title.strip():
        raise HTTPException(400, "Title is required")

    need = REQUIRED_BY_FETCHER.get(req.fetcher)
    if need and not getattr(req, need, None):
        raise HTTPException(400, f"'{req.fetcher}' needs a {need}")

    topic = {
        "key": key, "title": req.title.strip(), "subtitle": req.subtitle.strip(),
        "fetcher": req.fetcher, "code": req.code, "slug": req.slug,
        "url": req.url, "file": req.file, "mode": req.mode, "series": req.series,
        "source": req.source.strip(), "unit": req.unit,
        "unit_suffix": req.unit_suffix, "value_scale": req.value_scale,
        "mood": req.mood, "hashtags": req.hashtags,
    }
    total = _append_topic_block(topic)
    return {"ok": True, "key": key, "total": total}


# --------------------------------------------------------------------------- #
# Topic ideas — the dashboard proposes what to build next
# --------------------------------------------------------------------------- #
# Every entry is a complete, ready-to-render topic block. The indicator codes
# were each verified against the live World Bank API before being listed here;
# `/api/ideas/verify` re-checks one on demand so a dead source is caught before
# a render is queued rather than after.
IDEAS: list[dict[str, Any]] = [
    # ===================== SPORTS IN DATA =====================
    # Best pillar in the 2026-08-27 export: 4.37% CTR vs 2.52% channel, and
    # "Most World Cup Titles" took 1,058 views on day one.
    {
        "id": "cricket_test_wins",
        "reason": "Sports has the channel's best CTR by far (4.4% vs 2.5%). Test "
                  "cricket is the format the playlist is still missing.",
        "topic": {
            "key": "cricket_test_wins", "title": "Who Wins the Most Test Matches?",
            "subtitle": "Cumulative Test wins", "fetcher": "cricsheet",
            "url": "https://cricsheet.org/downloads/tests_male_csv2.zip",
            "agg": "cumcount", "mode": "bump_race", "top_n": 8, "series": "sports",
            "source": "Cricsheet (ODC-BY)", "mood": "majestic",
            "hashtags": ["cricket", "testcricket", "sports"],
        },
    },
    {
        "id": "cricket_women_t20",
        "reason": "England leads Australia 132-121 with India third — but the "
                  "order has only changed hands once since 2009, so cut it as a "
                  "chase, not a see-saw.",
        "topic": {
            "key": "cricket_women_t20_wins", "title": "Who Wins the Most Women's T20s?",
            "subtitle": "Cumulative T20 international wins", "fetcher": "cricsheet",
            "url": "https://cricsheet.org/downloads/t20s_female_csv2.zip",
            "agg": "cumcount", "mode": "bump_race", "top_n": 8, "series": "sports",
            "source": "Cricsheet (ODC-BY)", "mood": "majestic",
            "hashtags": ["cricket", "womenscricket", "sports"],
        },
    },
    {
        "id": "cricket_women_odi",
        "reason": "Same proven sports engine, an audience nobody else animates.",
        "topic": {
            "key": "cricket_women_odi_wins", "title": "Who Wins the Most Women's ODIs?",
            "subtitle": "Cumulative wins", "fetcher": "cricsheet",
            "url": "https://cricsheet.org/downloads/odis_female_csv2.zip",
            "agg": "cumcount", "mode": "bar_race", "top_n": 10, "series": "sports",
            "source": "Cricsheet (ODC-BY)", "mood": "majestic",
            "hashtags": ["cricket", "womenscricket", "sports"],
        },
    },
    {
        "id": "cricket_bbl",
        "reason": "IPL was your strongest sports launch — Big Bash is the same "
                  "franchise-rivalry format for a second cricket market.",
        "topic": {
            "key": "cricket_bbl_wins", "title": "Big Bash: Who Actually Dominates?",
            "subtitle": "Cumulative BBL wins", "fetcher": "cricsheet",
            "url": "https://cricsheet.org/downloads/bbl_male_csv2.zip",
            "agg": "cumcount", "mode": "bar_race", "top_n": 8, "series": "sports",
            "source": "Cricsheet (ODC-BY)", "flags": False, "mood": "majestic",
            "hashtags": ["cricket", "bigbash", "sports"],
        },
    },
    {
        "id": "cricket_psl",
        "reason": "Franchise cricket again, and PSL rankings are tight enough that "
                  "the order keeps flipping.",
        "topic": {
            "key": "cricket_psl_wins", "title": "PSL's Winningest Teams",
            "subtitle": "Cumulative PSL wins", "fetcher": "cricsheet",
            "url": "https://cricsheet.org/downloads/psl_male_csv2.zip",
            "agg": "cumcount", "mode": "bump_race", "top_n": 6, "series": "sports",
            "source": "Cricsheet (ODC-BY)", "flags": False, "mood": "majestic",
            "hashtags": ["cricket", "psl", "sports"],
        },
    },

    # ===================== WORLD IN DATA =====================
    # The workhorse: 603 median views at 3.21% CTR across 8 videos.
    {
        "id": "under5_mortality",
        "reason": "The strongest good-news dataset there is, and the same shape as "
                  "your 'Extreme Poverty Is Falling' video.",
        "topic": {
            "key": "child_mortality", "title": "Child Deaths Have Collapsed",
            "subtitle": "Deaths per 1,000 children under 5", "fetcher": "worldbank",
            "code": "SH.DYN.MORT", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank / UN IGME", "value_decimals": 1,
            "mood": "hopeful", "hashtags": ["health", "children", "progress"],
        },
    },
    {
        "id": "electricity_access",
        "reason": "A bounded share that begs to be drawn as 100 dots rather than "
                  "bars — and it pairs with your best-retaining electricity video.",
        "topic": {
            "key": "electricity_access", "title": "The World Got Electricity",
            "subtitle": "Share of people with access, India", "fetcher": "worldbank",
            "code": "EG.ELC.ACCS.ZS", "mode": "waffle_grow", "series": "world_in_data",
            "entity_filter": "India", "source": "World Bank", "unit_suffix": "%",
            "value_decimals": 0, "flags": False, "mood": "hopeful",
            "hashtags": ["energy", "electricity", "progress"],
        },
    },
    {
        "id": "internet_users",
        "reason": "Your two internet videos both landed well; this is the global "
                  "ranking version of that story.",
        "topic": {
            "key": "internet_users", "title": "Who Is Actually Online?",
            "subtitle": "Share of people using the internet", "fetcher": "worldbank",
            "code": "IT.NET.USER.ZS", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank / ITU", "unit_suffix": "%", "value_decimals": 1,
            "mood": "lofi", "hashtags": ["internet", "tech", "worldstats"],
        },
    },
    {
        "id": "renewable_electricity",
        "reason": "Your electricity video hit 754 views at 38% viewed — the best "
                  "retention in World in Data. This is its natural sequel.",
        "topic": {
            "key": "renewable_electricity", "title": "Who Runs on Renewables?",
            "subtitle": "Renewable share of electricity", "fetcher": "worldbank",
            "code": "EG.ELC.RNEW.ZS", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank", "unit_suffix": "%", "value_decimals": 1,
            "mood": "hopeful", "hashtags": ["renewables", "energy", "climate"],
        },
    },
    {
        "id": "energy_per_capita",
        "reason": "Per-person cuts flip rankings — exactly what your per-capita CO2 "
                  "video did.",
        "topic": {
            "key": "energy_per_capita", "title": "Who Uses the Most Energy?",
            "subtitle": "Energy use per person", "fetcher": "worldbank",
            "code": "EG.USE.PCAP.KG.OE", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank", "unit": "kg oil equivalent",
            "mood": "reflective", "hashtags": ["energy", "percapita", "worldstats"],
        },
    },
    {
        "id": "female_life",
        "reason": "Life Expectancy is already one of your better performers; the "
                  "women-only cut has a sharper hook.",
        "topic": {
            "key": "female_life_expectancy", "title": "Where Women Live Longest",
            "subtitle": "Female life expectancy at birth", "fetcher": "worldbank",
            "code": "SP.DYN.LE00.FE.IN", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank", "unit": "years", "value_decimals": 1, "top_n": 12,
            "mood": "calm", "hashtags": ["health", "lifeexpectancy", "women"],
        },
    },
    {
        "id": "female_labour",
        "reason": "A ranking that overturns assumptions — the countries at the top "
                  "are not the ones people guess.",
        "topic": {
            "key": "female_labour_force", "title": "Where Do Women Work Most?",
            "subtitle": "Female labour force participation", "fetcher": "worldbank",
            "code": "SL.TLF.CACT.FE.ZS", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank / ILO", "unit_suffix": "%", "value_decimals": 1,
            "mood": "hopeful", "hashtags": ["women", "work", "worldstats"],
        },
    },
    {
        "id": "rail_network",
        "reason": "Infrastructure nobody animates, and the top of the table is a "
                  "genuine surprise.",
        "topic": {
            "key": "rail_network", "title": "The World's Biggest Rail Networks",
            "subtitle": "Total rail lines", "fetcher": "worldbank",
            "code": "IS.RRS.TOTL.KM", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank", "unit": "km", "value_fmt": "integer",
            "mood": "majestic", "hashtags": ["rail", "infrastructure", "worldstats"],
        },
    },
    {
        "id": "literacy_rate",
        "reason": "Another good-news curve with a clear, climbing shape.",
        "topic": {
            "key": "literacy_rate", "title": "The World Learned to Read",
            "subtitle": "Adult literacy rate", "fetcher": "worldbank",
            "code": "SE.ADT.LITR.ZS", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank / UNESCO", "unit_suffix": "%", "value_decimals": 1,
            "mood": "hopeful", "hashtags": ["literacy", "education", "progress"],
        },
    },

    # ===================== MONEY & COST OF LIVING =====================
    # Mid-pack (251 median views, 1.99% CTR) but proven — worth topping up,
    # not expanding hard.
    {
        "id": "gdp_per_capita_ppp",
        "reason": "Your richest-per-person video is a proven format; PPP changes "
                  "the answer, which is the whole hook.",
        "topic": {
            "key": "money_real_income", "title": "Who's Actually Richest?",
            "subtitle": "GDP per person, adjusted for what money buys",
            "fetcher": "worldbank", "code": "NY.GDP.PCAP.PP.CD", "mode": "bar_race",
            "series": "money", "source": "World Bank", "value_fmt": "integer",
            "unit": "USD", "mood": "majestic",
            "hashtags": ["money", "economy", "percapita"],
        },
    },
    {
        "id": "govt_debt",
        "reason": "Debt rankings churn constantly, so the overtakes carry the "
                  "video — a natural fit for the rank-race format.",
        "topic": {
            "key": "money_government_debt", "title": "Who Owes the Most?",
            "subtitle": "Government debt as a share of GDP", "fetcher": "worldbank",
            "code": "GC.DOD.TOTL.GD.ZS", "mode": "bump_race", "top_n": 10,
            "series": "money", "source": "World Bank / IMF", "unit_suffix": "%",
            "value_decimals": 1, "mood": "reflective",
            "hashtags": ["debt", "economy", "money"],
        },
    },
    {
        "id": "tax_revenue",
        "reason": "Everyone has an opinion about tax; almost nobody has seen the "
                  "actual ranking.",
        "topic": {
            "key": "money_tax_revenue", "title": "Which Countries Tax the Most?",
            "subtitle": "Tax revenue as a share of GDP", "fetcher": "worldbank",
            "code": "GC.TAX.TOTL.GD.ZS", "mode": "bar_race", "series": "money",
            "source": "World Bank / IMF", "unit_suffix": "%", "value_decimals": 1,
            "mood": "reflective", "hashtags": ["tax", "economy", "money"],
        },
    },
    {
        "id": "health_spending",
        "reason": "Money's last big unexplored question.",
        "topic": {
            "key": "money_health_spending", "title": "Who Spends Most on Health?",
            "subtitle": "Health spending as a share of GDP", "fetcher": "worldbank",
            "code": "SH.XPD.CHEX.GD.ZS", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit_suffix": "%", "value_decimals": 1,
            "mood": "reflective", "hashtags": ["health", "spending", "economy"],
        },
    },
    {
        "id": "exports_share",
        "reason": "Completes 'Biggest Exporters' by showing which economies actually "
                  "depend on trade.",
        "topic": {
            "key": "money_trade_dependence", "title": "Which Economies Live on Trade?",
            "subtitle": "Exports as a share of GDP", "fetcher": "worldbank",
            "code": "NE.EXP.GNFS.ZS", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit_suffix": "%", "value_decimals": 1,
            "mood": "majestic", "hashtags": ["trade", "exports", "economy"],
        },
    },

    # ===================== INDIA IN DATA =====================
    # Second-best reach (48.8 views/day) but the worst retention at 17% — the
    # head-to-head framing is what holds people, so lead with rivalries.
    {
        "id": "india_china_urban",
        "reason": "Your India-vs-China videos are the pillar's best; this is the "
                  "one comparison you haven't drawn yet.",
        "topic": {
            "key": "india_vs_china_urban", "title": "India vs China: Moving to the Cities",
            "subtitle": "Share of people living in cities", "fetcher": "worldbank",
            "code": "SP.URB.TOTL.IN.ZS", "mode": "line_multi",
            "entities": ["India", "China"], "years_window": 50, "series": "india_in_data",
            "source": "World Bank", "unit_suffix": "%", "value_decimals": 1,
            "mood": "reflective", "hashtags": ["india", "china", "cities"],
        },
    },
    {
        "id": "india_china_child",
        "reason": "The same rivalry format on a statistic with a genuinely moving "
                  "payoff.",
        "topic": {
            "key": "india_vs_china_child_mortality",
            "title": "India vs China: Child Survival",
            "subtitle": "Deaths per 1,000 children under 5", "fetcher": "worldbank",
            "code": "SH.DYN.MORT", "mode": "line_multi",
            "entities": ["India", "China"], "years_window": 50, "series": "india_in_data",
            "source": "World Bank / UN IGME", "value_decimals": 1,
            "mood": "hopeful", "hashtags": ["india", "china", "health"],
        },
    },
    {
        "id": "india_power",
        "reason": "India went from half-connected to universal power in 30 years — "
                  "drawn as 100 dots, that lands harder than any axis.",
        "topic": {
            "key": "india_electricity_access", "title": "How India Got Power",
            "subtitle": "Share of Indians with electricity", "fetcher": "worldbank",
            "code": "EG.ELC.ACCS.ZS", "mode": "waffle_grow", "entity_filter": "India",
            "series": "india_in_data", "source": "World Bank", "unit_suffix": "%",
            "value_decimals": 0, "flags": False, "mood": "hopeful",
            "hashtags": ["india", "electricity", "progress"],
        },
    },
    # ===================== AI & COMPUTE =====================
    # The channel's biggest pillar (18 published videos) had no Build Next
    # entries at all, and it owns the best short-form retention on the channel:
    # the sub-10s AI topics run 32-61% where the 26s default runs ~24%
    # (docs/CONTENT_STRATEGY.md, findings 3-4). These are paced to ~9s with a
    # per-topic `seconds_per_year` instead of inheriting the 24s default.
    {
        "id": "ai_gpu_count",
        "reason": "200,000 GPUs trained Grok 4. The number IS the hook — which is "
                  "what every high-CTR title on this channel has in common.",
        "topic": {
            "key": "ai_gpu_count", "title": "How Many GPUs to Train One AI?",
            "subtitle": "Most GPUs used for a single training run",
            "fetcher": "csv_url", "url": "https://epoch.ai/data/notable_ai_models.csv",
            "date_col": "Publication date", "value_col": "Hardware quantity",
            "entity_label": "Most GPUs", "agg": "cummax",
            "year_min": 2016, "year_max": 2026, "years_window": 20,
            "seconds_per_year": 0.9, "mode": "line_grow", "log_scale": True,
            "value_fmt": "integer", "series": "ai_trends",
            "source": "Epoch AI (CC BY)", "mood": "hopeful",
            "hashtags": ["ai", "gpu", "nvidia"],
        },
    },
    {
        "id": "ai_cluster_cost",
        "reason": "The priciest AI cluster on record cost $7.1 BILLION in hardware. "
                  "Money plus a superlative is the channel's best-performing shape.",
        "topic": {
            "key": "ai_cluster_cost", "title": "The Most Expensive Computer Ever Built",
            "subtitle": "Priciest AI cluster hardware",
            "fetcher": "csv_url", "url": "https://epoch.ai/data/gpu_clusters.csv",
            "date_col": "First Operational Date", "value_col": "Hardware Cost",
            "entity_label": "Most expensive", "agg": "cummax",
            "year_min": 2016, "year_max": 2025, "years_window": 15,
            "seconds_per_year": 0.9, "mode": "line_grow", "log_scale": True,
            "value_scale": 1000000000, "unit_suffix": "B", "series": "ai_trends",
            "source": "Epoch AI (CC BY)", "mood": "reflective",
            "hashtags": ["ai", "datacenter", "money"],
        },
    },
    {
        "id": "ai_cluster_chips",
        "reason": "xAI's Colossus runs 230,000 chips in one building. Same size-shock "
                  "shape as 'How BIG Are AI Models?' (3.44% CTR, 34.9% retention).",
        "topic": {
            "key": "ai_cluster_chips", "title": "The Biggest AI Supercomputer",
            "subtitle": "Most AI chips in a single cluster",
            "fetcher": "csv_url", "url": "https://epoch.ai/data/gpu_clusters.csv",
            "date_col": "First Operational Date", "value_col": "Total number of AI chips",
            "entity_label": "Biggest cluster", "agg": "cummax",
            "year_min": 2015, "year_max": 2025, "years_window": 15,
            "seconds_per_year": 0.9, "mode": "line_grow",
            "value_fmt": "integer", "series": "ai_trends",
            "source": "Epoch AI (CC BY)", "mood": "hopeful",
            "hashtags": ["ai", "supercomputer", "nvidia"],
        },
    },
    {
        "id": "ai_open_vs_closed",
        "reason": "A real two-sided race: 455 closed models vs 338 open-weight ones, "
                  "and the gap is closing. Rivalry titles are the channel's top CTR "
                  "pattern (India vs China, 4.72%) — this is the AI version.",
        "topic": {
            "key": "ai_open_vs_closed", "title": "Open vs Closed: Who's Winning AI?",
            "subtitle": "Notable models released, cumulative",
            "fetcher": "csv_url", "url": "https://epoch.ai/data/notable_ai_models.csv",
            "date_col": "Publication date", "entity_col": "Open model weights?",
            "entity_map": {"Yes": "Open weights", "No": "Closed"},
            "entities": ["Open weights", "Closed"], "agg": "cumcount",
            "year_min": 2015, "year_max": 2026, "years_window": 15,
            "seconds_per_year": 0.9, "mode": "line_multi",
            "value_fmt": "integer", "series": "ai_trends",
            "source": "Epoch AI (CC BY)", "mood": "lofi",
            "hashtags": ["ai", "opensource", "technology"],
        },
    },
    {
        "id": "ai_training_time",
        "reason": "The longest single training run on record is 7,104 hours — 296 "
                  "days of nonstop compute for one model.",
        "topic": {
            "key": "ai_training_time", "title": "How Long Does Training an AI Take?",
            "subtitle": "Longest single training run (hours)",
            "fetcher": "csv_url", "url": "https://epoch.ai/data/notable_ai_models.csv",
            "date_col": "Publication date", "value_col": "Training time (hours)",
            "entity_label": "Longest run", "agg": "cummax",
            "year_min": 2016, "year_max": 2026, "years_window": 20,
            "seconds_per_year": 0.9, "mode": "line_grow",
            "value_fmt": "integer", "unit_suffix": "h", "series": "ai_trends",
            "source": "Epoch AI (CC BY)", "mood": "reflective",
            "hashtags": ["ai", "compute", "technology"],
        },
    },

    # ===================== MONEY & POWER =====================
    # Money is the unit in four of the channel's five best-CTR titles. These
    # stay at the default pace: the short-video evidence is strong within
    # line_grow but untested for bar_race, so they are not the place to bet.
    {
        "id": "stock_market_cap",
        "reason": "US listed companies are worth $68.9 TRILLION against China's "
                  "$15.5T. Biggest-number-wins, the same shape as the channel's "
                  "top video (The World's Biggest Economies, 4.65% CTR).",
        "topic": {
            "key": "money_stock_markets", "title": "The World's Biggest Stock Markets",
            "subtitle": "Listed company value", "fetcher": "worldbank",
            "code": "CM.MKT.LCAP.CD", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit": "USD",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 1,
            "mood": "majestic", "hashtags": ["money", "stocks", "economy"],
        },
    },
    {
        "id": "money_reserves",
        "reason": "China sits on $3.7 trillion in reserves and gold. 'Who has the "
                  "biggest pile of money' is the most literal version of the "
                  "channel's best-performing subject.",
        "topic": {
            "key": "money_reserves", "title": "Who Has the Biggest Piggy Bank?",
            "subtitle": "Total reserves, including gold", "fetcher": "worldbank",
            "code": "FI.RES.TOTL.CD", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit": "USD",
            "value_scale": 1000000000, "unit_suffix": "B",
            "mood": "majestic", "hashtags": ["money", "economy", "gold"],
        },
    },
    {
        "id": "hightech_exports",
        "reason": "China ships $857B of high-tech exports, double Hong Kong and "
                  "triple Germany. Pairs the AI audience with the money pillar.",
        "topic": {
            "key": "money_hightech_exports", "title": "Who Exports the Most Technology?",
            "subtitle": "High-technology exports", "fetcher": "worldbank",
            "code": "TX.VAL.TECH.CD", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit": "USD",
            "value_scale": 1000000000, "unit_suffix": "B",
            "mood": "hopeful", "hashtags": ["technology", "exports", "economy"],
        },
    },
    {
        "id": "fdi_inflows",
        "reason": "Where the world actually puts its money: $400B into the US in a "
                  "single year, with Singapore second on a fraction of the population.",
        "topic": {
            "key": "money_fdi", "title": "Where the World's Money Goes",
            "subtitle": "Foreign direct investment, net inflows", "fetcher": "worldbank",
            "code": "BX.KLT.DINV.CD.WD", "mode": "bar_race", "series": "money",
            "source": "World Bank", "unit": "USD",
            "value_scale": 1000000000, "unit_suffix": "B",
            "mood": "majestic", "hashtags": ["money", "investment", "economy"],
        },
    },
    {
        "id": "military_personnel",
        "reason": "India fields the largest armed forces on record at 3.07M, ahead "
                  "of China. Companion to the military spending video, with people "
                  "instead of dollars. Note: the series ends in 2020.",
        "topic": {
            "key": "military_personnel", "title": "The World's Biggest Armies",
            "subtitle": "Armed forces personnel", "fetcher": "worldbank",
            "code": "MS.MIL.TOTL.P1", "mode": "bar_race", "series": "world_in_data",
            "source": "World Bank", "unit": "people",
            "value_scale": 1000000, "unit_suffix": "M", "value_decimals": 2,
            "mood": "majestic", "hashtags": ["military", "worldstats", "army"],
        },
    },

    # ===================== BIGGEST IN THE WORLD (added 2026-10-08) =====================
    # From the 2026-08-07..10-08 export (80 videos): World in Data clears 800
    # views 52% of the time against ~20% for every other series, and within it
    # absolute "biggest / most" totals have a 644 median against 233 for rates
    # and per-person metrics. Every entry below is an absolute total, fetched
    # live on 2026-10-08. `year_min`/`year_max` keep each race inside the years
    # every bar has a real figure: _prepare_bar back- and forward-fills gaps, so
    # e.g. Russia (in the source from 1985 or 1992) would otherwise get an
    # invented flat bar for the years before.
    {
        "id": "oil_production",
        "reason": "The lead has changed hands six times since 1985 — Russia, "
                  "Saudi Arabia, then the US in 2017, which now pumps a record "
                  "10,040 TWh, 64% more than Russia in second.",
        "topic": {
            "key": "oil_production", "title": "Who Pumps the Most Oil?",
            "subtitle": "Oil production, terawatt-hours", "fetcher": "owid",
            "slug": "oil-production-by-country", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / Energy Institute",
            "unit_suffix": " TWh", "year_min": 1985, "year_max": 2024,
            "mood": "majestic", "hashtags": ["oil", "energy", "worldstats"],
        },
    },
    {
        "id": "coal_production",
        "reason": "The US led in 1985. China passed it in 1989 and now digs "
                  "25,920 TWh — more than five times India in second place.",
        "topic": {
            "key": "coal_production", "title": "Who Digs the Most Coal?",
            "subtitle": "Coal production, terawatt-hours", "fetcher": "owid",
            "slug": "coal-production-by-country", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / Energy Institute",
            "unit_suffix": " TWh", "year_min": 1985, "year_max": 2024,
            "mood": "majestic", "hashtags": ["coal", "energy", "worldstats"],
        },
    },
    {
        "id": "solar_capacity",
        "reason": "Germany led solar until 2015. China now has 1,202 GW installed "
                  "— nearly six times the US. Companion to 'Who Runs on "
                  "Renewables?' (1,234 views).",
        "topic": {
            "key": "solar_capacity", "title": "Who Has the Most Solar Power?",
            "subtitle": "Installed solar capacity, gigawatts", "fetcher": "owid",
            "slug": "installed-solar-pv-capacity", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / IRENA",
            "unit_suffix": " GW", "year_min": 2005,
            "mood": "hopeful", "hashtags": ["solar", "energy", "renewables"],
        },
    },
    {
        "id": "wind_power",
        "reason": "Three leaders in 25 years: Germany, then the US in 2008, then "
                  "China in 2016 — which now generates 997 TWh, more than double "
                  "the US.",
        "topic": {
            "key": "wind_power", "title": "Who Makes the Most Wind Power?",
            "subtitle": "Electricity from wind, terawatt-hours", "fetcher": "owid",
            "slug": "wind-generation", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / Ember",
            "unit_suffix": " TWh", "year_min": 2000, "year_max": 2024,
            "mood": "hopeful", "hashtags": ["wind", "energy", "renewables"],
        },
    },
    {
        "id": "nuclear_power",
        "reason": "The US leads throughout, but China (418 TWh) has passed "
                  "France (295 TWh) for second. Ends in 2022, the last year with "
                  "a real figure for Ukraine.",
        "topic": {
            "key": "nuclear_power", "title": "Who Makes the Most Nuclear Energy?",
            "subtitle": "Electricity from nuclear, terawatt-hours", "fetcher": "owid",
            "slug": "nuclear-energy-generation", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / Ember",
            "unit_suffix": " TWh", "year_min": 1985, "year_max": 2022,
            "mood": "majestic", "hashtags": ["nuclear", "energy", "worldstats"],
        },
    },
    {
        "id": "ev_sales",
        "reason": "The US sold the most electric cars until 2015. China bought "
                  "13.3 million in 2025 against 1.5 million in the US. Only ~60 "
                  "countries report, so the race is among the big markets.",
        "topic": {
            "key": "ev_sales", "title": "Who Buys the Most Electric Cars?",
            "subtitle": "Electric cars sold per year", "fetcher": "owid",
            "slug": "electric-car-sales", "mode": "bar_race", "top_n": 10,
            "series": "world_in_data", "source": "Our World in Data / IEA",
            "value_scale": 1000000, "unit_suffix": "M", "value_decimals": 2,
            "year_min": 2012,
            "mood": "hopeful", "hashtags": ["electriccars", "ev", "worldstats"],
        },
    },
    {
        "id": "rice_production",
        "reason": "China out-grew India in rice every year from 1961 — until "
                  "2023. India now leads 218 Mt to 208 Mt. 'India Just Overtook "
                  "China' is the channel's best title pattern.",
        "topic": {
            "key": "rice_production", "title": "Who Grows the Most Rice?",
            "subtitle": "Rice production, million tonnes", "fetcher": "owid",
            "slug": "rice-production", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / FAO",
            "value_scale": 1000000, "unit_suffix": " Mt", "year_min": 1961,
            "years_window": 64,
            "mood": "hopeful", "hashtags": ["rice", "food", "agriculture"],
        },
    },
    {
        "id": "milk_production",
        "reason": "The US led until 1997. India now produces 248 Mt of milk — "
                  "more than double the US, with Pakistan third. Starts in 1992, "
                  "the first year the source has Russia.",
        "topic": {
            "key": "milk_production", "title": "Who Produces the Most Milk?",
            "subtitle": "Milk production, million tonnes", "fetcher": "owid",
            "slug": "milk-production-tonnes", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / FAO",
            "value_scale": 1000000, "unit_suffix": " Mt", "year_min": 1992,
            "mood": "hopeful", "hashtags": ["milk", "food", "agriculture"],
        },
    },
    {
        "id": "gas_production",
        "reason": "A two-way fight: Russia led from 1986, the US took it back "
                  "for good in 2011 and now produces 10,319 TWh to Russia's 6,299.",
        "topic": {
            "key": "gas_production", "title": "Who Produces the Most Natural Gas?",
            "subtitle": "Gas production, terawatt-hours", "fetcher": "owid",
            "slug": "gas-production-by-country", "mode": "bar_race",
            "series": "world_in_data", "source": "Our World in Data / Energy Institute",
            "unit_suffix": " TWh", "year_min": 1985, "year_max": 2024,
            "mood": "majestic", "hashtags": ["naturalgas", "energy", "worldstats"],
        },
    },
    {
        "id": "manufacturing_output",
        "reason": "The US was the world's factory until China passed it in 2010. "
                  "The World Bank has China only from 2004 and no US figure "
                  "after 2021, so the race runs 2004-2021.",
        "topic": {
            "key": "manufacturing_output", "title": "Who Makes the World's Stuff?",
            "subtitle": "Manufacturing value added (US$)", "fetcher": "worldbank",
            "code": "NV.IND.MANF.CD", "mode": "bar_race",
            "series": "world_in_data", "source": "World Bank", "unit": "USD",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 2,
            "year_min": 2004, "year_max": 2021,
            "mood": "majestic", "hashtags": ["manufacturing", "economy", "worldstats"],
        },
    },

    # ===================== FOOTBALL (added 2026-10-08) =====================
    # Both Sports videos that cleared 800 views are football (World Cup titles
    # 1,088, international goals 870); the last four cricket posts did 57-420.
    # Built by scripts/curate_football.py from martj42/international_results,
    # which now runs through the 2026 World Cup. Finals tournaments only.
    {
        "id": "football_world_cup_goals",
        "reason": "Brazil 247, Germany 243 — four goals apart after 96 years of "
                  "World Cups, through 2026. Argentina is a distant third on 171.",
        "topic": {
            "key": "football_world_cup_goals", "title": "Most World Cup Goals",
            "subtitle": "Goals scored at FIFA World Cups since 1930",
            "fetcher": "curated_csv", "file": "football_world_cup_goals.csv",
            "mode": "bar_race", "top_n": 10, "years_window": 100,
            "value_fmt": "integer", "series": "sports",
            "source": "martj42/international_results (CC0)", "mood": "majestic",
            "hashtags": ["worldcup", "football", "sports"],
        },
    },
    {
        "id": "football_euro_wins",
        "reason": "Germany 30 wins, Spain 28 — two apart, with Spain winning the "
                  "last tournament. The source counts the Soviet Union as Russia.",
        "topic": {
            "key": "football_euro_wins", "title": "Who Wins the Most at the Euros?",
            "subtitle": "Match wins at the UEFA European Championship",
            "fetcher": "curated_csv", "file": "football_euro_wins.csv",
            "mode": "bar_race", "top_n": 10, "years_window": 70,
            "value_fmt": "integer", "series": "sports",
            "source": "martj42/international_results (CC0)", "mood": "majestic",
            "hashtags": ["euros", "football", "sports"],
        },
    },
    {
        "id": "football_copa_wins",
        "reason": "Argentina and Uruguay swapped the lead nine times before 1955. "
                  "Argentina now has 132 wins to Uruguay's 115 and Brazil's 109.",
        "topic": {
            "key": "football_copa_wins", "title": "Who Rules the Copa América?",
            "subtitle": "Match wins since 1916",
            "fetcher": "curated_csv", "file": "football_copa_wins.csv",
            "mode": "bar_race", "top_n": 10, "years_window": 110,
            "value_fmt": "integer", "series": "sports",
            "source": "martj42/international_results (CC0)", "mood": "majestic",
            "hashtags": ["copaamerica", "football", "sports"],
        },
    },

    # ===================== COUNTRY VS COUNTRY (added 2026-10-08) =====================
    # A test playlist. The five India-vs-China head-to-heads have a 571 median
    # with one flop in five (best floor on the channel outside World in Data),
    # and "India Just Overtook China" is the proven title shape. These extend
    # the format to other rivalries; each pair has a real figure for every year
    # shown. Keys start `vs_` -> series country_vs_country (config.topic_series).
    {
        "id": "vs_us_china_economy",
        "reason": "Measured by what the money actually buys, China passed the US "
                  "in 2014 and is now $41T to $31T. In plain dollars the US still "
                  "leads — the subtitle has to say which measure this is.",
        "topic": {
            "key": "vs_us_china_economy", "title": "US vs China: The Economy",
            "subtitle": "GDP at purchasing power parity", "fetcher": "worldbank",
            "code": "NY.GDP.MKTP.PP.CD", "mode": "line_multi",
            "entities": ["United States", "China"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 1,
            "mood": "majestic", "hashtags": ["usa", "china", "economy"],
        },
    },
    {
        "id": "vs_us_china_science",
        "reason": "China passed the US in published research in 2017 and now "
                  "puts out 933K papers a year to 431K. 'Most Scientific Papers' "
                  "did 1,129 views as a ranking.",
        "topic": {
            "key": "vs_us_china_science", "title": "US vs China: The Science Race",
            "subtitle": "Scientific papers published per year", "fetcher": "worldbank",
            "code": "IP.JRN.ARTC.SC", "mode": "line_multi",
            "entities": ["United States", "China"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank / NSF",
            "value_scale": 1000, "unit_suffix": "K", "value_decimals": 0,
            "mood": "hopeful", "hashtags": ["usa", "china", "science"],
        },
    },
    {
        "id": "vs_india_uk_gdp",
        "reason": "India passed the UK in 2022, and the 2025 figures have the UK "
                  "back in front by a hair — $4.00T to $3.96T.",
        "topic": {
            "key": "vs_india_uk_gdp", "title": "India vs UK: The Economy",
            "subtitle": "GDP (US$), head to head", "fetcher": "worldbank",
            "code": "NY.GDP.MKTP.CD", "mode": "line_multi",
            "entities": ["India", "United Kingdom"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 2,
            "mood": "reflective", "hashtags": ["india", "uk", "economy"],
        },
    },
    {
        "id": "vs_germany_japan_gdp",
        "reason": "Japan was the bigger economy for 51 years. Germany took the "
                  "place back in 2023 and now leads $5.05T to $4.44T.",
        "topic": {
            "key": "vs_germany_japan_gdp", "title": "Germany vs Japan: The Economy",
            "subtitle": "GDP (US$), head to head", "fetcher": "worldbank",
            "code": "NY.GDP.MKTP.CD", "mode": "line_multi",
            "entities": ["Germany", "Japan"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 2,
            "mood": "reflective", "hashtags": ["germany", "japan", "economy"],
        },
    },
    {
        "id": "vs_india_pakistan_income",
        "reason": "The two traded places for decades. India now earns $2,702 a "
                  "person to Pakistan's $1,596. A per-person metric, which is "
                  "the weaker kind on this channel — the rivalry is the bet.",
        "topic": {
            "key": "vs_india_pakistan_income", "title": "India vs Pakistan: Income",
            "subtitle": "GDP per person (US$)", "fetcher": "worldbank",
            "code": "NY.GDP.PCAP.CD", "mode": "line_multi",
            "entities": ["India", "Pakistan"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank",
            "value_fmt": "integer",
            "mood": "reflective", "hashtags": ["india", "pakistan", "economy"],
        },
    },
    {
        "id": "vs_uk_france_gdp",
        "reason": "The lead has changed hands five times since 1997; the UK is "
                  "ahead today, $4.00T to $3.37T.",
        "topic": {
            "key": "vs_uk_france_gdp", "title": "UK vs France: The Economy",
            "subtitle": "GDP (US$), head to head", "fetcher": "worldbank",
            "code": "NY.GDP.MKTP.CD", "mode": "line_multi",
            "entities": ["United Kingdom", "France"], "years_window": 50,
            "series": "country_vs_country", "source": "World Bank",
            "value_scale": 1000000000000, "unit_suffix": "T", "value_decimals": 2,
            "mood": "reflective", "hashtags": ["uk", "france", "economy"],
        },
    },

    # ===================== ML BASICS =====================
    # Worst reach on the channel (52 median views) and by far the best
    # conversion: 4.10 subs per 1k views against AI's 0.40. These three scenes
    # are already written and registered, and are retitled as paradoxes — the
    # one packaging that ever worked for the series ("99% Accurate and Totally
    # Useless": 1,492 views where its siblings average 52).
    {
        "id": "simpsons_paradox",
        "reason": "Every group went down while the total went up — a visual "
                  "impossibility on screen. Paradox titles are the only ML Basics "
                  "packaging that has ever broken out.",
        "topic": {
            "key": "simpsons_paradox", "title": "Every Group Went Down. The Total Went Up.",
            "subtitle": "Simpson's paradox", "mode": "manim", "scene": "simpsons_paradox",
            "series": "ml_concept", "source": "Concept explainer", "mood": "reflective",
            "hashtags": ["statistics", "data", "machinelearning"],
        },
    },
    {
        "id": "gradient_descent",
        "reason": "How a model actually learns, as a ball rolling downhill. The "
                  "scene is written and registered — it just has never been built.",
        "topic": {
            "key": "gradient_descent", "title": "AI Learns by Falling Downhill",
            "subtitle": "Gradient descent", "mode": "manim", "scene": "gradient_descent",
            "series": "ml_concept", "source": "Concept explainer", "mood": "hopeful",
            "hashtags": ["machinelearning", "ai", "datascience"],
        },
    },
    {
        "id": "kmeans",
        "reason": "The computer sorts the data into groups nobody labelled. Same "
                  "'wait, how?' hook, and the scene is ready to render.",
        "topic": {
            "key": "kmeans", "title": "Nobody Told It These Were Groups",
            "subtitle": "K-means clustering", "mode": "manim", "scene": "kmeans",
            "series": "ml_concept", "source": "Concept explainer", "mood": "lofi",
            "hashtags": ["machinelearning", "ai", "clustering"],
        },
    },

    # ===================== HOW CHARTS LIE =====================
    # Narrated Manim episodes. The scenes for these three are written and
    # registered, so they build like any other topic; the rest of the
    # 17-episode plan still needs its scenes authored.
    {
        "id": "lie_inverted_axis",
        "reason": "Episode 2 of the plan and the strongest 'wait, WHAT' moment in "
                  "the series — a rise drawn as a fall.",
        "topic": {
            "key": "lie_inverted_axis", "title": "The Chart That Was Upside Down",
            "subtitle": "Charts Lie #2", "mode": "manim", "scene": "lie_inverted_axis",
            "series": "charts_lie", "source": "Concept explainer", "mood": "reflective",
            "hashtags": ["data", "statistics", "dataliteracy"],
        },
    },
    {
        "id": "lie_mean_median",
        "reason": "Episode 9 — the average everybody quotes, broken by one outlier. "
                  "The most useful thing in the series.",
        "topic": {
            "key": "lie_mean_median", "title": "A Billionaire Walks Into a Bar",
            "subtitle": "Charts Lie #9", "mode": "manim", "scene": "lie_mean_median",
            "series": "charts_lie", "source": "Concept explainer", "mood": "reflective",
            "hashtags": ["data", "statistics", "dataliteracy"],
        },
    },
    {
        "id": "lie_area_radius",
        "reason": "Episode 14 — bubbles scaled by radius look four times too big. "
                  "Purely visual, so it needs no numeracy from the viewer.",
        "topic": {
            "key": "lie_area_radius", "title": "This Circle Is 4x Too Big",
            "subtitle": "Charts Lie #14", "mode": "manim", "scene": "lie_area_radius",
            "series": "charts_lie", "source": "Concept explainer", "mood": "reflective",
            "hashtags": ["data", "statistics", "dataliteracy"],
        },
    },
]

# Planned series that need a narrated Manim scene authored first — listed so
# they are visible, but never presented as one-click work.
AUTHORED_SERIES = [
    {"name": "How Charts Lie", "episodes": 13, "doc": "docs/SERIES_how_charts_lie.md",
     "note": "4 of 17 episodes have scenes written (see Build Next); the other 13 "
             "still need theirs authored."},
    {"name": "LLM Basics", "episodes": 10, "doc": "docs/SERIES_llm_basics.md",
     "note": "10-episode plan for a new 'How LLMs Work' playlist."},
]


def _idea_state(idea: dict[str, Any], existing: set[str]) -> str:
    return "exists" if idea["topic"]["key"] in existing else "ready"


@app.get("/api/ideas")
def api_ideas() -> dict[str, Any]:
    existing = {t["key"] for t in load_topics()}
    by_series: dict[str, int] = {}
    for t in load_topics():
        s = topic_series(t)
        by_series[s] = by_series.get(s, 0) + 1

    out = []
    for idea in IDEAS:
        topic = idea["topic"]
        series = topic.get("series") or "world_in_data"
        code = topic.get("code") or topic.get("slug") or topic.get("url") or ""
        out.append({
            "id": idea["id"],
            "reason": idea["reason"],
            "key": topic["key"],
            "title": topic["title"],
            "subtitle": topic.get("subtitle", ""),
            "series": series,
            "playlist": playlist_of(series)[0],
            "source": topic.get("source", ""),
            # Long cricsheet URLs are noise in the card; show the archive name.
            "code": (topic.get("scene", "") if topic.get("mode") == "manim"
                     else (code.rsplit("/", 1)[-1] if code.startswith("http") else code)),
            # Authored scenes have no fetcher — they carry their own content.
            "fetcher": topic.get("fetcher", "authored scene"),
            "mode": topic.get("mode", "bar_race"),
            "state": _idea_state(idea, existing),
        })

    # Grouped playlist-wise, richest pillar first, so the page reads by series.
    order = [s for s in SERIES_ORDER if any(i["series"] == s for i in out)]
    order += [s for s in {i["series"] for i in out} if s not in order]
    groups = []
    for series in order:
        items = [i for i in out if i["series"] == series]
        name, exists = playlist_of(series)
        groups.append({
            "series": series,
            "playlist": name,
            "playlist_exists": exists,
            "in_catalog": by_series.get(series, 0),
            "ready": sum(1 for i in items if i["state"] == "ready"),
            "ideas": items,
        })
    # Most suggestions first — that is where the work is.
    groups.sort(key=lambda g: -g["ready"])

    return {"ideas": out, "groups": groups, "authored": AUTHORED_SERIES,
            "catalog_size": len(existing)}


class IdeaReq(BaseModel):
    id: str
    # Accepting only writes the topic into the catalog. It then shows up in
    # Launch Control's NEW TOPICS strategy, where it can be reverted or built.
    render: bool = False


@app.post("/api/ideas/verify")
def api_idea_verify(req: IdeaReq) -> dict[str, Any]:
    """Actually fetch the idea's data source before committing to it."""
    idea = next((i for i in IDEAS if i["id"] == req.id), None)
    if not idea:
        raise HTTPException(404, "Unknown idea")
    if idea["topic"].get("mode") == "manim":
        # Narrated scenes carry their own content; there is nothing to fetch.
        from graph_bot.scenes import SCENES

        scene = idea["topic"].get("scene")
        if scene not in SCENES:
            return {"ok": False, "error": f"scene '{scene}' is not registered"}
        return {"ok": True, "rows": 0, "years": "authored scene", "entities": None,
                "note": f"Manim scene '{scene}' is registered and ready to render."}
    from graph_bot import fetch as fetch_mod

    try:
        df = fetch_mod.fetch(idea["topic"], load_settings())
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if df is None or len(df) == 0:
        return {"ok": False, "error": "source returned no rows"}
    years = sorted(df["year"].unique()) if "year" in df else []
    return {
        "ok": True, "rows": int(len(df)),
        "years": f"{years[0]}–{years[-1]}" if years else "",
        "entities": int(df["entity"].nunique()) if "entity" in df else None,
    }


@app.post("/api/ideas/accept")
def api_idea_accept(req: IdeaReq) -> dict[str, Any]:
    """Write the idea into topics.yaml (and optionally queue a render)."""
    idea = next((i for i in IDEAS if i["id"] == req.id), None)
    if not idea:
        raise HTTPException(404, "Unknown idea")
    topic = idea["topic"]
    if any(t.get("key") == topic["key"] for t in load_topics()):
        raise HTTPException(400, f"'{topic['key']}' is already in the catalog")

    _append_topic_block(topic)

    job = None
    if req.render:
        job = manager.submit([topic["key"]], topic["key"], ["--topics", topic["key"]])
    return {"ok": True, "key": topic["key"], "staged": not req.render,
            "job": job.to_dict() if job else None}


class RemoveTopicReq(BaseModel):
    key: str


@app.post("/api/topics/remove")
def api_remove_topic(req: RemoveTopicReq) -> dict[str, Any]:
    """Undo a staged topic by deleting its block from config/topics.yaml.

    Only ever removes topics that have never been rendered, so nothing that
    produced a video can be lost this way.
    """
    key = req.key
    if not any(t.get("key") == key for t in load_topics()):
        raise HTTPException(404, f"'{key}' is not in the catalog")
    if _last_rendered(key, resolve_path(load_settings(), "output")):
        raise HTTPException(400, f"'{key}' has already been rendered — remove it by hand")

    path = CONFIG_DIR / "topics.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip().startswith("- key:") and ln.split("key:", 1)[1].strip().strip('"\'') == key),
                 None)
    if start is None:
        raise HTTPException(500, f"could not locate the '{key}' block in topics.yaml")
    # The block runs from its `- key:` line to the next block; measure it from
    # there, then widen backwards over a generated comment line if present.
    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith(
            ("- key:", "# added via dashboard")):
        end += 1
    if start > 0 and lines[start - 1].strip().startswith("# added via dashboard"):
        start -= 1
    while end > start and not lines[end - 1].strip():
        end -= 1  # keep trailing blank lines out of the cut

    updated = "\n".join(lines[:start] + lines[end:]).rstrip("\n") + "\n"
    try:
        parsed = yaml.safe_load(updated)
        keys = [t.get("key") for t in parsed.get("topics", [])]
        if key in keys:
            raise ValueError("block still present after removal")
    except Exception as exc:
        raise HTTPException(500, f"Refusing to write invalid YAML: {exc}")
    path.write_text(updated, encoding="utf-8")
    return {"ok": True, "removed": key, "total": len(keys)}


class OpenReq(BaseModel):
    path: str


@app.get("/api/video/{key}")
def api_video(key: str, request: Request) -> Response:
    """Stream a topic's finished mp4 so it can be watched inside the dashboard.

    Serves Range requests, because browsers will not scrub (or in some cases
    even start) an HTML5 video without them.
    """
    rel = _exported_keys().get(key)
    path = (PROJECT_ROOT / rel / "video.mp4") if rel else None
    if path is None or not path.exists():
        latest = _latest_renders().get(key)
        if latest:
            try:
                meta = json.loads(latest[1].read_text(encoding="utf-8"))
                cand = Path(meta.get("video", ""))
                path = cand if cand.exists() else None
            except Exception:
                path = None
    if path is None or not path.exists():
        raise HTTPException(404, "No rendered video for this topic")

    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type="video/mp4",
                            headers={"Accept-Ranges": "bytes",
                                     "Cache-Control": "no-store"})

    try:
        units, _, rng = range_header.partition("=")
        start_s, _, end_s = rng.partition("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else size - 1
    except ValueError:
        raise HTTPException(416, "Bad Range header")
    start = max(0, start)
    end = min(end, size - 1)
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

    return StreamingResponse(chunks(), status_code=206, media_type="video/mp4",
                             headers={
                                 "Content-Range": f"bytes {start}-{end}/{size}",
                                 "Accept-Ranges": "bytes",
                                 "Content-Length": str(end - start + 1),
                                 "Cache-Control": "no-store",
                             })


from dashboard import longform_api  # noqa: E402

app.include_router(longform_api.router)


@app.get("/api/thumb/{key}")
def api_thumb(key: str) -> FileResponse:
    """The exported thumbnail.jpg for a topic, if one exists."""
    rel = _exported_keys().get(key)
    if rel:
        path = PROJECT_ROOT / rel / "thumbnail.jpg"
        if path.exists():
            return FileResponse(path, media_type="image/jpeg",
                                headers={"Cache-Control": "max-age=300"})
    raise HTTPException(404, "No thumbnail")


@app.post("/api/open")
def api_open(req: OpenReq) -> dict[str, Any]:
    """Open an export folder in the OS file explorer (local tool convenience)."""
    target = (PROJECT_ROOT / req.path).resolve()
    if not str(target).startswith(str(PROJECT_ROOT)) or not target.exists():
        raise HTTPException(400, "Path outside project or missing")
    if os.name == "nt":
        os.startfile(target)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    # Never cache the shell: its <script> tag points at a hashed bundle, so a
    # cached shell keeps serving the previous build after a rebuild.
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()
