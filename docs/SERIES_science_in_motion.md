# Science in Motion

A science series on Wonderlapse (playlist "Science in Motion", keys `science_`).
Started 2026-11-14. Built like Math and Space in Motion: `mode: sim`, one module
per episode in `graph_bot/sims/`.

## The angle

One physical idea per Short, shown as a real 3D scene the camera moves through,
with every number checked against a source. The hook is a single surprising
comparison; the body is the journey that proves it.

## Format and look

- Under 30 s including the spoken sign-off. Cold open: frame one is the finished
  image plus a spoken serif hook, then rewind and build.
- Voice: Andrew, English-only (en-US-AndrewNeural, +8%), word-timed captions.
- Visual Direction v2.0: charcoal backdrop, gold only on the key number, serif
  hook, heavy sans numbers. No neon or HUD.
- 3D is ray-marched in numpy (no engine): `ocean_depth.py` has the pieces to reuse:
  a camera (`Cam`), a heightfield march, a cutaway block, a tiling rock-detail
  texture with three-way projection, fog, sub-pixel sprite placement (`blit`).
- No flicker rules: fields are blurred to a few grid cells, edges are drawn as
  anti-aliased lines over the render, moving labels are placed at sub-pixel
  positions, fine rock detail fades with distance and is motion-blurred when the
  camera moves fast, particles fade at the wrap of their box, and a fixed dither
  stops banding in dark water.
- Objects that must look real (animals, ships, people) are real 3D models, built,
  animated and rendered in Blender, never drawn and never frozen: living things move
  (the whale's tail beats, the diver kicks and breathes bubbles, the fish wiggles).
  `scripts/make_ocean_models.py` paints their textures and runs
  `scripts/blender/ocean_models.py`, which models each one from scratch (lofted bodies,
  fins, tubes for limbs and hoses), rebuilds it in every pose of a loop and renders the
  loop with Cycles to transparent PNGs in `assets/<episode>/<name>/NNN.png`. Nothing is
  downloaded, so there is no licence to track. The sim plays those loops in its own 3D
  scene (fogged and lit by depth) and falls back to flat drawn sprites if they are
  missing. Blender 4.5 LTS (portable) is in `E:/tools/blender`; set `BLENDER` to use
  another copy.
- No diagram boxes: an establishing shot is a place (sea, sky, horizon), cut open only
  where the story needs to see inside.
- A thing shown out of its real place (the Titanic's wreck, which is in the Atlantic)
  says so on screen, next to it.
- Say plainly in the description what is to scale and what is not.

## What belongs here (and what goes to Space in Motion)

- **Science in Motion:** things on or inside the Earth, and physics: the ocean, water, drilling,
  atoms, weather.
- **Space in Motion:** anything looking outward beyond the Earth: planets, stars, galaxies, cosmic
  scale. "How high is space?", "How fast are you moving right now?" and the city-to-universe
  zoom-out ("How vast is space?") were moved there for that reason (2026-11-14).

## Resolution

New 3D episodes are drawn above 1080 x 1920 when they can be: `earth_water.py` renders everything,
text included, at 1440 x 2560 (`EARTH_WATER_SIZE=2160x3840` for 4K) and passes
`size=(w, h)` to `kit.encode`. Sizes in such a sim are written for a 1080-wide frame and
multiplied by `K = OUT_W / 1080`. `ocean_depth.py` is still 1080 x 1920.

## Episodes

| # | Key | Hook | Status |
|---|-----|------|--------|
| 1 | `science_ocean_depth` | How deep is the ocean? The Titanic isn't even halfway down (Everest in the trench) | uploaded 2026-11-14 |
| 2 | `science_earth_water` | All the water on Earth fits in this one ball (1,385 km; fresh 273 km; lakes and rivers 56 km) | built 2026-11-14 |
| 3 | | How deep have we ever drilled? (Kola, 12,262 m: deeper than the ocean, 0.2% of the way down) | idea |
| 4 | | Why is the sky blue and the sunset red? (scattering, one beam) | idea |
| 5 | | How big is an atom, really? (zoom from a hand) | idea |
| 6 | | What a lightning bolt does in one second | idea |
