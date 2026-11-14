# Series plan — "Math in Motion"

Format: wordless simulated Shorts (`mode: sim`, rendered by `graph_bot/sims/`), vertical,
60 fps, 25–32 s. Playlist: **Math in Motion** (create it on YouTube before the first upload).

**Why this series.** The channel's own numbers: Shorts of 10 s or less median 642 views, narrated
30 s+ episodes 52. Wordless, satisfying motion travels; narration doesn't. Simulation Shorts
in this genre regularly reach hundreds of thousands of viewers on channels with no data angle.
Our edge is that each one is a real result, not a trick: the pile, the counter, the curve are
what the maths actually does.

## The bar every episode must clear

- **Visually stunning, every time.** Neon board on near-black; glossy, antialiased objects; no
  per-object halos (a crowd of them flickers into a blob); smooth 60 fps motion from real or
  guided physics, never scripted snaps.
- **One question as the hook**, on screen from frame one ("Where will 500 balls land?").
- **Escalate:** start with one object alone (slow, every event heard), then the crowd.
- **Payoff:** a reveal in the last 4–5 s that answers the hook (a curve, a number, a shape).
- **Sound from the simulation:** every bounce or event plays a note (pentatonic, panned by
  position), turned down as events crowd. A rising arpeggio and chord on the reveal.
- **Honest:** the result on screen is computed, not drawn to match. Say what the rule is
  ("Every bounce: left or right, 50/50").
- **Safe areas:** nothing important in the bottom ~18% or the right edge from mid-height
  (YouTube's title, channel and buttons).

## Episodes

| # | Hook on screen | What happens | Payoff | Status |
|---|---|---|---|---|
| 1 | **Where will 500 balls land?** | Galton board: marbles bounce through 12 rows of pegs into bins | The bell curve drawn over the piles | **Built** (`sim: galton`) |
| 2 | **Should you switch doors?** | Monty Hall, 1,000 games played fast; "switch" and "stay" win counters race | Switch wins 2/3 of the time | **Built** (`sim: monty_hall`) |
| 3 | **Can random dots find π?** | Dots rain into a square; inside the circle turn gold; the estimate updates | The estimate settles on 3.14159… | **Built** (`sim: monte_carlo_pi`) |
| 4 | **Two balls, 0.001 apart. Same path?** | Two balls bounce in a circle, together at first | They split completely: chaos | Planned |
| 5 | **100 pendulums, almost identical** | Double pendulums released a hair apart, in a rainbow | They fan out into chaos | Planned |
| 6 | **15 pendulums. One release. What happens next?** | Pendulum wave (exact large-angle physics): snakes, rows, chaos; swing counters beside each bob | Slow motion into the line-up at 24 s; counters read 16…30 | **Built** (`sim: pendulum_wave`) |
| 7 | **Every dot is random. So why this shape?** | The chaos game: jump halfway to a random corner, 150,000 times | Sierpinski triangle, then a 4× self-similar zoom | **Built** (`sim: chaos_game`) |
| 8 | **How many people until two share a birthday?** | People walk into a room until a match; repeated 500 times | Usually just 23 people | **Built** (`sim: birthday`) |
| 9 | **Will a lost walker ever get home?** | Random walks on a grid, 2D vs 3D side by side | 2D always returns; 3D often never | Planned |
| 10 | **Light in a coffee cup** | Rays reflect inside a circle | A glowing cardioid (the cup caustic) | Planned |
| 11 | **Which sort finishes first?** | Bubble, quick and merge sort race on the same bars, with sound | Quick sort wins by miles | Planned |
| 12 | **Plot the primes in a spiral** | Numbers spiral out; primes light up | Arms appear out of nowhere | Planned |
| 13 | **Why do sunflowers turn each seed 137.5°?** | Seeds placed by a fixed turn; 90°, 120°, 135°, 137° tried with a live "seeds jammed" count (800, 800, 795, 525) | 137.5° jams none, petals bloom, spirals counted: 34 and 55 | **Built** (`sim: golden_angle`) |
| 14 | **Drop needles on a floor. Count them. Get π.** | Buffon's needle in 3D (Blender, Cycles): 5,000 steel needles fall on an oak floor whose boards are one needle wide; the ones across a crack turn brass; 2 × dropped ÷ crossed runs live | 3.1417 after 5,000 (seed picked so needle 1 crosses, 2 misses) | **Built** (`sim: buffon`) |
| 15 | **A perfect curve hides in your coffee.** | A glazed mug of milky coffee in low sun (Blender); rays drawn from above crowd into the bright curve (photon-traced for this cup); a clip-on LED on the rim turns it into a heart | Nephroid, then cardioid, with their exact outlines | **Built** (`sim: coffee`) |

Build order: 2, 3 and 8 next (probability, closest to the channel's data audience), then a
spectacle piece (4 or 6), then the rest. Each new sim reuses `sims/canvas.py` (drawing,
encoding) and `sims/sound.py` (event sounds).

## What the first four taught us (views, 9 Nov 2026)

Pi 1,685 views in 3 days and Galton 1,537 (both channel top 5); Monty Hall 13 and birthday 57.
Spectacle with one clear visual result wins; puzzles explained with tubes and charts don't.
The pi version that worked had a short British voice-over (Sonia) and word-timed captions.

## Hook rule (from episode 6 on, `sims/kit.py`)

- Frame one already shows the finished, most beautiful image, with the hook question in a large
  serif over it (words rise in one by one) and spoken aloud. Never an empty board or title card.
- Then the scene rewinds to the start and builds back up, so the payoff is earned.
- A live counter that makes the idea measurable (seeds jammed, jumps, swings).
- Voice: Sonia at +10%, 4–5 short lines, captions under the hook. Keep it to 30–35 s.

## Blender episodes (from ep 14, 2026-11-14)

Real-looking 3D: `sims/blend.py` runs Blender headless on `scripts/blender/<scene>.py` and caches one PNG per
frame under `data/cache/blender/<scene>/<hash of job + scripts>`; the sim draws text, counters and sound on top.
Drawn at 1440 x 2560. Shared Blender helpers (render setup, ring-geometry wood, lathe) in `scripts/blender/bkit.py`.
Cycles at 64 samples + OptiX denoise is about 1–2.5 s a frame on the RTX 4090; static stretches render once.

## Test plan

Run it on this channel for 10–12 episodes over 2–3 weeks. Keep going if the median beats
World in Data's ~1,000 views by 3× or more (then consider a dedicated channel); stop if it
cannot beat ~1,000.
