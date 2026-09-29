# Content strategy — what the channel's own analytics say

Built from `analytics_data/_new/Table data.csv` (YouTube Studio export, **2026-05-29 →
2026-08-27**) joined to `data/upload_log.json` → `config/topics.yaml`, so every claim
below is tied to a render mode and a topic key rather than to general Shorts advice.
Every number in the concepts and scripts was checked against `data/cache/<key>.csv`.

**Baseline:** 49 published videos · 20,646 views · 36.06 watch-hours · 72 subscribers ·
14,301 thumbnail impressions · 2.52% CTR.

---

## 1. What the data actually says

### Finding 1 — Thumbnails are worth ~2% of your views. Frame 0 is the real thumbnail.

14,301 impressions × 2.52% CTR = **~360 views from thumbnails**, out of 20,646 total.
The other **~98% arrived through the Shorts feed**, where the video is already playing
and no thumbnail is ever shown.

> Consequence: CTR work is a rounding error on this channel today. The first *frame* and
> first *second* of the video carry the load a thumbnail would carry elsewhere. Thumbnail
> concepts still appear below — they matter for the ~2% and for the channel page — but
> they are not where the leverage is.

### Finding 2 — Every video gets ~6 seconds watched, whatever its length

| | median |
|---|---|
| Average view duration, all 49 | **6.1s** |
| p90 average view duration | 8.7s |
| Video duration | 26s |

The median video is 26s and gets 6.1s watched: **roughly three quarters of every render
is never seen.** `config/settings.yaml` sets `target_seconds: 24`, which is why almost
everything is 26s.

### Finding 3 — Shorter videos win on both retention and views

| duration | n | median views | median retention | median AVD |
|---|---|---|---|---|
| under 10s | 6 | **642** | **33.7%** | 2.8s |
| 11-26s | 33 | 253 | 23.8% | 6.2s |
| 27-32s | 7 | 63 | 22.8% | 7.1s |
| 33s+ | 3 | 50 | 14.4% | 5.5s |

**Confound, stated honestly:** the sub-10s bucket is almost entirely AI topics
(`ai_params`, `ai_cost`, `ai_boom`, `ai_orgs`), which may have won on subject matter
rather than length. Length and topic are not separable in this dataset. Section 6 gives
the experiment that separates them. What *is* unconfounded is Finding 2: nobody is
watching past ~8s regardless.

### Finding 4 — `line_grow` at 26s is the single worst thing the pipeline makes

| mode | n | median views | median retention | median CTR |
|---|---|---|---|---|
| `bar_race` | 21 | 294 | 25.8% | **3.24%** |
| `line_multi` | 4 | 513 | 21.0% | 3.13% |
| `manim` | 11 | 54 | 22.1% | 1.23% |
| `line_grow` | 10 | 91 | 20.9% | 2.04% |

Split `line_grow` by length and it falls apart:

| `line_grow` | n | median views | median retention |
|---|---|---|---|
| under 12s | 4 | **642** | 32.9% |
| 13s+ | 6 | **68** | 14.1% |

The bottom of the retention table is four long `line_grow` / `line_multi` videos:
*India's Economy: 50 Years in 30 Seconds* (9.6%), *How India Got Online* (10.0%),
*India vs China: Getting Online* (9.5%), *How Much Power Does AI Use?* (13.2%).

**Why this is mechanical, not bad luck:** a bar race has a lead change every few seconds
— there is always a next event to wait for. One line growing across 26 seconds has
exactly one event, at the end. There is nothing to anticipate, so viewers leave at the
first flat stretch.

That is the intuitive story, and Finding 8 tests it directly. It does not survive — which
matters, because it is exactly the kind of rule that sounds right and quietly misdirects a
year of production.

### Finding 5 — Title patterns move CTR 9x (0.53% to 4.72%)

