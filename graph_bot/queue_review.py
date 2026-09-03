"""Queue review with no API key and no cost: rules first, local LLM on top.

The ranking formula (queue.next_up) orders by series momentum and length.
This layer adds the editorial checks the formula deliberately leaves out, in
two tiers:

1. RULES (always run, instant, deterministic): series gone quiet, titles that
   will truncate, three same-shaped hooks in a row, analytics staleness,
   uploads still sitting Private.
2. LOCAL LLM (best effort): if an Ollama server is reachable, the model named
   by OLLAMA_MODEL (default qwen3.5:27b) reads the ranked picks with their
   stats and adds judgment the rules can't encode — timeliness, title
   strength, sequencing. Inference runs entirely on this machine; nothing
   leaves it and nothing is billed. If Ollama is down, slow, or returns
   garbage, the rule tier's answer stands alone.

Returns the shape the dashboard's review panel renders:
{summary, items: [{key, verdict, note}], suggested_order, changed}.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

import requests

from . import store

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:27b")
OLLAMA_TIMEOUT = 420  # a 27B model on local hardware needs real room

# What the model must return; Ollama enforces this schema server-side.
_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["keep", "move_up", "move_down", "hold"]},
                    "note": {"type": "string"},
                },
                "required": ["key", "verdict", "note"],
            },
        },
        "suggested_order": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "items", "suggested_order"],
}

TITLE_MAX = 55          # Shorts feed truncates titles around here
STALE_SERIES_DAYS = 7   # a good series unfed for this long is worth a bump
STALE_STATS_DAYS = 3    # analytics older than this shouldn't steer the order


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(iso)).days
    except ValueError:
        return None


def _series_last_posted(series_of: dict[str, str]) -> dict[str, int]:
    """series -> days since its most recent upload."""
    out: dict[str, int] = {}
    for key, entry in store.load_log().items():
        s = series_of.get(key)
        days = _days_since(entry.get("uploaded_at"))
        if s is None or days is None:
            continue
        if s not in out or days < out[s]:
            out[s] = days
    return out


def _llm_review(picks: list[dict[str, Any]],
                last_posted: dict[str, int]) -> dict[str, Any] | None:
    """Ask the local Ollama model, or return None if it can't answer."""
    today = dt.date.today().isoformat()
    ch = store.latest_channel_stats() or {}
    lines = [
        f"Date: {today}.",
        f"Channel 'Data in Motion' — YouTube Shorts, animated data charts "
        f"({ch.get('subscribers', '?')} subscribers).",
        "Measured facts: videos ≤10s median 642 views; 30s+ median 52. "
        "Sports has the best click-through; ML explainers convert subscribers "
        "but reach poorly.",
        "",
        "The queue below is already ranked by a sound statistical formula. "
        "Only suggest moves the formula cannot see: timeliness against the "
        "date or season, weak or strong titles, better narrative sequencing. "
        "If the order is right, endorse it — do not invent changes. "
        "Include an item ONLY when its verdict is not 'keep' (at most 4 items); "
        "every note is one concrete sentence. Keep the summary to 2 sentences. "
        "suggested_order must contain exactly the keys given.",
        "",
        "Queue (best first):",
    ]
    for i, p in enumerate(picks, 1):
        lines.append(
            f"{i}. key={p['key']} · \"{p['title']}\" · playlist={p.get('playlist')}"
            f" · {p.get('duration_sec') or '?'}s"
            f" · series last posted {last_posted.get(p.get('series'), '?')} days ago"
            f" · ranked because: {p['reason']}")
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "stream": False,
                  "format": _SCHEMA,
                  # think=False: qwen's reasoning tokens triple the wall time
                  # here and the structured schema does the disciplining anyway.
                  "think": False,
                  "options": {"temperature": 0.2, "num_predict": 900},
                  "messages": [{"role": "user", "content": "\n".join(lines)}]},
            timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        parsed = json.loads(body["message"]["content"])
    except Exception as exc:
        # Ollama down, model missing, timeout, bad JSON — rules stand alone,
        # but say why in the server log so a misconfiguration isn't invisible.
        print(f"queue review: local LLM skipped ({type(exc).__name__}: {str(exc)[:200]})")
        return None

    known = {p["key"] for p in picks}
    items = [n for n in parsed.get("items", [])
             if isinstance(n, dict) and n.get("key") in known
             and n.get("verdict") in ("keep", "move_up", "move_down", "hold")]
    order = [k for k in parsed.get("suggested_order", []) if k in known]
    order += [p["key"] for p in picks if p["key"] not in order]  # never drop items
    return {
        "summary": str(parsed.get("summary", "")).strip(),
        "items": items,
        "suggested_order": order,
        "usage": {"input_tokens": body.get("prompt_eval_count", 0),
                  "output_tokens": body.get("eval_count", 0)},
    }


