# Space in Motion

A space-scale series on Data in Motion (playlist "Space in Motion", keys `space_`).
Started 2026-11-11. Built like Math in Motion: `mode: sim`, one module per episode in
`graph_bot/sims/`, shared pieces in `graph_bot/sims/space.py`.

## The angle

Space-scale Shorts are a crowded genre, and most are loose with facts. Each episode
takes a famous claim and shows the precise version, with one clear visual result:

- "1.3 million Earths fit in the Sun": by volume. As real balls, ~960,000 even packed perfectly.
- "All the planets fit between Earth and the Moon": they total ~388,000 km against a
  ~376,000 km average gap, so only when the Moon is near its farthest point.
- "Andromeda will hit us in 4.5 billion years": a 2025 study puts it near 50/50 within 10 billion years.

## Format and look

- 30–35 s vertical, cold open: frame one is the finished image plus a spoken serif hook,
  then rewind and build (same rule as Math in Motion). Sonia +10%, word-timed captions.
- Visual Direction v2.0: warm charcoal-navy (not black), gold only on the key number,
  serif hook, heavy sans numbers. No neon, HUD or lens flares.
- Planets are lit from the Sun's real direction (`space.lit_planet`); positions on any date
  come from JPL's approximate orbital elements (`space.helio`).
- Real photos or texture maps only if properly licensed, and only after the user approves the download.

## Episodes

| # | Key | Hook | Status |
|---|-----|------|--------|
| 1 | `space_voyager_light_day` | A signal from Voyager 1 now takes a full day (18 Nov 2026) | built 2026-11-11 |
| 2 | | How many Earths fit in the Sun? (packing twist, physics pour) | idea |
| 3 | | All the planets between Earth and the Moon (only sometimes) | idea |
| 4 | | How long to Proxima Centauri? light 4.2 y · Parker ~6,600 y · Voyager ~75,000 y | idea |
| 5 | | Planets → Sun → Betelgeuse size ladder (zoom out) | idea |
| 6 | | How big is the Milky Way? (Solar System as a coin) | idea |
| 7 | | The Sun's last lap of the galaxy began with the first dinosaurs (~230 Myr) | idea |
| 8 | | Andromeda: 2.5 million ly away, yet ~6 full Moons wide in our sky | idea |
| 9 | | How old is the light you see? (Sun 8 min 20 s, stars...) | idea |
| 10 | | Your age and weight on every planet | idea |
| 11 | | Jupiter's Great Red Spot is shrinking (3 Earths → ~1.3) | idea |
| 12 | | Mangalyaan cost less than the film *Gravity* (India in Data crossover) | idea |

Later: a long-form "How Big Is Space?" zoom-out documentary built from these as chapters.

Test: 6 episodes over ~2 weeks; keep the series if the median beats ~1,500 views
(the level of the best Math in Motion episodes).

## Episode 1 notes (Voyager, one light-day)

The camera rides the light front from Earth, so the front stays fixed on screen and the
Solar System shrinks inside it. Planet positions are for 18 Nov 2026 06:16 UTC (NASA's
time for the crossing). Light times from Earth that day: Sun 8.2 min, Jupiter 43.5 min,
Saturn 73 min, Uranus 2 h 33 min, Neptune 4 h 4 min; one light-day = 173.1 AU = 25.9 billion km.
Voyager and Proxima are placed by ecliptic longitude with their latitude folded into
the plane (distances exact). Proxima: 4.2465 ly; at 16.95 km/s ≈ 75,000 years.
