# pickfit design system: the fitting room

Written 2026-11-01. Product context is in [PRODUCT.md](PRODUCT.md); the mascot's own rules are in [brand/mascot/README.md](brand/mascot/README.md). The code that implements this file is `worker/src/ui/` (tokens, components, shell, icons) and the pages in `worker/src/page.ts` and `worker/src/pages/`.

## 1. Idea

Fitz is a tailorbird. Real tailorbirds pick leaves and stitch them into a nest that fits. pickfit does the same for software. It takes your measurements (OS, CPU, budget, offline), tries each tool on in a sandbox, and hands you only what fits.

So the page is a **tailor's fitting room**, not a SaaS dashboard. Each thing in it comes from that room and does a job:

| Tailor's world | What it does on the page |
|---|---|
| **Cutting mat** (deep green, with a measuring grid and ruler edge) | The ground of the hero, the results header and the footer: where the fitting happens. The grid is allowed because it is a measuring surface. |
| **Measuring tape** (yellow, ticked) | Every measurement: quality, popularity, feature checks, setup steps, freshness. Primary actions are tape yellow too. |
| **Stitching** (rufous running stitch) | Verification. A record pickfit ran is stitched; anything it has not verified gets no stitch. The missing stitch is the label. |
| **Fitting ticket** (paper tag) | A pick or a catalog entry: the claim on top, the evidence below the seam. |
| **Measurements card** (the conditions) | The request: the need in your words plus OS, CPU, free, offline as chips. |
| **Fitz** | The person in the room. Fitz greets you, works while you wait, says sorry when nothing fits, and never celebrates an unverified result. |

**Personality:** picky, honest, warm. **Voice:** plain, specific, short sentences. We say "not verified" and "pickfit hasn't run it on Windows" rather than hedge. No hype words, no exclamation marks except Fitz's own `!`.

## 2. Colour

Strategy: **Committed.** Mat green owns whole regions (hero, results header, footer). Paper carries reading. Tape yellow marks the one primary action per view. Rufous is for stitching and the brand dot, never for large fills.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--mat` | `#1D3D2A` | `#16301F` | Cutting-mat field |
| `--mat-deep` | `#132A1C` | `#0E2015` | Mat shadows, footer base |
| `--mat-line` | cream at 12% | cream at 10% | Mat grid and ruler ticks |
| `--on-mat` | `#F4F1DE` | `#F4F1DE` | Text on mat |
| `--on-mat-2` | `#C9D3B4` | `#B7C3A2` | Secondary text on mat (≥4.5:1) |
| `--paper` | `#F4F5EC` | `#101A13` | Page ground |
| `--sunk` | `#E9ECDD` | `#0B140E` | Wells, code blocks in light |
| `--tag` | `#FFFEF7` | `#18241B` | Tickets, cards, popovers |
| `--ink` | `#17231A` | `#ECEFE3` | Text |
| `--ink-2` | `#4B584E` | `#B4BEB0` | Secondary text |
| `--rule` | `#D5DAC6` | `#2A382D` | Hairlines (1px, only where a grid needs them) |
| `--tape` | `#F5C243` | `#F5C243` | Primary buttons, tape meters |
| `--tape-ink` | `#3A2905` | `#3A2905` | Text on tape |
| `--stitch` | `#C4552D` | `#E07A4F` | Stitching, brand dot, focus accents |
| `--pass` | `#2E7A35` | `#7CCB7A` | Verified, checked, good match |
| `--caution` | `#8A5300` | `#F0B45A` | Partial match, not on your system |
| `--fail` | `#B23A26` | `#F08A73` | Test failed, errors |
| `--info` | `#28698A` | `#86C4E6` | Neutral information |

Soft tints of the state colours (`--pass-soft`, `--caution-soft`, `--fail-soft`) are the colour mixed into `--tag` at 14%. Fitz's palette (`brand/mascot/README.md`) is never recoloured; the UI palette is derived from it (mat from the olive family, tape and stitch from the tape and cap).

Rules: body text is ≥4.5:1 on its ground, large text ≥3:1. Secondary text on a coloured ground is tinted from that ground (`--on-mat-2`), never grey. State colour appears only where it carries meaning.

## 3. Type

| Role | Face | Size / line height | Notes |
|---|---|---|---|
| Display | Bricolage Grotesque 800, opsz 96 | `clamp(2.6rem, 5.4vw, 4.6rem)` / 1.0 | Hero and page titles. Tracking -0.03em. |
| Title | Bricolage Grotesque 700 | `clamp(1.6rem, 2.6vw, 2.2rem)` / 1.1 | Section titles, tool names on detail |
| Heading | Bricolage Grotesque 700 | 1.25rem / 1.25 | Ticket names, card headings |
| Label | Bricolage Grotesque 600 | 0.875rem / 1.2 | Buttons, chips, badges, table heads |
| Body | System UI stack | 1rem (17px root on desktop) / 1.55 | Reading text, max 68ch |
| Small | System UI stack | 0.875rem / 1.45 | Citations, captions |
| Code and readings | System mono stack | 0.875rem / 1.55 | Commands, tape readings, versions. Never as a costume. |

Bricolage Grotesque (OFL, self-hosted, Latin subset, `worker/public/assets/fonts/`) was picked for its ink-trap, slightly hand-cut shapes: crafted, warm and sturdy, like a tailor's ticket print, and still legible at UI sizes. Numbers in tables and meters use `font-variant-numeric: tabular-nums`.

## 4. Shape, depth, space