| best CTR | | worst CTR (300+ impressions) | |
|---|---|---|---|
| India Just Overtook China | **4.72%** | Where Prices Exploded | 0.53% |
| The World's Biggest Economies | 4.65% | The Mistake Beginners Make (ML Basics) | 0.64% |
| India vs China: The Economy | 4.10% | Supervised vs Unsupervised (ML Basics) | 0.71% |
| How BIG Are AI Models? | 3.44% | Features vs Labels Explained (ML Basics) | 0.78% |
| The Richest Countries Per Person | 3.24% | Bias vs Variance Explained (ML Basics) | 1.08% |

Winners share three things: a **named entity the viewer already has feelings about**
(India, China, "countries"), a **superlative or a verb of conflict** (Biggest, Richest,
*Just Overtook*), and **money or size as the unit**. Losers are abstractions with no
entity — note that "vs" alone does nothing: *Supervised vs Unsupervised* is 0.71%,
*India vs China* is 4.10%. The "vs" needs opponents the viewer can root for.

### Finding 6 — ML Basics is your best converter and your worst reach

| series | n | median views | median CTR | **subs per 1k views** |
|---|---|---|---|---|
| ML Basics | 10 | 52 | 1.23% | **4.10** |
| India | 4 | 132 | 2.19% | 1.26 |
| Money | 5 | 271 | 2.44% | 0.79 |
| AI | 18 | 190 | 2.52% | 0.40 |
| World | 9 | 754 | 1.92% | 0.00 |
| Sports | 2 | **850** | **4.37%** | 0.00 |

ML Basics converts **10x better than AI**, and zero subscribers came from World or Sports
at all. The two ends of the channel do different jobs: **World/Sports/AI buy reach, ML
Basics buys subscribers.** Killing ML Basics for its view count would be a mistake; it is
the only thing on the channel that turns a view into a subscriber.

One ML Basics video escaped the series' packaging problem entirely:

> **99% Accurate and Totally Useless | ML Basics** — 1,492 views, 4 subscribers,
> 20.4% retention on a **47-second** video. Its 9 siblings average 52 views.

It is the *only* one whose title is a paradox instead of a textbook term. That title is
the template for the whole series (concepts 8 and 9).

### Finding 7 — Sports is the best-performing series and it has 2 videos

Median 850 views, 4.37% CTR, on **83 and 51 impressions** — essentially pure Shorts-feed
distribution. Meanwhile `config/topics.yaml` has **four cricket topics already configured
and never rendered**. Caveat: n = 2. Highest-upside, lowest-cost test on the channel, not
a proven law.

### Finding 8 — The obvious retention theory is wrong. I tested it; it failed.

Finding 4's mechanism (races retain because the lead keeps changing) is measurable before
rendering: count how often the #1 entity changes hands, and how many entities ever reach
the top 3. `scripts/event_density.py` computes both off the cached CSV.

Scored across the **35 published videos with scoreable data**, against what they actually
did:

| correlation | r |
|---|---|
| lead changes vs retention | **-0.00** |
| lead changes vs views | **-0.19** |
| distinct top-3 vs retention | -0.00 |
| distinct top-3 vs views | -0.33 |
| lead changes vs retention, `bar_race` only (n=21) | **+0.01** |

**Event density predicts nothing on this channel.** The extremes make it vivid:

| topic | lead changes | views | retention |
|---|---|---|---|
| `gdp` (best video on the channel) | **0** | 1,682 | 29.5% |
| `ai_params` | 0 | 762 | 34.9% |
| `ai_cost` | 0 | 599 | 34.0% |
| `life_expectancy` | **107** | 294 | 27.3% |
| `money_poverty` | 54 | 62 | 25.2% |

The four topics with *zero* lead changes are four of the best performers, and the busiest
dataset in the cache did 294 views. Whatever holds a viewer, it is not the number of
overtakes — it is the **subject and the number attached to it** (Finding 5). Money, size
and AI win; demography and development lose, however much the chart moves.

**What this changes:** do not pick topics by chart motion. `scripts/event_density.py`
stays in the repo as a *descriptive* tool — it is how I learned that a Test-wins race is
Australia in front in 23 of 24 years, which is still a real editorial problem for that
one video (concept 7) — but it is not a selection metric, and there is no R8.

## 2. The system — seven rules