def review(picks: list[dict[str, Any]]) -> dict[str, Any]:
    from .config import load_topics, topic_series

    series_of = {t["key"]: topic_series(t) for t in load_topics()}
    last_posted = _series_last_posted(series_of)

    notes: list[dict[str, str]] = []
    ups: list[str] = []
    downs: list[str] = []
    summary_bits: list[str] = []
    stale_flagged: set[str] = set()  # one staleness note per series, not per pick

    # ---- per-item checks ----
    for i, p in enumerate(picks):
        key, series = p["key"], series_of.get(p["key"])
        title = p.get("title") or ""
        dur = p.get("duration_sec")

        if dur and dur >= 30:
            notes.append({"key": key, "verdict": "hold",
                          "note": f"{dur:.0f}s — 30s+ videos median ~52 views vs 642"
                                  " for ≤10s. Worth a re-cut before it burns a slot."})
            downs.append(key)
            continue

        if len(title) > TITLE_MAX:
            notes.append({"key": key, "verdict": "keep",
                          "note": f"title is {len(title)} chars — the Shorts feed"
                                  f" truncates around {TITLE_MAX}; consider shortening."})

        # A strong series that has gone quiet deserves its next slot sooner —
        # flagged once, on the series' best-ranked pick.
        days = last_posted.get(series)
        if (days is not None and days >= STALE_SERIES_DAYS and i >= 3
                and series not in stale_flagged):
            stale_flagged.add(series)
            notes.append({"key": key, "verdict": "move_up",
                          "note": f"{p.get('playlist') or series} hasn't posted in"
                                  f" {days} days — feeds reward regularity, bump it."})
            ups.append(key)

    # Three near-identical openers in a row read as a rut in the feed.
    openers = [(p["key"], (p.get("title") or "").split(" ")[0].lower()) for p in picks]
    for i in range(2, len(openers)):
        a, b, c = openers[i - 2][1], openers[i - 1][1], openers[i][1]
        if a and a == b == c:
            key = openers[i][0]
            if key not in downs:
                notes.append({"key": key, "verdict": "move_down",
                              "note": f"third \"{openers[i][1].title()}…\" title in a row"
                                      " — space repeated hooks so the feed stays varied."})
                downs.append(key)
            break

    # ---- channel-level context for the summary ----
    stats = store.latest_video_stats()
    if stats:
        newest = max((v.get("fetched_at") or "") for v in stats.values())
        stale = _days_since(newest)
        if stale is not None and stale >= STALE_STATS_DAYS:
            summary_bits.append(f"analytics are {stale} days old — sync before trusting"
                                " the order")
        private = sum(1 for v in stats.values() if v.get("privacy_status") == "private")
        if private:
            summary_bits.append(f"{private} uploaded video(s) still Private on YouTube —"
                                " flip them public before adding more to the pile")

    # ---- compose the rule-tier order: ups bubble toward the front,
    # holds/downs sink to the back, everything else keeps formula order ----
    base = [p["key"] for p in picks]
    order = ([k for k in base if k in ups]
             + [k for k in base if k not in ups and k not in downs]
             + [k for k in base if k in downs])

    # ---- local LLM tier (best effort) ----
    llm = _llm_review(picks, _series_last_posted(series_of))
    if llm:
        # Hard facts beat vibes: rule holds/downs stay sunk even if the model
        # liked those picks; otherwise the model's sequencing wins.
        order = ([k for k in llm["suggested_order"] if k not in downs]
                 + [k for k in llm["suggested_order"] if k in downs])
        ruled = {n["key"] for n in notes if n["verdict"] != "keep"}
        notes += [n for n in llm["items"]
                  if n["verdict"] != "keep" and n["key"] not in ruled]
        summary = llm["summary"] or "Reviewed."
        if summary_bits:
            summary += " Also: " + "; ".join(summary_bits) + "."
        return {
            "summary": summary,
            "items": notes,
            "suggested_order": order,
            "changed": order != base,
            "model": f"{OLLAMA_MODEL} + rules · local",
            "usage": llm["usage"],
        }

    flagged = len(ups) + len(downs)
    if flagged == 0 and not summary_bits:
        summary = "The ranked order holds up — nothing the rules would change."
    else:
        parts = []
        if flagged:
            parts.append(f"{flagged} of {len(picks)} picks adjusted"
                         f" ({len(ups)} up, {len(downs)} down/hold)")
        parts += summary_bits
        summary = "; ".join(parts).capitalize() + "."

    return {
        "summary": summary,
        "items": notes,
        "suggested_order": order,
        "changed": order != base,
        "model": "rules",   # the panel shows this instead of a token count
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
