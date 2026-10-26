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
| 6 | **15 pendulums, one release** | Pendulum wave: snakes, lines, chaos, then back in sync | All 15 line up again at 60 s | Planned |
| 7 | **What do random dots draw?** | The chaos game: jump halfway to a random corner, again and again | A Sierpinski triangle appears | Planned |
| 8 | **How many people until two share a birthday?** | People walk into a room until a match; repeated 500 times | Usually just 23 people | **Built** (`sim: birthday`) |
| 9 | **Will a lost walker ever get home?** | Random walks on a grid, 2D vs 3D side by side | 2D always returns; 3D often never | Planned |
| 10 | **Light in a coffee cup** | Rays reflect inside a circle | A glowing cardioid (the cup caustic) | Planned |
| 11 | **Which sort finishes first?** | Bubble, quick and merge sort race on the same bars, with sound | Quick sort wins by miles | Planned |
| 12 | **Plot the primes in a spiral** | Numbers spiral out; primes light up | Arms appear out of nowhere | Planned |

Build order: 2, 3 and 8 next (probability, closest to the channel's data audience), then a
spectacle piece (4 or 6), then the rest. Each new sim reuses `sims/canvas.py` (drawing,
encoding) and `sims/sound.py` (event sounds).

## Test plan

Run it on this channel for 10–12 episodes over 2–3 weeks. Keep going if the median beats
World in Data's ~1,000 views by 3× or more (then consider a dedicated channel); stop if it
cannot beat ~1,000.
