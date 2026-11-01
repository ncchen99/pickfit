# Fitz, the PickFit mascot

Fitz is a tailorbird (縫葉鶯). Real tailorbirds pierce leaves with a needle-like beak and stitch them into a nest that fits exactly: they **pick** the leaves and make the nest **fit**. Fitz does the same with software: it tries things first, and says plainly when something doesn't fit.

Personality: picky, honest, warm. Never recommends what it hasn't tried.

Open `index.html` through a local server (for example `python3 -m http.server -d brand/mascot`) to see every file on light and dark backgrounds.

## Files

| File | What |
|---|---|
| `fitz.svg` | Main character, three-quarter view facing right |
| `fitz-front.svg` | Front view |
| `fitz-mono.svg` | One-colour line version; uses `currentColor` |
| `expressions/fitz-{neutral,happy,thinking,surprised,sorry,proud}.svg` | Expression set |
| `states/fitz-{idle,searching,testing,recommending,test-failed,success}.svg` | Animated states (CSS keyframes inside the SVG) |
| `icons/fitz-{16,32,64}.svg`, `icons/fitz-mono-32.svg` | Icons, drawn separately for each size |
| `build.py` | Writes every SVG above from one set of shapes and one palette |
| `index.html` | Preview page |

Edit `build.py`, not the SVGs, then run `python3 brand/mascot/build.py`. The SVGs are committed so they can be used without running anything.

## Palette

| Role | Hex |
|---|---|
| Outline, eyes, beak (ink) | `#4A2E22` |
| Body, olive yellow-green | `#A9BC4C` |
| Wing | `#869E3A` |
| Tail | `#7C9334` |
| Cap, rufous | `#C4552D` |
| Belly, cream | `#FFF3D3` |
| Measuring tape | `#F5C243` |
| Tape end tab | `#C3CAD2` |
| Blush | `#F2917C` at 55% |
| Accents: sparkles | `#F5C243` · sweat drop `#7CC0E8` · `?` `!` and dots use the cap colour |
| Props: leaf `#6CBF4E` / `#3E8A3A`, package `#E8BC7E` / `#C9924E`, good `#4CA65A`, bad `#D9533C` |

Line weight on the 200-unit canvas: 4.5 for the outer outline, 3 for inner lines (tape edges, wing, props), 2 for tape ticks. Icons use their own weights (64: 2.4, 32: 1.5, 16: 1).

## Proportions

- One shape is both head and body: an ellipse 128 × 114 (a little wider than tall, like a rice cake).
- Cap covers the crown and runs down the forehead to the beak base, as on a real tailorbird.
- Eyes sit just below the cap line, a little above the body's middle; the far eye is slightly smaller. Blush sits under the near eye.
- Beak: a thin needle about two-thirds the body radius long, pointing right. It doubles as a pointer.
- Tail: narrow where it leaves the body, wider and rounded at the tip, cocked up and leaning back about 15°. About 40% of the body height shows above the back.
- Measuring tape: a band around the neck between face and belly, with one free end hanging down the chest.

Silhouette test: filled solid, Fitz must still read as round bird + tail up + needle beak. At 32 px the cap and tape still show; at 16 px the tape and belly are dropped and only body, cap, tail, one eye and beak remain.

## Do / don't

Do
- Keep the tail cocked up in every pose. It is the silhouette.
- Keep the cap rufous and the tape yellow; they are the two things people remember.
- Let the beak point at the thing being talked about (a result, a button).
- Use `fitz-16.svg` / `fitz-32.svg` for favicons and small UI; don't shrink `fitz.svg`.

Don't
- Don't add more shapes (no hat, no glasses, no hands). Props come from the beak or the tape.
- Don't recolour the body or cap, stretch, or rotate Fitz so the tail points sideways.
- Don't put text inside the character.
- Don't show the happy or proud face next to an unverified result. Fitz only celebrates what passed a test.

On dark backgrounds the brown outline fades but the colour shapes still read. For very small sizes on dark, put the icon on a cream (`#FFF3D3`) circle or rounded square.

## Which state goes with which product moment

| State / expression | Product moment |
|---|---|
| `idle` | Waiting for the user's request |
| `searching` | `find_software` / `find_alternatives` is running |
| `thinking` | Asking the user a clarifying question (OS, must be free/offline) |
| `testing` | Install and verification running in the sandbox |
| `recommending` | Presenting the pick: "this one fits" |
| `proud` | A result card for a verified pick |
| `happy` / `success` | Install guide finished and the tool works (`report_outcome` success) |
| `test-failed` / `sorry` | Verification failed, or nothing fits; say so plainly |
| `surprised` | Unexpected result, for example the built-in tool is already enough |
| `neutral` | Default on result cards and docs |

All animations are short loops (1.8–3.4 s) using CSS keyframes inside each SVG. They stop under `prefers-reduced-motion: reduce`; the still frame is the key pose (tape fully out, leaf held up, gap marked), so nothing is lost.

## Provenance

Original artwork, drawn as hand-written SVG (through `build.py`) on 2026-11-01 during the hackathon development period. ChatGPT-generated images were viewed only as style reference (proportions, eye style, line weight); none of them are included, traced or copied here.
