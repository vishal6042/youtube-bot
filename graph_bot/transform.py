"""Reshape tidy data into what the renderers need.

- ``bar_race``  -> wide DataFrame: index = year, columns = top-N entities.
- ``line_grow`` -> DataFrame with a single 'value' column indexed by year.

Both apply the "last N years" window and fill gaps so animation is smooth even
when the source data is sparse (e.g. curated snapshots every 2 years).
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def prepare(df: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any]) -> tuple[str, pd.DataFrame]:
    """Return (mode, data) ready for rendering."""
    # Topics may narrow the window (e.g. AI data is only meaningful post-2010).
    window = int(topic.get("years_window") or settings.get("years_window", 50))
    mode = topic.get("mode", "bar_race")
    if mode == "line_multi":
        return "line_multi", _prepare_multi(df, topic, window)
    if mode == "line_grow":
        return "line_grow", _prepare_line(df, topic, window)
    if mode == "waffle_grow":
        # Same single-series shape as line_grow; the renderer draws it as a
        # 100-dot grid rather than a curve. With `people_code` it also gets a
        # population column and is drawn as one dot per million people.
        series = _prepare_line(df, topic, window)
        if topic.get("people_code"):
            series = _attach_people(series, topic, settings)
        return "waffle_grow", series
    if mode == "bump_race":
        # Same wide frame as bar_race — ranks are derived in the renderer.
        return "bump_race", _prepare_bar(df, topic, settings, window)
    return "bar_race", _prepare_bar(df, topic, settings, window)


def _window(df: pd.DataFrame, window: int) -> pd.DataFrame:
    max_year = int(df["year"].max())
    return df[df["year"] >= max_year - window + 1]


def _prepare_bar(df: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any], window: int) -> pd.DataFrame:
    top_n = int(topic.get("top_n") or settings.get("video", {}).get("top_n", 12))
    d = _window(df, window)

    wide = d.pivot_table(index="year", columns="entity", values="value", aggfunc="mean")
    # Fill to a continuous year index so bars move every frame.
    full_years = range(int(wide.index.min()), int(wide.index.max()) + 1)
    wide = wide.reindex(full_years)
    wide = wide.interpolate(method="linear", limit_direction="both")

    # Rank by the most recent year and keep the top N.
    final = wide.iloc[-1].dropna()
    top_entities = final.sort_values(ascending=False).head(top_n).index.tolist()
    wide = wide[top_entities]

    return wide.dropna(how="all")


def _prepare_multi(df: pd.DataFrame, topic: dict[str, Any], window: int) -> pd.DataFrame:
    """Head-to-head: a wide frame with one column per named entity.

    Unlike bar_race this keeps the entities the topic asked for, in that order,
    so "India vs China" always draws India first.
    """
    names = topic.get("entities")
    if not names:
        raise RuntimeError(f"mode 'line_multi' needs an `entities:` list ({topic.get('key')})")

    d = df[df["entity"].isin(names)]
    missing = [n for n in names if n not in set(d["entity"])]
    if missing:
        raise RuntimeError(f"entities not found in data for '{topic.get('key')}': {missing}")

    d = _window(d, window)
    wide = d.pivot_table(index="year", columns="entity", values="value", aggfunc="mean")
    full_years = range(int(wide.index.min()), int(wide.index.max()) + 1)
    wide = wide.reindex(full_years).interpolate(method="linear", limit_direction="both")
    return wide[[n for n in names if n in wide.columns]].dropna(how="all")


def _attach_people(series: pd.DataFrame, topic: dict[str, Any], settings: dict[str, Any]) -> pd.DataFrame:
    """Add a `people` column (millions) from a World Bank population indicator.

    Turns "share with X" into head counts: the people dot field needs to know
    how many people there were each year, not just the percentage.
    """
    from . import fetch

    code = topic["people_code"]
    entity = topic.get("entity_filter")
    if not entity:
        raise RuntimeError(f"`people_code` needs an `entity_filter` ({topic.get('key')})")
    # Shares the code-keyed cache file long-form chapters already use.
    pop = fetch.fetch({"key": "lf_" + code.lower().replace(".", "_"), "fetcher": "worldbank",
                       "code": code}, settings)
    pop = pop[pop["entity"] == entity].groupby("year")["value"].mean() / 1e6
    if pop.empty:
        raise RuntimeError(f"no {code} rows for '{entity}' ({topic.get('key')})")
    years = series.index
    pop = pop.reindex(range(min(int(pop.index.min()), int(years.min())),
                            max(int(pop.index.max()), int(years.max())) + 1))
    pop = pop.interpolate(limit_direction="both")
    out = series.copy()
    out["people"] = pop.reindex(years).values
    return out


def _prepare_line(df: pd.DataFrame, topic: dict[str, Any], window: int) -> pd.DataFrame:
    d = _window(df, window)

    entity_filter = topic.get("entity_filter")
    if entity_filter:
        d = d[d["entity"] == entity_filter]
        if d.empty:
            raise RuntimeError(
                f"entity_filter '{entity_filter}' matched no rows for topic '{topic.get('key')}'"
            )
        series = d.groupby("year")["value"].mean()
    else:
        # No filter -> global aggregate across all entities.
        series = d.groupby("year")["value"].sum()

    series = series.sort_index()
    full_years = range(int(series.index.min()), int(series.index.max()) + 1)
    series = series.reindex(full_years).interpolate(limit_direction="both")
    return series.to_frame("value")
