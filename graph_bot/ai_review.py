"""On-demand AI review of the upload queue's top picks.

The queue RANKING is a plain formula (queue.next_up) — deterministic, free,
auditable — and this module never replaces it. What an LLM adds is the
judgment a formula can't encode: timeliness ("post the CO₂ video this week"),
title strength, seasonal hooks, sequencing sense. One Claude call, only when
the user clicks the button; nothing here runs on the hot path.

Needs ANTHROPIC_API_KEY in .env (config.py loads .env on import). The response
is validated against a Pydantic schema via client.messages.parse, so the
dashboard always gets well-formed suggestions or a clean error.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, List, Literal

from pydantic import BaseModel

from . import store
from .config import PROJECT_ROOT  # noqa: F401  (imported for its .env side effect)

MODEL = "claude-opus-5"


class ItemNote(BaseModel):
    key: str
    verdict: Literal["keep", "move_up", "move_down", "hold"]
    note: str          # one sentence, concrete, references the data or the moment


class QueueReview(BaseModel):
    summary: str       # 2-3 sentences on the queue as a whole
    items: List[ItemNote]
    suggested_order: List[str]   # keys, best-first — usually close to the input order


class ReviewError(RuntimeError):
    """Raised with a message a human can act on."""


def _context(picks: list[dict[str, Any]]) -> str:
    """Everything the reviewer needs, compact enough to stay cheap."""
    today = dt.date.today().isoformat()
    ch = store.latest_channel_stats() or {}
    recent = sorted(store.load_log().items(),
                    key=lambda kv: kv[1].get("uploaded_at") or "", reverse=True)[:6]

    lines = [
        f"Date: {today}",
        f"Channel: 'Data in Motion' — short-form data-visualisation videos "
        f"({ch.get('subscribers', '?')} subscribers, {ch.get('views', '?')} total views).",
        "Measured facts: videos ≤10s median 642 views; 30s+ median 52. "
        "Sports carries the best CTR; ML content converts subscribers but reaches poorly.",
        "",
        "Recently uploaded (newest first):",
    ]
    for key, entry in recent:
        lines.append(f"  - {key} on {(entry.get('uploaded_at') or '')[:10]}")
    lines += ["", "Queue as currently ranked by the formula (best first):"]
    for i, p in enumerate(picks, 1):
        lines.append(
            f"  {i}. key={p['key']} · \"{p['title']}\" · playlist={p.get('playlist')}"
            f" · {p.get('duration_sec') or '?'}s · episode {p.get('episode')}"
            f" · ranked because: {p['reason']}"
        )
    return "\n".join(lines)


def review(picks: list[dict[str, Any]]) -> dict[str, Any]:
    """One Claude call over the ranked picks. Returns a dict for the API."""
    if not picks:
        raise ReviewError("Nothing in the queue to review.")

    try:
        import anthropic
    except ModuleNotFoundError as exc:
        raise ReviewError(
            "The anthropic package is missing. Run:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install anthropic"
        ) from exc

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=(
                "You review the upload queue for a YouTube Shorts data-viz channel. "
                "The order you are given comes from a sound statistical ranking — "
                "only suggest moves a formula cannot see: timeliness against today's "
                "date or season, weak or strong titles, better narrative sequencing, "
                "over-long videos worth holding for a re-cut. Be concrete and terse; "
                "if the order is already right, say so rather than inventing changes. "
                "suggested_order must contain exactly the keys you were given."
            ),
            messages=[{"role": "user", "content": _context(picks)}],
            output_format=QueueReview,
        )
    except (anthropic.AuthenticationError, TypeError) as exc:
        # TypeError is the SDK's "no credentials at all" — raised before any request.
        raise ReviewError(
            "No Anthropic API key configured. Add ANTHROPIC_API_KEY=sk-ant-... to .env "
            "(get one at console.anthropic.com) and restart the dashboard."
        ) from exc
    except anthropic.APIStatusError as exc:
        raise ReviewError(f"Claude API error ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ReviewError("Could not reach the Claude API — check the network.") from exc

    if response.stop_reason == "refusal":
        raise ReviewError("The model declined to review this queue.")

    parsed: QueueReview = response.parsed_output
    known = {p["key"] for p in picks}
    order = [k for k in parsed.suggested_order if k in known]
    order += [p["key"] for p in picks if p["key"] not in order]  # never drop items

    return {
        "summary": parsed.summary,
        "items": [n.model_dump() for n in parsed.items if n.key in known],
        "suggested_order": order,
        "changed": order != [p["key"] for p in picks],
        "model": MODEL,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
