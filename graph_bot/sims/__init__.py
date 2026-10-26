"""Math in Motion: simulated, wordless Shorts (Galton board, chaos, Monte Carlo...).

Each simulation computes its whole timeline up front (every ball, every bounce),
then draws frames and synthesises a sound for each event, so picture and sound
always agree. Shared pieces live in `canvas` and `sound`. Topics use them with
``mode: sim`` and ``sim: <name>``; the series plan is docs/SERIES_math_in_motion.md.

    python -m graph_bot.sims galton out.mp4
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

# sim name -> module with render(out_path, ffmpeg, seed=..., progress=...) -> seconds
SIMS = {
    "galton": "graph_bot.sims.galton",
    "monty_hall": "graph_bot.sims.monty_hall",
    "monte_carlo_pi": "graph_bot.sims.monte_carlo_pi",
    "birthday": "graph_bot.sims.birthday",
}


def render_topic(topic: dict[str, Any], settings: dict[str, Any], out_path: Path) -> float:
    """Render a ``mode: sim`` topic to out_path (video and its sound). Returns seconds."""
    from ..render import ffmpeg_exe

    name = topic.get("sim")
    if name not in SIMS:
        raise ValueError(f"Unknown sim {name!r} for topic '{topic.get('key')}'. "
                         f"Built sims: {', '.join(SIMS)}")
    mod = importlib.import_module(SIMS[name])
    return mod.render(Path(out_path), ffmpeg_exe(settings), seed=int(topic.get("seed", 7)))
