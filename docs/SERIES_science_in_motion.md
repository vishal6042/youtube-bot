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

## Episodes

| # | Key | Hook | Status |
|---|-----|------|--------|
| 1 | `science_ocean_depth` | Drop Everest into the deepest ocean: its peak is still 2 km underwater | built 2026-11-14 |
| 2 | | How fast are you moving right now? (spin, orbit, galaxy) | idea |
| 3 | | Why is the sky blue and the sunset red? (scattering, one beam) | idea |
| 4 | | How big is an atom, really? (zoom from a hand) | idea |
| 5 | | What a lightning bolt does in one second | idea |
| 6 | | How much of Earth's water is drinkable? (spheres over the globe) | idea |
