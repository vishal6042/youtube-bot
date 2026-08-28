# Series draft — "India in Data" (pillar #6)

Series key: `india` (topic keys prefixed `india_`). Playlist: **India in Data**.

Why this pillar: a large, underserved audience; far less competition than generic
world stats; and a clear geographic niche is exactly the signal the algorithm
rewards. "India vs China" is the flagship format.

---

## Tier 1 — India vs China (the flagship, launch with these)

Head-to-head: two countries only. Maximum tribal appeal, maximum comments.

| # | Title | The story | Data |
|---|---|---|---|
| 1 | **India Just Overtook China** | The 2023 population crossover — a genuinely historic moment, and the lines actually cross on screen | World Bank `SP.POP.TOTL` |
| 2 | **India vs China: The Economy** | China pulls far ahead from ~1990; shows the gap honestly | `NY.GDP.MKTP.CD` |
| 3 | **India vs China: Who Lives Longer?** | Life expectancy — closer than people expect | OWID `life-expectancy` |
| 4 | **India vs China: Who Pollutes More?** | Total vs per-person flips the answer completely | OWID CO₂ + per-capita |
| 5 | **India vs China: Getting Online** | Internet adoption race | `IT.NET.USER.ZS` |

## Tier 2 — India's rise (single-country growth stories)

| # | Title | The story | Data |
|---|---|---|---|
| 6 | **India's Economy: 50 Years in 30 Seconds** | The 1991 liberalisation inflection is visible | `NY.GDP.MKTP.CD` |
| 7 | **India Got Online** | Internet users 0 → ~900M | `IT.NET.USER.ZS` |
| 8 | **The Mobile Phone Revolution** | One of the fastest tech adoptions in history | `IT.CEL.SETS` |
| 9 | **India Learned to Read** | Literacy climb since independence | `SE.ADT.LITR.ZS` |
| 10 | **India's Life Expectancy Doubled** | ~32 years at independence → 70+ | OWID |
| 11 | **India's Poverty Collapse** | Hundreds of millions lifted out of extreme poverty | `SI.POV.DDAY` |

## Tier 3 — India's place in the world

| # | Title | The story | Data |
|---|---|---|---|
| 12 | **What Is India #1 At?** | India's global rank across many indicators | multiple |
| 13 | **India's Share of Humanity** | % of world population over time | World Bank |
| 14 | **India's Software Developers** | The IT boom, and the projected overtake of the US | SlashData / Octoverse (curated) |

## Tier 4 — Inside India (state-level; needs a new data source)

| # | Title | Data |
|---|---|---|
| 15 | **Richest Indian States** | GSDP — RBI / MoSPI / data.gov.in |
| 16 | **Most Populous States** | Census of India |
| 17 | **Most Literate States** | Census / NITI Aayog |

## Tier 5 — Culture

| # | Title | Data |
|---|---|---|
| 18 | **India Makes the Most Films** | Feature films produced — UNESCO UIS (India leads the world) |
| 19 | **Cricket, in Numbers** | ESPNcricinfo / Kaggle datasets (curated) |

---

## Build notes / honest costs

- **Tiers 2–3 work with the pipeline as-is** — `line_grow` already supports
  `entity_filter: "India"`. These are pure config, near-zero build cost.
- **Tier 1 (head-to-head) needs one small feature**: an `entities:` list so a
  bar_race/line can show exactly two named countries. Worth building — it also
  unlocks head-to-heads for every other pillar (US vs China, etc.).
- **Tier 4 needs a new data source** — state-level data isn't in World Bank.
  `data.gov.in` publishes CSVs that the existing `csv_url` fetcher can read;
  otherwise a curated CSV. Highest effort of the set.
- **#18 (films)** finally gives the long-parked UNESCO/DBnomics film topic a home.

## Suggested launch order

**1 → 6 → 8 → 4 → 2.** Lead with the population crossover (historic + the lines
literally cross), then the growth stories, then the CO₂ twist which is the most
argued-about. Save state-level for once the pillar has traction.

## Tone note

Celebrate the progress honestly, but don't hide the gaps — the GDP gap with China
is real, and pretending otherwise costs credibility with the exact audience most
likely to subscribe.
