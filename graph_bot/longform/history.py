"""Long-form renders in the dashboard's job history, beside the Shorts runs.

A render writes one row to the same ``job`` table the Shorts pipeline uses:
"running" when it starts, updated as each chapter is rendered or reused, and
settled as done or failed at the end. The build records itself rather than the
dashboard doing it, so a render started from the command line is in the
history too.

The row is marked ``kind: "longform"`` with a ``chapters`` list instead of the
Shorts' six pipeline steps, and its key is the upload-log key (``lf_<key>``).
A render killed outright cannot update its row; the dashboard settles those
from the episode's state file when it reads the history.

Recording is best-effort: a database that is down must never fail a render.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

LOG_KEPT = 120  # same tail the Shorts jobs keep


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class RenderRecord:
    """One render's row. ``target`` is "episode" (the long video) or "shorts" (the
    vertical Shorts cut from its chapters); ``chapters`` limits which chapters the
    row lists (the Shorts skip the cold open and outro)."""

    def __init__(self, key: str, ep: dict[str, Any], only: list[str] | None, force: bool,
                 target: str = "episode", chapters: list[dict[str, Any]] | None = None) -> None:
        shorts = target == "shorts"
        self.job: dict[str, Any] = {
            "id": uuid.uuid4().hex[:10],
            "kind": "longform",
            "target": target,
            "episode": key,
            "label": f"Shorts: {ep.get('title') or key}" if shorts else ep.get("title") or key,
            "keys": [f"lf_{key}_shorts" if shorts else f"lf_{key}"],
            "status": "running",
            "created_at": _now(),
            "started_at": _now(),
            "finished_at": None,
            "current_key": f"lf_{key}",
            "stage": "chapter",
            "agents": {}, "progress": {}, "steps": [], "results": {},
            "options": {"only": only, "force": force},
            "chapters": [{"id": c["id"], "heading": (c.get("short") or {}).get("title") if shorts
                          and (c.get("short") or {}).get("title") else c.get("heading") or c["id"],
                          "state": "pending", "secs": None, "took": None}
                         for c in (chapters if chapters is not None else ep["chapters"])],
            "log": [],
            "log_len": 0,
        }
        self._save()

    @property
    def id(self) -> str:
        return self.job["id"]

    def say(self, line: str) -> None:
        """Print a progress line and keep it in the record's log."""
        print(line, flush=True)
        self.job["log"] = (self.job["log"] + [line.strip()])[-LOG_KEPT:]
        self.job["log_len"] += 1

    def chapter(self, index: int, state: str, done: dict[str, Any] | None = None) -> None:
        ch = self.job["chapters"][index]
        ch["state"] = state
        if done:
            ch["secs"], ch["took"] = done.get("secs"), done.get("took")
        self.job["stage"] = "chapter"
        self._save()

    def stage(self, name: str) -> None:
        self.job["stage"] = name
        self._save()

    def finish(self, status: str, *, secs: float | None = None, error: str | None = None,
               folder: str | None = None) -> None:
        j = self.job
        j.update(status=status, finished_at=_now(), current_key=None,
                 stage="done" if status == "done" else status)
        for ch in j["chapters"]:
            if ch["state"] == "active":
                ch["state"] = "failed" if status == "failed" else "stopped"
        key = j["keys"][0]
        j["results"] = {key: {"status": "ok", "export": folder, "secs": secs} if status == "done"
                        else {"status": "failed", "error": error or "failed"}}
        self._save()
        if status == "done" and self.job["target"] == "episode":
            self._lifecycle(folder)

    def _save(self) -> None:
        try:
            from .. import store

            store.save_job(self.job)
        except Exception as exc:
            print(f"  (job history not saved: {str(exc).splitlines()[0] if str(exc) else exc})",
                  flush=True)

    def _lifecycle(self, folder: str | None) -> None:
        """First and last render dates, the record that outlives deleted files."""
        try:
            from .. import store

            today = dt.date.today().isoformat()
            store.sync_lifecycle([{"topic_key": self.job["keys"][0], "first_rendered_at": today,
                                   "last_rendered_at": today, "last_exported_at": today,
                                   "export_path": folder}])
        except Exception:
            pass
