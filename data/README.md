# data/

Operational state (uploads, discards, queue order, job history) lives in
**Postgres** — see `graph_bot/store/` and `python -m graph_bot.store status`.

The JSON files here are the **pre-migration backup** (migrated 2026-08-29) and are
no longer read at runtime. `python -m graph_bot.store export` rewrites the same
shapes into `data/export/` from the database, which is the escape hatch if you
ever need to go back.

Still plain files, deliberately:
- `brand.json`   — channel/playlist copy, hand-edited config
- `cache/`, `music_cache/`, `manim_media/`, `flags/`, `curated/` — caches and assets
