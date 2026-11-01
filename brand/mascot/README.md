# Fitz, the PickFit mascot

Fitz is a tailorbird (縫葉鶯). Real tailorbirds pierce leaves with a needle-like beak and stitch them into a nest that fits exactly: they **pick** the leaves and make the nest **fit**. Fitz does the same with software: it tries things first, and says plainly when something doesn't fit.

Personality: picky, honest, warm. Never recommends what it hasn't tried.

Open `index.html` through a local server (for example `python3 -m http.server -d brand/mascot`) to see every file on light and dark backgrounds.

## Files

| File | What |
|---|---|
| `fitz.svg` | Main character, facing the viewer |
| `fitz-turn.svg` | Face turned a little to the right, for pointing at something beside Fitz |
| `fitz-mono.svg` | One-colour line version; uses `currentColor` |
| `expressions/fitz-{neutral,happy,thinking,surprised,sorry,proud}.svg` | Expression set |
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
| Cap, rufous | `#C4552D` |
| Belly, cream (also the outline of the `-dark` icons) | `#FFF3D3` |
| Beak, warm horn orange | `#E8964A` |
| Measuring tape | `#F5C243` |
| Tape end tab | `#C3CAD2` |
| Blush | `#F2917C` at 55% |
| Accents: sparkles | `#F5C243` · sweat drop `#7CC0E8` · `?` `!` and dots use the cap colour |
| Props: leaf `#6CBF4E` / `#3E8A3A`, package `#E8BC7E` / `#C9924E`, good `#4CA65A`, bad `#D9533C` |

Line weight on the 200-unit canvas: 4.5 for the outer outline, 3 for inner lines (beak, wings, tape edges, props), 1.8 for tape ticks. Icons use their own weights (64: 2.4, 32: 1.5, 16: 1).

## Proportions

- One chubby shape is both head and body (130 × 118 on the 200 canvas). Never a small head on a neck.
- Face: two eyes 48 apart, just below the cap line. The **beak sits between the eyes, centred, its top at eye level and its tip pointing down**, like a mascot's mouth. It is a short orange triangle (20 wide, 25 long), sharp enough to hint at the tailor's needle.
- Cap: rufous over the crown, with a small point coming down the forehead to meet the beak, as on a real tailorbird.
- Tail: grows from **behind** the body and sweeps up and back past the left shoulder, about 25° from vertical. It must never sit on the crown like a stalk.
- Wings: a teardrop on each side, tips pointing down and out past the body edge.
- Measuring tape: draped around the neck; both ends hang down the chest with a metal tab, the way a tailor wears one.
- `fitz-turn.svg` and the states that point at a prop shift the eyes, beak, cap point and tape 10 units to the right.

Silhouette test (all filled solid): round body + tail cocked up behind one shoulder + a wing on each side = a small bird. At 32 px the cap, beak, wings and tape still show; at 16 px the tape and wings are dropped and the beak becomes a small centred triangle.

## Do / don't

Do
- Keep the beak centred under the eyes in every view.
- Keep the tail coming from behind and cocked up. It is the silhouette.
- Keep the cap rufous, the beak orange and the tape yellow.
- Let props (tape end, leaf) come from the beak tip; let the wings gesture.
- Use the per-size icons for favicons and small UI, and the `-dark` icons on dark backgrounds; don't shrink `fitz.svg`.

Don't
- Don't put the beak on the outline of the head or out to the side.
- Don't add a neck, hands, hat or glasses.
- Don't recolour the body or cap, stretch, or rotate Fitz so the tail points sideways.
- Don't put text inside the character.
- Don't show the happy or proud face next to an unverified result. Fitz only celebrates what passed a test.

## Which state goes with which product moment

| State / expression | Product moment |
|---|---|
| `idle` | Waiting for the user's request |
| `searching` | `find_software` / `find_alternatives` is running |
| `thinking` | Asking the user a clarifying question (OS, must be free/offline) |
| `testing` | Install and verification running in the sandbox: the tape runs from the beak across a `</>` package |
| `recommending` | Presenting the pick, a stitched leaf held in the beak: "this one fits" |
| `proud` | A result card for a verified pick |
| `happy` / `success` | Install guide finished and the tool works (`report_outcome` success) |
| `test-failed` / `sorry` | Verification failed, or nothing fits; the tape comes up short and Fitz says so plainly |
| `surprised` | Unexpected result, for example the built-in tool is already enough |
| `neutral` | Default on result cards and docs |

All animations are short loops (1.8–3.4 s) using CSS keyframes inside each SVG. They stop under `prefers-reduced-motion: reduce`; the still frame is the key pose (tape fully out, leaf held up, gap marked), so nothing is lost.

## History

- v1: three-quarter view with a long needle beak on the side of the head, tail straight up from the crown, and the tape as a band around the middle. It read as a ball with a stem.
- v2 (current): front-facing face with the beak between the eyes, tail from behind, wings, and a draped tape.

## Provenance

Original artwork, drawn as hand-written SVG (through `build.py`) on 2026-11-01 during the hackathon development period. ChatGPT-generated images were viewed only as style reference (proportions, eye style, line weight); none of them are included, traced or copied here.
