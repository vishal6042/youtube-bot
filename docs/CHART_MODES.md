# Chart modes plan — beyond bar_race and line_grow

**Ground rule: already-exported/uploaded videos are never re-rendered or
modified.** New modes are for FUTURE videos only. Where a live dataset deserves
a second look in a new form, it becomes a **new topic key** (a re-cut), never an
edit of an existing one.

Today `render.py` dispatches three modes: `bar_race`, `line_grow`,
`line_multi` (dispatch at the top of `render()`), all fed the same tidy
`entity,year,value` frame. Every mode below slots into that dispatch.

---

## Pick the chart from the data, not the other way round

Profiled all 49 cached datasets (scratch script; signals: rank churn/yr in the
top 10 over the last 30 years, lead changes at #1, %-bounded values, monotonic
cumulative shape). The heuristic:

| Data shape | Best mode | Why |
|---|---|---|
| Many entities, HIGH rank churn (≥3 swaps/yr) or #1 changes hands | `bump_race` | The overtakes ARE the story; bars hide mid-table drama |
| Many entities, LOW churn (<1.5) | `bar_race` (or skip) | A race no one overtakes in is a list |
| Bounded % / share of a whole | `waffle_grow` | "X of 100 people" reads emotionally; axes don't |
| Composition of a total shifting | `stream_share` | Parts-of-whole over time; bars can't show mix |
| Single monotonic series | `line_grow` (have it) | Already the right tool |
| 2 entities, one crossing | `line_multi` (have it) | Already the right tool |
| Seasonal/monthly cycle | `spiral_loop` | Perfect visual loop → the 110%-retention band |
| Two indicators + size per entity | `gapminder` | Health-vs-wealth motion, nothing else shows it |

## Mode roadmap (priority order)

1. **`bump_race`** — rank lines that cross on overtakes. Zero data-layer work
   (ranks computed in transform from the same frame). *Build first.*
2. **`waffle_grow`** — 100-dot grid recoloring as a % moves. Needs only a
   single %-series (entity_filter or global). *Build second.*
3. **`stream_share`** — stacked-area / streamgraph of composition. Same frame,
   values normalized to share-of-year. 
4. **`spiral_loop`** — Ed-Hawkins-style radial spiral. Needs MONTHLY data
   (new fetch: OWID temperature anomaly / HadCRUT). One-off but loops
   perfectly, and looping 6–9s videos are the channel's retention champions.
5. **`gapminder`** — animated scatter, bubble = population. Needs a
   multi-indicator frame (x, y, size per entity/year) — the only mode
   requiring fetch-layer changes. gdp_per_capita + life_expectancy +
   population are all already cached, so the data exists locally.
6. **`map_fill`** (parked) — choropleth filling in over time. Fights the 9:16
   frame; needs geopandas + shapefiles. Revisit only with a strong concept.

**Avoid:** radial/circular bar races — length distortion is exactly what the
How Charts Lie pillar teaches against.

## What the profiling actually found (evidence for the assignments)

- **`money_inflation`** — #1 changed hands **19×** in 30 years (churn 5.0):
  the most bump-race-shaped dataset in the whole cache.
- **`money_inequality`** — 20 lead changes. **`money_unemployment`** — churn
  5.0, 5 lead changes. The money pillar is overtake country.
- **`gdp`** — churn 2.3 but **zero** #1 changes (US never passed): the *story*
  is mid-table — Japan sliding, India climbing — which bars under-show and
  rank-lines nail.
- **`ai_orgs`** (churn 5.3, 4 lead changes) and **`ai_cluster_owners`** (5.0,
  4) — the AI leaderboard genuinely flips; strong bump re-cuts for the
  strongest pillar.
- **`india_internet` / `money_poverty`** — %-bounded with huge sweep
  (poverty's "#1" changed 28× — ranking noise, NOT a race; it's a share
  story → waffle).
- **`forest` (churn 0.2), `population` (0.5), `patents` (1.7)** — static
  rankings; confirms low-churn topics make dull races (patents/science stalled
  ~51 views). The churn number is now a go/no-go check for any future
  bar_race or bump_race topic.

## Future video candidates (all NEW keys — nothing live is touched)

| New key | Mode | Source data | Hook |
|---|---|---|---|
| `rank_economies` | bump_race | gdp (cached) | "India's climb up the GDP table" — Japan falls, India rises |
| `rank_inflation` | bump_race | money_inflation | The inflation crown changed heads 19 times |
| `rank_ai_orgs` | bump_race | ai_orgs | Who led AI, year by year |
| `world_online_100` | waffle_grow | internet users % (global) | "In 1995, 1 of these 100 people was online" |
| `poverty_100` | waffle_grow | money_poverty (global) | Dots leaving poverty, 1990→today |
| `energy_mix` | stream_share | new OWID slug (energy by source) | Coal's share melting, solar's growing |
| `ai_model_share` | stream_share | ai_countries (cached) | US vs China share of new models |
| `temp_spiral` | spiral_loop | new monthly HadCRUT/OWID fetch | The climate spiral — born to loop |
| `health_wealth` | gapminder | 3 cached indicators combined | 200 countries, 50 years, one chart |

## Sequencing

Build `bump_race` when the next production window opens (upload queue under a
week), ship `rank_economies` as the pilot, and read its analytics before
building mode #2. One new mode proven at a time — same discipline as pillars.