**R1 — Length is set by mode, not by a global default.** `target_seconds: 24` is wrong
for three of the four modes.

| mode | target | why |
|---|---|---|
| `bar_race` | **14-16s** | lead changes carry attention, but not past ~15s |
| `bump_race` | **14-16s** | same — rank flips are the events |
| `line_grow` / `line_multi` | **8-10s** | one event; get to it and loop |
| `manim` (narrated) | **25s**, hard cap | the 33s+ bucket retains 14.4% |

**R2 — Frame 0 must show the payoff, not the starting state.** Today every chart opens on
its *earliest* year: tiny bars, nothing happening, at the exact moment 98% of viewers
decide. Open on a 0.4s flash of the **final** frame (or the crossover moment), then snap
back and run. The viewer now knows what they are waiting for. Needs a change in
`graph_bot/render.py` (section 5).

**R3 — Title formula:** `[superlative or conflict verb] + [entity with a fanbase] + [unit
of money or size] + [year range]`. Apply to `YT_TITLES` in `graph_bot/caption.py`.
Banned: bare jargon pairs ("X vs Y" where neither side has a fanbase), and vague verbs
("Exploded", "Took Over") with no named subject.

**R4 — Thumbnail: the crossover, not the finish line.** `graph_bot/thumbnail.py` lifts a
frame from near the end — the settled answer. For rivalry topics, lift the frame where
the lead *changes* and overlay the question. Worth ~2% of views, so do it once and move on.

**R5 — Series have roles. Budget them separately.** Reach (World, Sports, AI short):
optimise views. Conversion (ML Basics): optimise the hook and accept low views; its job is
4.1 subs/1k. Target mix roughly **4 reach : 1 conversion**, and post the conversion video
the day after a reach video lands.

**R6 — CTA by role, not one CTA for everything.** The current description CTA is identical
on all 49 videos ("A new world-data short every day — subscribe for more!"). On a reach
video the viewer has no reason to subscribe yet; on an ML Basics video they just learned
something and do.

**R7 — Loop-close every video under ~12s.** `settings.yaml` already notes short AI topics
retain over 100% because they replay. Make the last frame visually match the first, and
never fade to black under 12s (`loop_seamless_below: 12` already does the audio half).

> **Rejected: "score event density and refuse flat topics."** It was the obvious eighth
> rule and Finding 8 shows it correlates with nothing (r = -0.00 on retention). It is
> recorded here so it does not get re-invented in three months.

---

## 3. Ten concepts, ranked by expected value

Ranked by the two things that *did* hold up: the proven title/subject pattern (Finding 5
— named entity + superlative + money or size) and the series' proven role (Findings 6-7).
Not by chart motion, which Finding 8 rules out. "Config" means the topic already exists in
`config/topics.yaml` and needs only a render.

### 1. India's Climb Up the GDP Table (config: `rank_economies`, `bump_race`, unpublished)
- **Hook:** frame 0 flashes today's top 10 with India highlighted, then rewinds to 1976.
- **Title:** `India Went From #13 to #5 (1976-2024)`
- **Thumbnail:** India's rank line crossing two rivals at once.
- **Structure:** 15s bump race, India in brand orange, everyone else muted.
- **Retention device:** a single protagonist climbing. The US never loses first place
  (0 lead changes), so do not sell the top slot — sell the climb underneath, where India
  passes eight countries.
- **CTA:** "Which country should I track next?"
- **Why:** *India Just Overtook China* is the **highest-CTR video on the channel (4.72%)**
  and *The World's Biggest Economies* is second (4.65%). This is both patterns at once,
  and `bump_race` supplies the rank events the failed 26s India `line_grow` videos
  (9.5-10% retention) never had. Verified: India #13 in 1976, #5 in 2024, #6 in 2025.

### 2. Who's Actually Richest? (config: `money_real_income`, unpublished)
- **Hook:** two bars labelled "GDP" and "GDP per person" with different leaders.
- **Title:** `The Richest Country Isn't the Biggest (1990-2025)`
- **Thumbnail:** number 1 by total vs number 1 per person, side by side.
- **Structure:** 14s bar race, PPP-adjusted per-person income.
- **Retention device:** a contradiction set up in the first second and resolved only by
  watching — viewers stay to see whether their assumption survives.
