# Fitz, the PickFit mascot

Fitz is a tailorbird (縫葉鶯). Real tailorbirds pierce leaves with a needle-like beak and stitch them into a nest that fits exactly: they **pick** the leaves and make the nest **fit**. Fitz does the same with software: it tries things first, and says plainly when something doesn't fit.

Personality: picky, honest, warm. Never recommends what it hasn't tried.

Open `index.html` through a local server (for example `python3 -m http.server -d brand/mascot`) to see every file on light and dark backgrounds.

## Files

| File | What |
|---|---|
| `fitz.svg` | Main character, facing the viewer |
| `fitz-turn.svg` | Head turned about three-quarters to the right; the beak shows from the side and can hold things |
| `fitz-mono.svg` | One-colour line version; uses `currentColor` |
| `expressions/fitz-{neutral,happy,thinking,surprised,sorry,proud}.svg` | Expression set (front) |
| `states/fitz-{idle,searching,testing,recommending,test-failed,success}.svg` | Animated states (CSS keyframes inside the SVG) |
| `icons/fitz-{16,32,64}.svg` | Icons, drawn separately for each size |
| `icons/fitz-{16,32,64}-dark.svg` | Same icons with a cream outline, for dark backgrounds |
| `icons/fitz-mono-32.svg` | One-colour 32 px icon |
| `build.py` | Writes every SVG above from one set of shapes and one palette |
| `index.html` | Preview page |

Edit `build.py`, not the SVGs, then run `python3 brand/mascot/build.py`. The SVGs are committed so they can be used without running anything.

## Palette

| Role | Hex |
|---|---|
| Outline, eyes (ink) | `#4A2E22` |
| Body, olive yellow-green | `#A9BC4C` |
| Wings | `#869E3A` |
| Tail | `#7C9334` |
| Cap and tuft, rufous | `#C4552D` |
| Belly, cream (also the outline of the `-dark` icons) | `#FFF3D3` |
| Beak: upper half / lower half | `#CF6F2A` / `#F0A04B` |
| Measuring tape | `#F5C243` |
| Tape end tab | `#C3CAD2` |
| Blush | `#F2917C` at 55% |
| Accents: sparkles | `#F5C243` · sweat drop `#7CC0E8` · `?` `!` and dots use the cap colour |
| Props: leaf `#6CBF4E` / `#3E8A3A`, package `#E8BC7E` / `#C9924E`, good `#4CA65A`, bad `#D9533C` |

Line weight on the 200-unit canvas: 4.5 for the outer outline, 3 for inner lines (tape, wings, props), 2.4 for the beak, 1.8 for tape ticks. Icons use their own weights (64: 2.4, 32: 1.5, 16: 1).

## Proportions

- **Body**: one egg, a little narrower at the top (126 × 124 on the 200 canvas). Head and body are the same shape; no neck.
- **Tuft**: a small soft rufous curl on top.
- **Face**: lots of empty space. Two small dot eyes, 56 apart (about 45% of the body width), a little above the middle.
- **Beak, front**: a tiny diamond (13 × 13) centred between the eyes and just below them; upper half darker. It is the mouth.
- **Beak, turned**: a small side triangle on the face near the front edge, under the far eye. Its tip is where Fitz holds the tape end or the leaf.
- **Cap**: rufous over the crown, with a point coming down the forehead toward the beak.
- **Tail**: grows from behind the body and sweeps up and back past the left shoulder. Never a stalk on the crown.
- **Wings**: small side flaps, not much bigger than the eye-to-cheek area.
- **Measuring tape**: one band around the neck with a short loose end and a metal tab, as in v1.

Silhouette test (all filled solid): egg + small tuft + tail cocked up behind = a small bird. At 32 px the cap, tuft, eyes, beak and tape still show; at 16 px the tuft, tape and wings are dropped and the beak is a 2 px diamond.

## Do / don't

Do
- Front view: keep the beak a tiny diamond centred just below the eyes.
- When Fitz holds something, turn the head (`turn` pose) so the beak becomes a side triangle.
- Keep the tail coming from behind and cocked up.
- Keep the cap rufous, the beak orange and the tape yellow.
- Use the per-size icons for favicons and small UI, and the `-dark` icons on dark backgrounds; don't shrink `fitz.svg`.

Don't
- Don't make the beak bigger or put it on the outline of the head.
- Don't add a neck, hands, hat or glasses, and don't let the wings grow into arms.
- Don't recolour the body or cap, stretch, or rotate Fitz so the tail points sideways.
- Don't put text inside the character.
- Don't show the happy or proud face next to an unverified result. Fitz only celebrates what passed a test.

## Which state goes with which product moment

| State / expression | Pose | Product moment |
|---|---|---|
| `idle` | front | Waiting for the user's request |
| `searching` | front | `find_software` / `find_alternatives` is running |
| `thinking` | front | Asking the user a clarifying question (OS, must be free/offline) |
| `testing` | turned | Install and verification running in the sandbox: the tape runs from the beak across a `</>` package |
| `recommending` | turned | Presenting the pick, a stitched leaf held in the beak: "this one fits" |
| `proud` | front | A result card for a verified pick |
| `happy` / `success` | front | Install guide finished and the tool works (`report_outcome` success) |
| `test-failed` / `sorry` | turned / front | Verification failed, or nothing fits; the tape comes up short and Fitz says so plainly |
| `surprised` | front | Unexpected result, for example the built-in tool is already enough |
| `neutral` | front | Default on result cards and docs |

All animations are short loops (1.8–3.4 s) using CSS keyframes inside each SVG. They stop under `prefers-reduced-motion: reduce`; the still frame is the key pose (tape fully out, leaf held up, gap marked), so nothing is lost.

## History

- v1: three-quarter view, long needle beak on the side of the head, tail straight up from the crown, tape as a band. Read as a ball with a stem.
- v2: front face with a large beak between the eyes, tail from behind, big wings, tape draped as two strips. Read as a bird, but the beak and wings were too big and the tape too busy.
- v3 (current): egg body, tuft, small dot eyes, tiny diamond beak, v1-style tape band, small wings, and a turned pose for holding things.

## Provenance

Original artwork, drawn as hand-written SVG (through `build.py`) on 2026-11-01 during the hackathon development period. ChatGPT-generated images and two stock images the user found online were viewed only as style reference (proportions, eye and beak size, line weight); none of them are included, traced or copied here.
