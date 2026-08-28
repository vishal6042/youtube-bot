"""Build curated football CSVs from martj42/international_results (CC0).

The raw dataset is one row per international match (1872-present) with
home/away teams and scores — no winner column, so the generic csv_url
fetcher cannot race it. This script rolls it up into the tidy
entity,year,value shape that `fetcher: curated_csv` expects, mirroring
what fetch._aggregate does for cricsheet:

    data/curated/football_wins.csv   cumulative match wins per team
    data/curated/football_goals.csv  cumulative goals scored per team

Draws count for neither team; unplayed/abandoned rows (blank scores) are
dropped. Re-run any time to refresh the snapshot:

    .venv/Scripts/python.exe scripts/curate_football.py
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

RAW_URL = ("https://raw.githubusercontent.com/martj42/"
           "international_results/master/results.csv")
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "curated"


def cumulate(df: pd.DataFrame, how: str) -> pd.DataFrame:
    """entity,year,value rows -> cumulative totals on a continuous year grid."""
    agg = df.groupby(["entity", "year"])["value"]
    per_year = (agg.size() if how == "count" else agg.sum()).unstack(fill_value=0)
    per_year = per_year.reindex(
        columns=range(int(df["year"].min()), int(df["year"].max()) + 1),
        fill_value=0,
    )
    out = per_year.cumsum(axis=1).stack().reset_index()
    out.columns = ["entity", "year", "value"]
    return out.astype({"value": int})


def main() -> None:
    resp = requests.get(RAW_URL, timeout=60)
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text))
    raw = raw.dropna(subset=["home_score", "away_score"])
    raw["year"] = raw["date"].str[:4].astype(int)

    home_win = raw["home_score"] > raw["away_score"]
    away_win = raw["away_score"] > raw["home_score"]
    wins = pd.DataFrame({
        "entity": pd.concat([raw.loc[home_win, "home_team"],
                             raw.loc[away_win, "away_team"]]),
        "year": pd.concat([raw.loc[home_win, "year"],
                           raw.loc[away_win, "year"]]),
        "value": 1,
    })

    goals = pd.DataFrame({
        "entity": pd.concat([raw["home_team"], raw["away_team"]]),
        "year": pd.concat([raw["year"], raw["year"]]),
        "value": pd.concat([raw["home_score"], raw["away_score"]]),
    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df, how in [("football_wins.csv", wins, "count"),
                          ("football_goals.csv", goals, "sum")]:
        tidy = cumulate(df, how)
        tidy.to_csv(OUT_DIR / name, index=False)
        top = tidy[tidy["year"] == tidy["year"].max()].nlargest(5, "value")
        print(f"{name}: {len(tidy)} rows, {tidy['entity'].nunique()} teams, "
              f"{tidy['year'].min()}-{tidy['year'].max()}")
        for _, r in top.iterrows():
            print(f"    {r['entity']}: {r['value']}")


if __name__ == "__main__":
    main()