- **CTA:** "Surprised? Full list in the description."
- **Why:** *The Richest Countries Per Person* did 1,354 views at 3.24% CTR and 33.6%
  retention — top five on both axes. Same idea, sharper contradiction.

### 3. The AI Cost Curve, in 8 seconds (config: `ai_cost`, published — re-cut)
- **Hook:** the final number on screen at frame 0 — **$387,842,678**.
- **Title:** `Training One AI Model Now Costs $388 Million (2016-2025)`
- **Thumbnail:** the number alone on the brand gradient.
- **Structure:** 8s `line_grow`, log scale, loop-closed per R7.
- **Retention device:** the number *is* the hook, the curve is the proof, and it loops
  before boredom is possible.
- **CTA:** none on-frame — let it loop.
- **Why:** *The Insane Cost of Training AI* already does 34.0% retention at 6s. Its only
  weakness is a title with no number in it. Verified from cache: $201,332 in 2016 →
  $387.8M in 2025, a **1,926x** rise in nine years.

### 4. The Inflation Crown Keeps Moving (config: `rank_inflation`, `bump_race`, unpublished)
- **Hook (frame 0):** a crown on Iran's name, then it jumps backwards through 34 owners.
- **Title:** `Which Country Has the Worst Inflation? (1960-2025)`
- **Thumbnail:** the crown mid-jump between two countries, with "23,773%" on screen.
- **Structure:** 15s `bump_race` on the top slot.
- **Retention device:** escalating numbers, not chart motion. Peru 667% (1988), Ukraine
  4,735% (1993), **Congo 23,773% (1994)**, Argentina 220% (2024), Iran 42% (2025) — each
  beat is bigger than the last, which is the same "number gets absurd" shape as the AI
  topics that retain 34%. (The crown also changes hands 34 times; per Finding 8 treat that
  as pacing material, not as a reason to expect views.)
- **CTA:** "Guess who holds it today."
- **Why:** a direct fix for the channel's **worst CTR**. *Where Prices Exploded* (0.53%,
  232 views) is this exact subject with no entity and a vague verb — the R3 failure mode.
  Re-titled around a country and a crown it becomes a Finding 5 winner, and the escalating
  numbers give the title the figure that every high-CTR video on the channel has.

