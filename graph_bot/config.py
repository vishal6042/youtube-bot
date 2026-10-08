"""Configuration + path helpers shared across the pipeline."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"

# Best-effort load of .env (for Meta tokens etc.); no-op if python-dotenv missing.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # pragma: no cover
    pass


def env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable (populated from .env)."""
    return os.environ.get(name, default)


def load_settings() -> dict[str, Any]:
    with open(CONFIG_DIR / "settings.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# topics.yaml is parsed on nearly every helper call (topic_episode looks up its
# peers, for one), so a 26KB YAML parse per topic added up to seconds. Cache on
# the file's mtime+size: edits are picked up, repeat calls are free.
_TOPICS_CACHE: dict[str, Any] = {"stamp": None, "data": []}


def load_topics() -> list[dict[str, Any]]:
    path = CONFIG_DIR / "topics.yaml"
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None

    if stamp is not None and _TOPICS_CACHE["stamp"] == stamp:
        return _TOPICS_CACHE["data"]

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    topics = data.get("topics", [])
    _TOPICS_CACHE["stamp"] = stamp
    _TOPICS_CACHE["data"] = topics
    return topics


def get_topic(key: str) -> dict[str, Any]:
    for topic in load_topics():
        if topic.get("key") == key:
            return topic
    available = ", ".join(t.get("key", "?") for t in load_topics())
    raise KeyError(f"Topic '{key}' not found. Available: {available}")


# Series a topic belongs to -> the playlist it should be published into.
SERIES_WORLD = "world_in_data"
SERIES_AI = "ai_trends"
SERIES_ML = "ml_concept"
SERIES_MONEY = "money"
SERIES_CHARTS = "charts_lie"
SERIES_INDIA = "india_in_data"
SERIES_SPORTS = "sports"
SERIES_VS = "country_vs_country"


def topic_series(topic: dict[str, Any]) -> str:
    """Which series/playlist a topic belongs to.

    Honours an explicit ``series:`` in topics.yaml; otherwise infers it:
      * key starting ``ai_``            -> ai_trends
      * key starting ``ml_`` or a Manim scene -> ml_concept
      * key starting ``vs_``            -> country_vs_country
      * everything else                 -> world_in_data
    """
    explicit = topic.get("series")
    if explicit:
        return str(explicit)

    key = str(topic.get("key", ""))
    if key.startswith("ai_"):
        return SERIES_AI
    if key.startswith("india_"):
        return SERIES_INDIA
    if key.startswith("money_"):
        return SERIES_MONEY
    if key.startswith("lie_"):
        return SERIES_CHARTS
    if key.startswith(("cricket_", "football_")):
        return SERIES_SPORTS
    # The older india_vs_china_* topics stay in India in Data: they are
    # published there, and the `india_` rule above catches them first.
    if key.startswith("vs_"):
        return SERIES_VS
    if key.startswith("ml_") or topic.get("mode") == "manim":
        return SERIES_ML
    return SERIES_WORLD


def topic_episode(topic: dict[str, Any]) -> int:
    """Episode number of a topic within its series.

    Resolution order:
      1. explicit ``episode:`` in topics.yaml
      2. a ``#N`` in the subtitle (e.g. "ML Basics #7")
      3. its 1-based position among the topics of the same series, in
         topics.yaml order — so every video gets a stable number for free.
    """
    explicit = topic.get("episode")
    if explicit is not None:
        return int(explicit)

    match = re.search(r"#(\d+)", str(topic.get("subtitle", "")))
    if match:
        return int(match.group(1))

    series = topic_series(topic)
    peers = [t for t in load_topics() if topic_series(t) == series]
    for i, t in enumerate(peers, 1):
        if t.get("key") == topic.get("key"):
            return i
    return 1


def resolve_path(settings: dict[str, Any], which: str) -> Path:
    """Resolve a configured path (cache/curated/output) to an absolute Path."""
    rel = settings.get("paths", {}).get(which, which)
    path = PROJECT_ROOT / rel
    path.mkdir(parents=True, exist_ok=True)
    return path