- **Radius:** tickets and cards 14px, controls 10px, chips and badges 999px, code 10px.
- **Depth:** one system, shadows with offset and blur: `--lift-1` (resting ticket), `--lift-2` (hover, popovers), `--lift-3` (dialogs, the compare tray). Never a border and a wide shadow together.
- **Outline:** a 2px ink outline is reserved for the request field and Fitz's speech bubble. It echoes Fitz's own outline and marks the places where you and Fitz talk.
- **Stitch:** `border-top: 2px dashed var(--stitch)` with 6px dashes, or the `.seam` element. It is used only on verified evidence.
- **Space scale (px):** 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Groups are tight and sections are generous. A heading has more space above it than below.
- **Layout:** content max 1240px, 24px gutter (16px on phones). Reading columns max 68ch.

## 5. Components

Every component is a string helper in `worker/src/ui/kit.ts` with its CSS in `worker/src/ui/styles.ts`.

| Component | Class | States |
|---|---|---|
| Button | `.btn` + `.btn-primary` (tape) / `.btn-quiet` (paper) / `.btn-ghost` / `.btn-on-mat` | hover (lift), active (press 1px), focus-visible (3px stitch ring), disabled, `aria-busy` (Fitz dots) |
| Request field | `.ask` | empty (placeholder shows a real example), focus (ink outline thickens, tape underline), invalid (fail tint and message) |
| Chip / toggle | `.chip` (checkbox or radio inside) | off, on (ink fill), hover, focus, disabled |
| Segmented control | `.seg` | the OS and CPU choice; radio inputs, keyboard arrows native |
| Badge | `.badge` + `-pass` / `-gem` / `-free` / `-caution` / `-quiet` | static |
| Tape meter | `tape()` | value, empty (not scored: hatched track and "not scored") |
| Coverage bar | `coverage()` | checked / not checked / failed segments with counts |
| Fitting ticket | `.ticket` | resting, hover (lift-2), `:target` (stitch ring), entering (stitch draws on) |
| Fact sheet | `.facts` | known value, unknown ("not stated") |
| Seam | `.seam` | verified evidence only |
| Fitz says | `.says` | speech bubble with a Fitz state; `role="status"` when it reports progress |
| Notice | `.notice` + `-busy` / `-error` / `-info` | with a Fitz state |
| Skeleton | `.skel` | shimmer, still under reduced motion |
| Popover | `[popover]` + `.pop` | native popover API; opens on click or Enter; Esc closes |
| Dialog | `<dialog class="sheet">` | the ticket legend; Esc closes and focus returns |
| Toast | `.toast` | copy and compare-tray feedback, `role="status"` |
| Compare tray | `.tray` | hidden, 1 to 4 tools, full (4) |
| Navigation | `.top` | current page (`aria-current`), mobile menu (`details`) |
| Sidebar | `.side` | the request summary on results and the filters on browse |

## 6. Fitz on the page

| Moment | Asset | Where |
|---|---|---|
| Arriving at the home page | `states/fitz-hello.svg` | Hero, on the mat, beside the request field |
| Waiting for input | `states/fitz-idle.svg` | Compact search bar on results |
| Search running | `states/fitz-searching.svg` | Loading panel, with a tape that unrolls |
| Picks found (model) | `states/fitz-recommending.svg` | Results header: "These fit." |
| Clarifying question | `expressions/fitz-thinking.svg` | The question bubble |
| Nothing fits / no results | `expressions/fitz-sorry.svg` | Empty state |
| Built-in is enough | `expressions/fitz-surprised.svg` | "You may not need to install anything" |
| Model paused, busy, rate limited | `states/fitz-resting.svg` | Notices |
| Network or server error | `states/fitz-test-failed.svg` | Error notice |
| Verified record | `states/fitz-testing.svg` | How it works: Install stage; tool page evidence |
| Install works (pass) | `states/fitz-success.svg` | Tool page header when a function-level run passed |
| Comparing | `states/fitz-comparing.svg` | Compare page header, compare tray |
| Hints and tips | `fitz-peek.svg` | Peeks over the top edge of a tip card |
| Favicon, nav mark | `icons/fitz-32.svg`, `icons/fitz-16.svg` | |
| 404 | `expressions/fitz-surprised.svg` | |

Rule from the mascot README: Fitz is happy or proud only next to something that passed a test. A partial or weak match gets `neutral` or `thinking`, and an unverified option gets no Fitz at all.

## 7. Motion

- **Easing:** `--ease-out: cubic-bezier(.16,1,.3,1)` for entrances, `--ease-in-out: cubic-bezier(.65,0,.35,1)` for state changes. **Durations:** 120ms (press), 200ms (hover, toggle), 360ms (reveal), 600ms (stitch draw).
- **The one authored moment:** when results arrive, each ticket's seam is stitched on (the dash pattern draws left to right), then its tape meters extend to their reading. It says "these were measured" without a word.
- Fitz's own loops live inside its SVGs and stop under reduced motion. The page adds only: the hero Fitz settling in once, hover lift on tickets, the loading tape, the popover and dialog fade, and toast slide.
- `prefers-reduced-motion: reduce`: every animation and transition is off, and stitches and meters render in their final state.

## 8. Iconography and imagery

- Icons: Lucide (ISC), 24-unit grid, 1.75 stroke, round caps, `currentColor`. Only drawn icons; no emoji standing in for icons.
- Illustration: Fitz and its props (package, leaf, tape) only. No stock photos, no 3D blobs, no gradients.
- Texture: the cutting-mat grid on mat fields only. Paper stays flat.

## 9. Refused (from Impeccable's craft floor, and ours)

No eyebrow labels over headings, no gradient text, no glass, no side-stripe accent borders, no hard offset shadows, no nested cards, no identical icon-tile rows as page structure, no "AI is thinking" pulse. Fitz does that job, honestly labelled. No status-chip clutter: at most three badges on a ticket. No number without its source.
