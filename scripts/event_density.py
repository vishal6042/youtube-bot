"""Score a topic's "event density" before spending a render on it.

Retention on a race chart comes from having a next event to wait for. The
channel's own analytics say so: `bar_race` holds 25.8% of a video while a 26s
`line_grow` — one line, one event, at the end — holds 14.1% and gets a quarter
of the views (docs/CONTENT_STRATEGY.md, findings 4 and 8).

That property is measurable straight off the cached CSV, before rendering:

    lead changes    how often the #1 entity changes hands   -> bar_race
    distinct top-3  how many entities ever reach the top 3  -> bump_race

A topic scoring 0-1 lead changes is flat: Test-match wins looks like a great
race until you count them and find Australia in front in 23 of 24 years. Such a
topic needs re-framing (race for second place) or a short `line_grow` cut, not a
15-second race.

Usage:
    python scripts/event_density.py rank_inflation      # one topic
    python scripts/event_density.py --all               # every cached topic
    python scripts/event_density.py --all --min 2       # only flat ones
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / "data" / "cache"


def score(key: str) -> dict[str, object] | None:
    """Lead changes and top-3 churn for one cached topic, or None if unusable."""
    path = CACHE / f"{key}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if not {"entity", "year", "value"} <= set(df.columns):
        return None  # manim topics and odd shapes have no race to score

    leader = df.sort_values("value", ascending=False).groupby("year").first()["entity"]
    changes = sum(a != b for a, b in zip(leader.values, leader.values[1:]))
    top3 = {e for _, g in df.groupby("year") for e in g.nlargest(3, "value")["entity"]}
    return {
        "key": key,
        "years": f"{df['year'].min()}-{df['year'].max()}",
        "changes": changes,
        "top3": len(top3),
        "leader": leader.iloc[-1],
    }


def verdict(row: dict[str, object]) -> str:
    changes, top3 = int(row["changes"]), int(row["top3"])
    if changes >= 5:
        return "strong bar_race"
    if changes >= 2:
        return "ok bar_race"
    if top3 >= 6:
        return "flat #1 - bump_race or race-for-2nd"
    return "FLAT - re-frame or cut short"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("key", nargs="?", help="topic key (matches data/cache/<key>.csv)")
    ap.add_argument("--all", action="store_true", help="score every cached topic")
    ap.add_argument("--min", type=int, default=None,
                    help="only show topics with FEWER lead changes than this")
    args = ap.parse_args()

    if not args.key and not args.all:
        ap.error("give a topic key or --all")

    keys = sorted(p.stem for p in CACHE.glob("*.csv")) if args.all else [args.key]
    rows = [r for r in (score(k) for k in keys) if r]
    if not rows:
        print(f"no scoreable data for {args.key!r} (missing cache, or not a race topic)")
        return 1

    rows.sort(key=lambda r: (-int(r["changes"]), -int(r["top3"])))
    print("%-26s %-11s %7s %7s  %-34s %s"
          % ("topic", "years", "changes", "top3", "verdict", "leader"))
    for r in rows:
        if args.min is not None and int(r["changes"]) >= args.min:
            continue
        print("%-26s %-11s %7d %7d  %-34s %s"
              % (r["key"], r["years"], r["changes"], r["top3"], verdict(r), r["leader"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
