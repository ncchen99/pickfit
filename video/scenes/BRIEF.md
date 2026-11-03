# Brief for building an animated scene

Read this, then [../script.md](../script.md) (Chinese; the storyboard for your segment) and
[../edit/timeline.json](../edit/timeline.json) (narration cue times). The product context is in
[../../docs/submission/story.md](../../docs/submission/story.md) sections 1–2 if you need it.

## What pickfit is (one paragraph)

pickfit is a neutral software advisor: it finds software (desktop apps, CLIs, MCP servers, web
apps), installs and tests each one in a sandbox (Linux on Modal, a fresh macOS VM, a sandboxed
browser), and tells you, or your AI agent over MCP, which one fits your need, with the exact
steps that worked. Its mascot is **Fitz**, a tailorbird: tailorbirds stitch leaves into a nest
that fits. The site is a tailor's fitting room: your request is a white card with a measuring
tape as its baseline; Fitz's answer is an olive card; a rufous running stitch means "pickfit ran
it". Meta's models do the work: **Muse Spark 1.3** (extraction with quotes, judging, live
matching) and **Muse Spark Open**, Meta's open-weight model (prescreen, operating GUI apps).

## The look (approved by 念誠 from out/look-1.png)

- Real 3D (three.js): soft daylight, soft shadows, ambient occlusion, a little depth of field.
  Tactile materials: paper cards with thickness and the cut corner, a satin measuring tape with
  ticks, a cotton thread, Fitz in clay with his ink outline. Not flat, not busy.
- Colour comes from the live site; use `kit/tokens.js` only (`site.*`, `fitz.*`). One quiet paper
  ground (`site.paper`). At most one solid tape-yellow thing per shot. Rufous stitch only on
  verified things. No gradients, no glass, no neon, no extra colours.
- Fitz never changes colour or proportions. He holds things only in the turned pose (`fz.turn(1)`),
  with the item in `fz.hold`. He looks happy only next to something that passed a test.
- Every motion has a purpose you can say in one word. Entrances: scale from ~0.94 plus opacity
  or a short rise, never from 0. Use the site's curves: `ease.out` (expo.out) for entrances,
  `ease.io` (power3.inOut) for moves. No ease-in on UI. Save the big surprises for the moments
  the script names.
- At most three layers at once; a new layer pushes the old one back and dims it.
- Every website, review, app icon and dialog in an animated scene is a fictional generic style:
  no real brands, logos, product names or real people (MangoDisk, pickfit, Muse Spark and the
  real repo URL in the script are the only real names).
- English on screen, short. Display type: `fonts.display` (Bricolage, opsz 96) weight 700;
  body `fonts.sans`; commands `fonts.mono`. Text is printed on cards with canvas textures
  (`paperCard({ draw })`, `text()`), so it stays sharp.

## The kit (video/kit/, do not edit it)

If the kit is missing something, put a helper in your own file under `scenes/<your-scene>/` or
inside your HTML, and mention it in your report. If you find a kit bug, work around it locally
and report it; I will fix the kit.

- `stage.js`: `new Stage({ dof, ao, ground, fov, background })` gives `stage.scene`, `.camera`,
  `.target`, `.key` (shadow light), `.fill`, `.floor`, `.catcher`, `.render()`, `.lookAt(x,y,z)`,
  `.ready` (fonts). Call `stage.run({ duration, update(t) })` once; `update(t)` must pose
  EVERYTHING purely from `t` (seconds): the renderer seeks frames out of order and repeatedly, so
  no state carried between frames, no `Math.random()` at render time (seed it), no real clocks.
  The usual pattern: one paused GSAP timeline built up front, `tl.seek(t, false)` in `update`,
  plus pure functions of `t` for loops (blink, bob). `canvasTexture(w, h, draw)` makes a sharp
  texture; `tex.userData.redraw(fn)` repaints it (e.g. a clock face), but only redraw when the
  value actually changes (cache the last value) since it is slow.
- `fitz3d.js`: `createFitz()` → `{ root, bird, torso, parts, hold, height, blink(v), flap(v),
  squash(s), turn(v) }`; `leaf()` makes the stitched leaf for `hold`. Scale `root` to taste
  (look-1 uses 0.85). Units: Fitz is about 1.3 tall at scale 1.
- `props.js`: `paperCard({ w, h, depth, cut, color, edge, edgeWidth, draw, ppu })` (stands up,
  face +z; lay it flat with `rotation.x = -PI/2`), `cardPath`, `text(ctx, str, x, y, opts)`,
  `drawTape`, `drawSeam`, `drawMeasure(ctx, rows, x, y, w)`, `stitchThread(curve, opts)` with
  `.userData.progress(v)` to sew it in, `screenPanel({ w, h })` (a dark-framed slab whose
  `userData.face` is a plane you can give any texture).
- `tokens.js`: `site`, `fitz`, `ease`, `fonts`.
- `scenes/look.html` is a working example of the whole setup (head, import map, fonts).

## Render and check

```bash
cd video
node render.mjs <scene> --still 12.5          # one PNG at t = 12.5 s → out/<scene>-12.5.png
node render.mjs <scene>                       # the whole scene → out/<scene>.mp4 (30 fps)
node render.mjs <scene> --from 10 --to 14     # a slice
```

A frame takes about 0.1–0.3 s. Look at your stills with the Read tool at several moments (every
cue in the narration) and fix what looks wrong before rendering the whole scene. You cannot hear
the narration: sync to the cue times you were given. Check the first and last frame: they must
cut cleanly with the neighbouring segment as the script describes.

## Rules

- Write only your own files: `scenes/<name>.html` and `scenes/<name>/` if you need more. Do not
  edit `kit/`, `render.mjs`, `edit/`, `script.md` or anything outside `video/`.
- Do not commit; I review and commit.
- No new npm packages, no downloads, no network calls from the scene. three.js addons from
  `three/addons/` are fine. Fonts: only the two in the kit.
- Do not read `../../eval/` or `.env`.
- Finish with `node render.mjs <name>` and report: the file paths, the cue-by-cue description
  of what is on screen, anything you could not do, and any kit issues.
