"""Data fetchers.

Every fetcher returns a *tidy* DataFrame with exactly three columns:

    entity (str)  |  year (int)  |  value (float)

A topic's ``fetcher`` field selects the backend. Results are cached to disk so
re-runs (and iterating on the render) don't re-hit the network.
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import resolve_path

TIDY_COLS = ["entity", "year", "value"]
_TIMEOUT = 60

# World Bank's /country/all endpoint mixes real countries with regional and
# income-group aggregates. For country bar-races we drop these iso3 codes.
_WB_AGGREGATES = {
    "AFE", "AFW", "ARB", "CEB", "CSS", "EAP", "EAR", "EAS", "ECA", "ECS",
    "EMU", "EUU", "FCS", "HIC", "HPC", "IBD", "IBT", "IDA", "IDB", "IDX",
    "INX", "LAC", "LCN", "LDC", "LIC", "LMC", "LMY", "LTE", "MEA", "MIC",
    "MNA", "NAC", "OED", "OSS", "PRE", "PSS", "PST", "SAS", "SSA", "SSF",
    "SST", "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "UMC", "WLD",
}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def fetch(topic: dict[str, Any], settings: dict[str, Any], *, refresh: bool = False) -> pd.DataFrame:
    """Fetch tidy data for a topic, using an on-disk cache."""
    cache_dir = resolve_path(settings, "cache")
    cache_file = cache_dir / f"{topic['key']}.csv"

    if cache_file.exists() and not refresh:
        df = pd.read_csv(cache_file)
        return _clip_years(_coerce_tidy(df), topic)

    fetcher = topic.get("fetcher")
    if fetcher == "worldbank":
        df = _fetch_worldbank(topic["code"])
    elif fetcher == "owid":
        df = _fetch_owid(topic["slug"], topic.get("value_column"))
    elif fetcher == "dbnomics":
        df = _fetch_dbnomics(topic["series_url"])
    elif fetcher == "curated_csv":
        df = _fetch_curated(topic["file"], resolve_path(settings, "curated"))
    elif fetcher == "csv_url":
        df = _fetch_csv_url(topic)
    elif fetcher == "cricsheet":
        df = _fetch_cricsheet(topic)
    else:
        raise ValueError(f"Unknown fetcher: {fetcher!r} (topic {topic.get('key')})")

    df = _coerce_tidy(df)
    if df.empty:
        raise RuntimeError(f"No data returned for topic '{topic.get('key')}'")
    df.to_csv(cache_file, index=False)
    return _clip_years(df, topic)


def _clip_years(df: pd.DataFrame, topic: dict[str, Any]) -> pd.DataFrame:
    """Apply ``year_min`` / ``year_max`` to any fetcher's output.

    Trimming happens on the way out rather than before the cache is written, so
    changing the window in topics.yaml takes effect on the next render without
    needing ``--refresh``. ``_fetch_csv_url`` also trims internally because its
    aggregations (cumcount, cummax) must run on the already-windowed rows; the
    two passes agree, so applying it twice is harmless.
    """
    lo, hi = topic.get("year_min"), topic.get("year_max")
    if lo is None and hi is None:
        return df
    if lo is not None:
        df = df[df["year"] >= int(lo)]
    if hi is not None:
        df = df[df["year"] <= int(hi)]
    if df.empty:
        raise RuntimeError(
            f"Topic '{topic.get('key')}' has no rows left after applying "
            f"year_min={lo} / year_max={hi} — check the window against the source."
        )
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
def _fetch_worldbank(code: str) -> pd.DataFrame:
    url = (
        f"https://api.worldbank.org/v2/country/all/indicator/{code}"
        "?format=json&per_page=20000"
    )
    payload = requests.get(url, timeout=_TIMEOUT).json()
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        raise RuntimeError(f"World Bank returned no data for indicator {code}")

    rows = []
    for item in payload[1]:
        iso3 = item.get("countryiso3code") or ""
        if not iso3 or iso3 in _WB_AGGREGATES:
            continue
        if item.get("value") is None:
            continue
        rows.append(
            {
                "entity": item["country"]["value"],
                "year": int(item["date"]),
                "value": float(item["value"]),
            }
        )
    return pd.DataFrame(rows, columns=TIDY_COLS)


def _fetch_owid(slug: str, value_column: str | None = None) -> pd.DataFrame:
    url = (
        f"https://ourworldindata.org/grapher/{slug}.csv"
        "?v=1&csvType=full&useColumnShortNames=false"
    )
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "graph_bot/0.1"})
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text))

    # OWID CSVs are: Entity, Code, Year, <one or more value columns>.
    meta_cols = {"Entity", "Code", "Year"}
    value_cols = [c for c in raw.columns if c not in meta_cols]
    if not value_cols:
        raise RuntimeError(f"OWID chart '{slug}' has no value column")
    col = value_column if value_column in value_cols else value_cols[0]

    df = raw.rename(columns={"Entity": "entity", "Year": "year", col: "value"})
    df = df[["entity", "Code", "year", "value"]].dropna(subset=["value"])
    # Drop OWID aggregate rows (regions/income groups have no ISO code or an
    # OWID_* pseudo-code). Keep real countries (3-letter ISO).
    df = df[df["Code"].apply(_is_real_iso3)]
    return df[TIDY_COLS]


def _fetch_dbnomics(series_url: str) -> pd.DataFrame:
    resp = requests.get(series_url, timeout=_TIMEOUT)
    resp.raise_for_status()
    docs = resp.json().get("series", {}).get("docs", [])
    rows = []
    for doc in docs:
        # Label the entity from the first dimension label if available.
        labels = doc.get("dimensions_labels") or {}
        entity = (
            next(iter(labels.values()), None)
            or doc.get("series_name")
            or doc.get("series_code")
            or "series"
        )
        for period, value in zip(doc.get("period", []), doc.get("value", [])):
            if value is None:
                continue
            year = int(str(period)[:4])
            rows.append({"entity": entity, "year": year, "value": float(value)})
    return pd.DataFrame(rows, columns=TIDY_COLS)


# Long official country names -> short display names (for chart labels).
_SHORT_NAMES = {
    "United States of America": "United States",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "Korea (Republic of)": "South Korea",
    "Russian Federation": "Russia",
    "Iran (Islamic Republic of)": "Iran",
    "Taiwan, Province of China": "Taiwan",
    "Viet Nam": "Vietnam",
}


def _clean_entity(value: Any, how: str | None) -> str:
    """Normalise an entity label. how='country' takes the primary (first) entry."""
    text = str(value).strip()
    if how == "country":
        # Fields like "United States of America,France" list every author's country;
        # attribute the model to the primary (first) one.
        text = text.split(",")[0].strip()
    return _SHORT_NAMES.get(text, text)


def _fetch_csv_url(topic: dict[str, Any]) -> pd.DataFrame:
    """Generic fetcher for any public CSV, with optional aggregation.

    Config keys: url, entity_col | entity_label, date_col | year_col, value_col,
    agg (none|count|cumcount|sum|max|cummax), entity_clean, year_min, year_max.
    """
    url = topic["url"]
    resp = requests.get(url, timeout=120, headers={"User-Agent": "graph_bot/0.1"})
    resp.raise_for_status()

    if url.lower().endswith(".zip"):
        # Several providers (e.g. Epoch AI) ship datasets as a zipped bundle.
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            member = topic.get("zip_member")
            if not member:
                csvs = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                if not csvs:
                    raise RuntimeError(f"No CSV inside {url}")
                member = csvs[0]
            with archive.open(member) as fh:
                raw = pd.read_csv(fh, low_memory=False)
    else:
        raw = pd.read_csv(io.StringIO(resp.text), low_memory=False)

    # --- year ---
    if topic.get("year_col"):
        years = pd.to_numeric(raw[topic["year_col"]], errors="coerce")
    else:
        years = pd.to_datetime(raw[topic["date_col"]], errors="coerce", format="mixed").dt.year
    df = pd.DataFrame({"year": years})

    # --- entity ---
    if topic.get("entity_col"):
        df["entity"] = raw[topic["entity_col"]].apply(
            lambda v: _clean_entity(v, topic.get("entity_clean"))
        )
        df.loc[raw[topic["entity_col"]].isna(), "entity"] = None
        # Raw source labels are often unreadable on screen ("Yes"/"No" for a
        # flag column). `entity_map: {old: new}` renames them before
        # aggregation, exactly as it does for renamed cricket franchises.
        if topic.get("entity_map"):
            df["entity"] = df["entity"].replace(topic["entity_map"])
    else:
        df["entity"] = topic.get("entity_label", "All")

    # --- value ---
    agg = topic.get("agg", "none")
    if topic.get("value_col"):
        df["value"] = pd.to_numeric(raw[topic["value_col"]], errors="coerce")
    else:
        df["value"] = 1.0  # counting rows

    needs_value = agg in {"sum", "max", "cummax", "cumsum", "none"}
    df = df.dropna(subset=["year", "entity"] + (["value"] if needs_value else []))
    df["year"] = df["year"].astype(int)

    # Optional year bounds (e.g. drop an incomplete current year).
    if topic.get("year_min") is not None:
        df = df[df["year"] >= int(topic["year_min"])]
    if topic.get("year_max") is not None:
        df = df[df["year"] <= int(topic["year_max"])]
    if df.empty:
        raise RuntimeError(f"csv_url: no rows left after filtering for '{topic.get('key')}'")

    return _aggregate(df, agg)


def _fetch_cricsheet(topic: dict[str, Any]) -> pd.DataFrame:
    """Match results from a Cricsheet CSV archive (ODC-BY — credit it in `source`).

    Cricsheet ships one file per match rather than a combined table, so
    ``_fetch_csv_url``'s single ``zip_member`` cannot read it. Each
    ``<id>_info.csv`` is a long ``info,<key>,<value>`` file; we pull the winner
    and date out of every one and emit a row per decided match, which
    ``_aggregate`` then rolls up (``agg: cumcount`` gives cumulative wins).

    Topic keys: ``url`` (the archive), optional ``count`` — ``winner``
    (default), ``toss_winner`` or ``player_of_match``.

    Ties and no-results have no winner row and are skipped, so totals are wins,
    not appearances.
    """
    field = topic.get("count", "winner")
    resp = requests.get(topic["url"], timeout=_TIMEOUT * 3)
    resp.raise_for_status()

    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if not name.endswith("_info.csv"):
                continue
            date = winner = None
            text = zf.read(name).decode("utf-8", errors="replace")
            for parts in csv.reader(io.StringIO(text)):
                # Rows are `info,<key>,<value>`; some carry a trailing extra
                # column (e.g. `info,player,<team>,<name>`) which we ignore.
                if len(parts) < 3 or parts[0] != "info":
                    continue
                if parts[1] == "date" and date is None:
                    date = parts[2].strip()
                elif parts[1] == field:
                    winner = parts[2].strip()
            if date and winner:
                rows.append({"entity": winner, "year": int(date[:4]), "value": 1.0})

    if not rows:
        raise RuntimeError(
            f"No decided matches found in {topic['url']} — check the archive "
            f"still ships `<id>_info.csv` members."
        )
    df = pd.DataFrame(rows, columns=TIDY_COLS)
    # Cricsheet records the name a team had at match time, so a renamed
    # franchise splits into two entities and an "all-time" total is wrong.
    # `entity_map: {old: new}` in the topic merges them before aggregation.
    if topic.get("entity_map"):
        df["entity"] = df["entity"].replace(topic["entity_map"])
    return _aggregate(df, topic.get("agg", "none"))


def _aggregate(df: pd.DataFrame, agg: str) -> pd.DataFrame:
    if agg == "none":
        return df[TIDY_COLS]
    if agg in {"sum", "max", "count"}:
        how = {"sum": "sum", "max": "max", "count": "size"}[agg]
        out = df.groupby(["entity", "year"]).agg(value=("value", how)).reset_index()
        return out[TIDY_COLS]
    if agg == "cummax":
        # Running maximum across years (a "frontier" curve); single series.
        per_year = df.groupby(["entity", "year"])["value"].max().reset_index()
        per_year = per_year.sort_values("year")
        per_year["value"] = per_year.groupby("entity")["value"].cummax()
        return per_year[TIDY_COLS]
    if agg == "cumsum":
        # Running total of a value over time (e.g. data-centre power added each year).
        per_year = df.groupby(["entity", "year"])["value"].sum().unstack(fill_value=0.0)
        full_years = range(int(df["year"].min()), int(df["year"].max()) + 1)
        per_year = per_year.reindex(columns=full_years, fill_value=0.0)
        out = per_year.cumsum(axis=1).stack().reset_index()
        out.columns = ["entity", "year", "value"]
        return out[TIDY_COLS]
    if agg == "cumcount":
        # Cumulative count per entity over a continuous year grid.
        counts = df.groupby(["entity", "year"]).size().unstack(fill_value=0)
        full_years = range(int(df["year"].min()), int(df["year"].max()) + 1)
        counts = counts.reindex(columns=full_years, fill_value=0)
        cum = counts.cumsum(axis=1)
        out = cum.stack().reset_index()
        out.columns = ["entity", "year", "value"]
        return out[TIDY_COLS]
    raise ValueError(f"Unknown agg: {agg!r}")


def _fetch_curated(file: str, curated_dir: Path) -> pd.DataFrame:
    path = curated_dir / file
    if not path.exists():
        raise FileNotFoundError(f"Curated data file not found: {path}")
    df = pd.read_csv(path)
    return df.rename(columns={c: c.lower() for c in df.columns})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _is_real_iso3(code: Any) -> bool:
    return isinstance(code, str) and len(code) == 3 and code.isalpha() and not code.startswith("OWID")


def _coerce_tidy(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in TIDY_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Fetched data missing columns {missing}; got {list(df.columns)}")
    out = df[TIDY_COLS].copy()
    out["year"] = out["year"].astype(int)
    out["value"] = out["value"].astype(float)
    out["entity"] = out["entity"].astype(str)
    return out.dropna()