### 5. Big Bash: Who Actually Dominates? (config: `cricket_bbl_wins`, unpublished)
- **Hook:** eight team colours level at "2011".
- **Title:** `Big Bash: Who Actually Dominates?`
- **Thumbnail:** Perth and Sydney separated by six wins.
- **Structure:** 14s bar race, `top_n: 8`.
- **Retention device:** 4 lead changes — but be honest, they are **front-loaded**
  (Hobart → Sydney → Perth → Sydney → Perth, all by 2015; Perth then leads to 2026,
  finishing 108 to Sydney's 102). Spend 60% of the runtime on 2011-2015 and compress the
  Perth era.
- **CTA:** "Who's winning this season?"
- **Why:** Sports is the top series by median views (850) and CTR (4.37%), and this is
  already configured. The lead-change detail above is a *pacing* note, not the reason to
  pick it — Finding 8 killed chart motion as a selection metric.

### 6. Who Wins the Most Women's ODIs? (config: `cricket_women_odi_wins`, unpublished)
- **Hook:** frame 0 flash of the current leader, then back to 2007.
- **Title:** `Who Wins the Most Women's ODIs? (2007-2026)`
- **Thumbnail:** the two-way title fight.
- **Structure:** 15s bar race.
- **Retention device:** 4 lead changes across a short history, and an answer most viewers
  genuinely do not know.
- **CTA:** "More women's cricket data?"
- **Why:** the second Sports bet, zero configuration cost. Chosen over the women's T20
  set because that one is a procession (one lead change in 17 years) — a pacing problem,
  not a prediction about views.

### 7. Everyone Is Chasing Australia (config: `cricket_test_wins`, unpublished — re-framed)
- **Hook:** "Australia has been #1 since 2002." Then: "This is the race for second."
- **Title:** `The Race for Second in Test Cricket (2002-2026)`
- **Thumbnail:** England, India and South Africa stacked within 22 wins of each other.
- **Structure:** 14s bar race, Australia pinned at the top and greyed out, the animation
  scoped to places 2-5.
- **Retention device:** manufactured, because the data has none to give — Australia leads
  23 of 24 years. The contest that *is* live: England 122, India 105, South Africa 100.
- **CTA:** "Can India catch England?"
- **Why:** the obvious framing ("who wins the most Test matches") promises a race the
  data does not contain. Finding 8 says that will not necessarily cost you views — but it
  does break the deal the title makes with the viewer, and the fix is free: promise the
  contest that is actually on screen.

### 8. A Model That's 99% Right and Completely Useless (config: `ml_accuracy_lies`, re-cut)
- **Hook:** "This model is 99% accurate." (beat) "It's useless."
- **Title:** `99% Accurate and Completely Useless | ML Basics`
- **Thumbnail:** "99%" with a red cross through it.
- **Structure:** 25s hard cap (the current cut is 47s); narration in section 4.
- **Retention device:** paradox stated in second one, resolved at second twenty.
- **CTA:** "Rest of the series on the channel — this is number 10."
- **Why:** the existing 47s cut did **1,492 views and 4 subs**, the series' only hit. R1
  says the same script at 25s should hold more of them.

### 9. A Billionaire Walks Into a Bar (config: `lie_mean_median`, unpublished)
- **Hook:** ten people, an average salary, then one man walks in and the average triples.
- **Title:** `A Billionaire Walks Into a Bar (Why Averages Lie)`
- **Thumbnail:** the average line jumping past everyone in the room.
- **Structure:** 22s narrated manim.
- **Retention device:** a story with a character and a punchline, not a definition.
- **CTA:** "This is why 'average salary' headlines mislead. More in the series."
- **Why:** best title in the unrendered set by R3, and the same paradox shape that made
  concept 8 work. Check the numpy `shift=` trap before rendering this one.

### 10. The Trend That Lies (config: `simpsons_paradox`, unpublished)
- **Hook:** a line going up; then the same data split, with every group going down.
- **Title:** `Every Group Went Down. The Total Went Up.`
- **Thumbnail:** the two contradictory arrows on one chart.
- **Structure:** 24s narrated manim.
- **Retention device:** a visual impossibility on screen — viewers stay for the trick.
- **CTA:** "Which chart fooled you recently?"
- **Why:** the paradox pattern with no jargon at all. Charts Lie has one published video
  (97 views, 2.84% CTR) and needs a stronger opener to justify the series.

---

## 4. Full scripts

### Script A — `rank_inflation` (concept 4; chart video, 15s, no narration)

On-frame text only. Beats taken from the actual cached series.

```
0.0-0.4s   FLASH: the crown on "Iran 42%" (2025), caption "35 owners since 1960"
0.4s       SNAP to 1960. Title: "Which Country Has the Worst Inflation?"
           Subtitle: "The worst inflation on Earth, year by year"
0.4-4.0s   1960s-70s: Indonesia, Uruguay, Chile, Ghana trade the crown (double digits)
4.0s       Overlay chip: "so far, under 150%"
4.0-9.0s   1980s-90s escalation: Brazil 228% -> Peru 667% -> Ukraine 4,735%
7.5s       Overlay chip, large: "Congo, 1994 - 23,773%"
9.0-13.0s  2000s onward, numbers fall back: Venezuela, Zimbabwe, Sudan, Lebanon
12.0s      CTA chip, bottom third: "Guess who holds it today"
13.0-15.0s Land on Iran 2025; hold; final frame colour-matches frame 0 for the loop
```

```yaml
# config/topics.yaml - rank_inflation
key: rank_inflation
title: The Inflation Crown Keeps Moving
subtitle: The worst inflation on Earth, year by year
mode: bump_race
target_seconds: 15    # R1
series: money
source: World Bank
hashtags: [inflation, economy, money]
```

```python
# graph_bot/caption.py - add to YT_TITLES
"rank_inflation": "Which Country Has the Worst Inflation? ({range})",
```

Description (R6, reach-video CTA):

```
Which country has the worst inflation? The crown changed hands 34 times since 1960.
Congo hit 23,773% in 1994.

Data source: World Bank
Guess who holds it today.
New data short every day.

#inflation #economy #money #dataviz #Shorts
```

### Script B — `ml_accuracy_lies` (concept 8) re-cut to 25s (narrated manim)

Narration goes in `self.voiceover(text=...)` in `graph_bot/scenes/ml_accuracy_lies.py`.
The current cut runs 47s; this is the same argument at 25s, cutting the setup rather than
the punchline.

```
0-3s    VO: "This model is ninety-nine percent accurate. It's also completely useless."
        VISUAL: 10x10 chip grid fades in, one chip pink.
3-8s    VO: "One person in a hundred is sick. The model says: nobody is sick."
        VISUAL: gold box - Model: "nobody is sick". All chips turn blue.
8-13s   VO: "It gets ninety-nine out of a hundred right. And it misses every single
        patient who was actually sick."
        VISUAL: 99 tick counter races up; one cross flashes pink and stays.
13-19s  VO: "That's why accuracy alone is a lie. Recall asks a better question - of
        everyone who was sick, how many did we catch?"
        VISUAL: recall formula, the one pink chip circled; counter reads 0 of 1.
19-25s  VO: "Zero. Ninety-nine percent accurate. Zero percent useful."
        VISUAL: "99%" with a cross; hold to end card.
```

Cut from the 47s version: the precision/recall trade-off and the second worked example.
Both are better as their own video than as the back half of this one — the data says
nobody reaches the back half.

Description (R6, conversion-video CTA):

```
99% accurate, 0% useful - why accuracy is the most misleading metric in ML.
ML Basics #10.

The whole ML Basics series is on the channel - start at #1.
Which metric should I break down next?

#machinelearning #ml #ai #datascience #Shorts
```

### Script C — `ai_cost` (concept 3) re-cut to 8s (chart video, loop)

```
0.0-0.5s  Final value already on screen: "$387,842,678" - no build-up.
0.5s      Snap to 2016: "$201,332"
0.5-6.5s  line_grow on a log axis; year counter runs; value label tracks the line
6.0s      Chip: "1,926x in nine years"
6.5-8.0s  Land on $388M; hold. NO fade-out (loop_seamless_below: 12 handles audio).
          Final frame framed identically to frame 0, so the loop seam is invisible
```

```yaml
# config/topics.yaml - ai_cost
target_seconds: 8
log_scale: true
```

```python
# graph_bot/caption.py
"ai_cost": "Training One AI Model Now Costs $388 Million ({range})",
```

No on-frame CTA: under 12s the loop is the retention mechanism, and a CTA chip competes
with the number for the only 3 seconds that matter.

---

## 5. What to change in the repo

| # | Change | File | Rule |
|---|---|---|---|
| 1 | Per-mode `target_seconds` instead of one global 24 | `config/settings.yaml`, `graph_bot/render.py` | R1 |
| 2 | Cap `manim` scenes at 25s | `config/settings.yaml` | R1 |
| 3 | Prepend a 0.4s final-frame flash, then rewind | `graph_bot/render.py`, before the title block | R2 |
| 4 | Rewrite the 8 lowest-CTR entries in `YT_TITLES` | `graph_bot/caption.py` | R3 |
| 5 | Thumbnail frame = crossover, not end, for rivalry topics | `graph_bot/thumbnail.py` | R4 |
| 6 | CTA varies by `series` role | `graph_bot/caption.py`, `build_description` | R6 |
| 7 | Keep `scripts/event_density.py` as a descriptive pacing check — **not** topic selection | `scripts/event_density.py` (new) | Finding 8 |
| 8 | Render `rank_inflation`, `rank_economies`, `money_real_income`, `cricket_bbl_wins`, `cricket_women_odi_wins` | already configured | §3 |

---

## 6. How to know if any of this worked

Finding 3 is confounded (length vs topic). One clean test settles it:

**A/B the same topic at two lengths.** Take a proven 26s bar race — `gdp` (1,682 views,
29.5%) or `population` (1,482 views, 22.4%) — and publish a 14s re-cut of the *same data,
same title, same thumbnail*. Only length changes. If the 14s cut beats the 26s original
on views and retention, R1 is real and the whole back catalogue is worth re-cutting.

Measure these four per video, in the dashboard's Analytics page:

1. **Average view duration in seconds** — the honest number; retention % flatters short videos.
2. **Views at 7 days** — Shorts distribution is decided fast.
3. **Subs per 1,000 views** — the only number separating reach from conversion (R5).
4. **CTR** — only for the ~2% arriving via thumbnails; do not optimise the channel on it.

Re-export Studio analytics into `analytics_data/_new/` and re-run the join described in
this document's header to refresh every table here.

---

## 7. Shipped into Build Next (2026-09-29)

Thirteen ideas added to `IDEAS` in `dashboard/server.py` (25 → 38), chosen on the two
criteria that survived section 1 — proven subject/title pattern and series role — and
**not** on chart motion. Every data source was fetched live before being listed; the two
candidates that failed that gate are recorded below.

**AI & Compute (new section — the pillar had zero Build Next entries despite being the
channel's biggest, and it owns the best short-form retention):**

| idea | the number that carries it | mode |
|---|---|---|
| How Many GPUs to Train One AI? | 200,000 GPUs (Grok 4) | `line_grow` |
| The Most Expensive Computer Ever Built | $7.12B in hardware | `line_grow` |
| The Biggest AI Supercomputer | 230,000 chips (xAI Colossus) | `line_grow` |
| Open vs Closed: Who's Winning AI? | 455 closed vs 338 open, gap closing | `line_multi` |
| How Long Does Training an AI Take? | 7,104 hours — 296 days | `line_grow` |

All five are paced to ~9s with a per-topic `seconds_per_year: 0.9`. R1 is applied here and
**not** to the new bar races: the short-video evidence is strong *within* `line_grow`
(642 median views under 12s vs 68 over) but untested for `bar_race`, whose 13s+ cut is the
proven workhorse. Applying an unvalidated rule to the workhorse would be the mistake
section 6 is designed to prevent.

**Money & Power:** The World's Biggest Stock Markets (US $68.9T vs China $15.5T, India
third), Who Has the Biggest Piggy Bank? (China $3.7T reserves), Who Exports the Most
Technology? (China $857B), Where the World's Money Goes (US $400B FDI), The World's
Biggest Armies (India 3.07M — note the series ends in 2020).

**ML Basics (new section — 4.10 subs/1k, the only converter on the channel):** the three
registered-but-never-built scenes, retitled as paradoxes after the series' one breakout:
`simpsons_paradox` → *Every Group Went Down. The Total Went Up.*, `gradient_descent` →
*AI Learns by Falling Downhill*, `kmeans` → *Nobody Told It These Were Groups*. Their old
`YT_TITLES` entries were the exact failure mode Finding 5 describes — *How Computers Find
Patterns (K-Means)* and *Explained in 30s* — so `graph_bot/caption.py` was updated for
these three plus all ten new topics.

**Rejected at the verification gate:**

- *Whose Chips Train the World's AI?* — "Anonymized" is the second-largest supplier in the
  source (182 of 482 clusters), so the race would be NVIDIA against a placeholder.
- *The Fastest Growing Economies* — the top three are a different set of micro-economies
  every single year (Guyana, Maldives, Turks and Caicos, Palau, Samoa). A race with no
  persistent contestants is noise, not a story.

**One pipeline change was needed:** `entity_map` only worked in the cricsheet fetcher, so
the open-vs-closed lines would have been labelled "Yes" and "No". `graph_bot/fetch.py` now
applies it in the `csv_url` path too, matching the field's documented, generic meaning.

