# pickfit design system: the fitting room

Written 2026-11-01. Product context is in [PRODUCT.md](PRODUCT.md); the mascot's own rules are in [brand/mascot/README.md](brand/mascot/README.md). The code that implements this file is `worker/src/ui/` (tokens, components, shell, icons) and the pages in `worker/src/page.ts` and `worker/src/pages/`.

## 1. Idea

Fitz is a tailorbird. Real tailorbirds pick leaves and stitch them into a nest that fits. pickfit does the same for software. It takes your measurements (OS, CPU, budget, offline), tries each tool on in a sandbox, and hands you only what fits.

So the page is a **tailor's fitting room**, not a SaaS dashboard. Each thing in it comes from that room and does a job:

| Tailor's world | What it does on the page |
|---|---|
| **The room itself** (one quiet floor) | Every page is one ground, `--paper`, header and footer included, with a hairline between parts. The cutting mat, its grid and the rulers under each band are retired (11/3): a quiet room lets the conversation stand out. |
| **Measuring tape** (yellow, ticked) | The one signature, where you talk: the request field's baseline is Fitz's tape, fine ticks at rest, unrolled in full yellow while you type. The waiting tape uses it too. The quality and popularity readings keep its ticks in ink. The one action per screen is tape yellow. |
| **Fitz's voice** (his own olive) | Fitz's words: the first pick on results (his answer) and what he says while you wait. The only coloured surface on the site. |
| **Stitching** (rufous running stitch) | Verification. A record pickfit ran is stitched; anything it has not verified gets no stitch. The missing stitch is the label. |
| **Fitting ticket** (paper tag) | A pick or a catalog entry: the claim on top, the evidence below the seam. |
| **Measurements card** (the conditions) | The request: the need in your words plus OS, CPU, free, offline as chips. |
| **Fitz** | The person in the room. Fitz greets you, works while you wait, says sorry when nothing fits, and never celebrates an unverified result. |

**Personality:** picky, honest, warm. **Voice:** plain, specific, short sentences. We say "not verified" and "pickfit hasn't run it on Windows" rather than hedge. No hype words, no exclamation marks except Fitz's own `!`.

## 2. Colour

Strategy (11/3): **one ground; colour lives in the conversation.** Everything sits on `--paper` and most things are ink and hairlines. Colour is spent where you and Fitz talk: your request is the one raised card, outlined in Fitz's line colour with his tape as its baseline; Fitz's answer is in his olive, `--voice`; and each screen has one solid tape-yellow action. Other colour only carries meaning: `--pass` for a run that passed, `--caution` and `--fail`, `--stitch` for stitches and the focus ring. Dark is not made darker to feel calm: the more something matters, the lighter its surface.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#F7F7F4` | `#161613` | The one ground: every page, header and footer included |
| `--tag` | `#FFFFFF` | `#242521` | Cards: Browse, the install box, At a glance |
| `--raised` | `#FFFFFF` | `#2E2E29` | Your request, popovers, the legend, the compare tray, toasts |
| `--voice` | `#F1F6E2` | `#1E2413` | Fitz's words only: the first pick, his words while you wait (one block per screen) |
| `--voice-line` | `#CDD7AB` | `#394129` | The 1px edge of `--voice` |
| `--sunk` | `#F0F1EC` | `#0E0F0C` | Wells, meter tracks |
| `--code-bg` | `#FFFFFF` | `#0E0F0C` | Command boxes (white with a hairline in light) |
| `--rule` | `#DEDFD9` | `#393A34` | Hairlines |
| `--line-ctl` | `#80817A` | `#7A7B74` | Control edges (≥3:1 on every ground) |
| `--ink` | `#1A1D17` | `#EBEAE2` | Text |
| `--ink-2` | `#4F5149` | `#BFBEB6` | Secondary text |
| `--ink-3` | `#65655E` | `#A5A59D` | Metadata, placeholders (≥4.5:1, also on `--voice`) |
| `--tape` | `#F5C243` | `#F5C243` | The one action per screen; the tape |
| `--tape-edge` | `#A57710` | `#F5C243` | Tape ticks and the action's 1px edge (tape on white is only 1.66:1) |
| `--tape-ink` | `#3A2905` | `#3A2905` | Text and ticks on tape |
| `--tape-tab` | `#C3CAD2` | `#C3CAD2` | The tape's metal tab |
| `--stitch` | `#C4552D` | `#E07A4F` | Stitching, brand dot, focus ring. Not for text (4.06:1 on light `--voice`) |
| `--fitz-line` | `#4A2E22` | `#93938A` | Your request's 2px outline (light: Fitz's own outline colour) |
| `--pass` | `#2E7A35` | `#7CCB7A` | Verified, checked, good match |
| `--caution` | `#8A5300` | `#F0B45A` | Partial match, not on your system |
| `--fail` | `#B23A26` | `#F08A73` | Test failed, errors |
| `--info` | `#28698A` | `#86C4E6` | Neutral information |
| `--scrim` | ink at 42% | `--sunk` at 78% | Behind the legend dialog |

Retired with the mat: `--mat`, `--mat-deep`, `--mat-line`, `--mat-line-2`, `--on-mat`, `--on-mat-2`, `--code`, `--code-ink`. Until the templates drop the `mat` class they are aliases of the new values (`--mat` is `--paper`, `--on-mat` is `--ink`).

Soft tints of the state colours (`--pass-soft`, `--caution-soft`, `--fail-soft`, `--info-soft`) are the colour mixed into `--tag` at 12 to 18%. Fitz's palette (`brand/mascot/README.md`) is never recoloured; the UI takes its colours from him: `--voice` from his body's hue, `--tape` is his tape, `--stitch` his cap, `--fitz-line` his outline, `--tape-tab` the tape's tab.

Rules: body text is ≥4.5:1 on its ground, large text and controls ≥3:1. **One solid yellow per screen:** Find tools on home, the first pick's Copy on results (quiet when its steps ran on another OS than the one you chose), the tool page's Next, Connect your agent on /agents. Meters, gems, counts and headline words are never yellow. Saturated green is only Fitz, a `--pass` fact or one block of `--voice`. In dark mode shadows don't show, so lifts are hairlines (`--lift-1` is a 1px `--rule` ring). Every text and control pair was checked in both schemes for the 11/3 redesign (WCAG 2.x relative luminance).

## 3. Type

| Role | Face | Size / line height | Notes |
|---|---|---|---|
| Display | Bricolage Grotesque 700, opsz 96 | `clamp(2.3rem, 4.1vw, 3.5rem)` / 1.04; page heads `clamp(2rem, 3.2vw, 2.75rem)` | Hero and page titles. Tracking -0.03em. No yellow word. |
| Title | Bricolage Grotesque 700 | `clamp(1.6rem, 2.6vw, 2.2rem)` / 1.1 | Section titles, tool names on detail |
| Heading | Bricolage Grotesque 700 | 1.25rem / 1.25 | Ticket names, card headings |
| Label | Bricolage Grotesque 600 | 0.875rem / 1.2 | Buttons, chips, badges, table heads |
| Body | System UI stack | 1rem (17px root on desktop) / 1.55 | Reading text, max 68ch |
| Small | System UI stack | 0.875rem / 1.45 | Citations, captions |
| Code and readings | System mono stack | 0.875rem / 1.55 | Commands, tape readings, versions. Never as a costume. |

Bricolage Grotesque (OFL, self-hosted, Latin subset, `worker/public/assets/fonts/`) was picked for its ink-trap, slightly hand-cut shapes: crafted, warm and sturdy, like a tailor's ticket print, and still legible at UI sizes. Numbers in tables and meters use `font-variant-numeric: tabular-nums`.

## 4. Shape, depth, space

- **Radius:** tickets and cards 14px, controls 10px, code 10px. 999px (a pill) only for switches: chips, the segmented control, selects. Badges are plain text.
- **Depth:** one system: `--lift-1` (resting card), `--lift-2` (hover, popovers), `--lift-3` (dialogs, the compare tray). Shadows with offset and blur in light, hairline rings in dark. Never a border and a wide shadow together. Fitz's answer (`--voice`) has no shadow, only its 1px `--voice-line`.
- **Outline:** a 2px `--fitz-line` outline is reserved for your request (it thickens to 3px while you type). Fitz's words are not outlined: they are in his colour, `--voice`. So you and Fitz each have one surface.
- **Stitch:** the `.seam` element, 7px stitches. Full width on the first pick; three stitches (31px) on every other verified item (Also fits, Browse cards). Used only on verified evidence: no stitch means not verified.
- **Space scale (px):** 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Groups are tight and sections are generous. A heading has more space above it than below.
- **Layout:** content max 1240px, 24px gutter (16px on phones). Reading columns max 68ch.

## 5. Components

Every component is a string helper in `worker/src/ui/kit.ts` with its CSS in `worker/src/ui/styles.ts`.

| Component | Class | States |
|---|---|---|
| Button | `.btn` + `.btn-primary` (tape, the one per screen, 1px `--tape-edge`) / `.btn-quiet` (transparent, 1px `--line-ctl`) / `.btn-ghost`; `.btn-on-mat` is a retired alias of quiet | hover, active (press 1px), focus-visible (3px stitch ring), disabled, `aria-busy` (Fitz dots) |
| Request field | `.ask-card` + `.ask` | empty (placeholder shows a real example), focus (the outline thickens 2px to 3px as a ring, so nothing shifts, and the tape unrolls under your words with its tab; no transition under reduced motion), invalid (fail tint and message). Stacked on a phone, the field is the card's full width and grows to the whole sentence. |
| Chip / toggle | `.chip` (checkbox or radio inside) | off (1px `--line-ctl`), on (a faint ink tint, an ink ring, a check and bolder words: the same treatment as a selected segment, never a solid fill), hover, focus, disabled |
| Segmented control | `.seg` | the OS and CPU choice; radio inputs, keyboard arrows native |
| Badge | `.badge` + `-pass` / `-gem` / `-free` / `-caution` / `-quiet`: plain text in its tone, not a pill; `marks` makes it icons only, named in a tooltip | static |
| Marks | `kindTag()`, `levelIcon()`, `osList()`, `sysTag()`, `runFacts()` | facts every card repeats (kind, how far the run got, OSes, where and when it ran) as one mark each, named on hover and for screen readers; `marksLegend()` explains them in the ticket legend and on /how |
| Tape meter | `tape()` | value (an ink reading with the tape's ticks, never yellow), empty (not scored: hatched track and "not scored") |
| Coverage bar | `coverage()` | checked / not checked / failed segments with counts |
| Fitting ticket | `.pick` | resting, `:target` (stitch ring), entering (a short rise). The answer comes first: the first pick is Fitz's answer on `--voice`: name, fit sentence, the verdict as plain facts between hairlines (your system, proof, setup, price), "On Linux instead? Use babelscribe." when another pick ran on a system it did not (the run's own level words), the full seam, then every step (up to three) in one block with the screen's one solid-yellow Copy, and the README fix in full. A step with sudo gets a Copy of its own; steps that ran on another OS than the one chosen say so first and their Copy is quiet. The others follow under "Also fits": name, kind, fit sentence, three stitches and one line of facts; their steps and README fix are in the fold and on the tool page. Reasons with citations, meters, the test record and the full steps (folded when they are all above) sit behind one "Why it fits and how we know" expander. |
| Fact sheet | `.facts` | known value, unknown ("not stated") |
| Seam | `.seam` | verified evidence only |
| Command | `command()`, `.cmd` | wraps instead of scrolling, as a terminal does (to the edge, not at a hyphen); a wrapped part hangs 2ch in, and each line of several is its own block, so a continuation never reads as the next command. Copy copies the text exactly as run. |
| Disclosure | `<details>` | one mark everywhere: a chevron before the words, pointing down, up once open. Works without the script. |
| Fitz says | `.says` | his words in a `--voice` bubble with a Fitz state; `role="status"` when it reports progress. Over the results he stands without a bubble: the answer below is his. |
| Notice | `.notice` + `-busy` / `-error` / `-info` | with a Fitz state |
| Skeleton | `.skel` | one dashed outline in the answer's shape; it doesn't pulse (the unrolling tape is the only motion while Fitz looks) |
| Popover | `[popover]` + `.pop` | native popover API; opens on click or Enter; Esc closes |
| Dialog | `<dialog class="sheet">` | the ticket legend, on `--raised` over the `--scrim`, with no Fitz of its own (the page's is behind it); Esc closes and focus returns |
| Toast | `.toast` | copy and compare-tray feedback on `--raised`, `role="status"` |
| Compare tray | `.tray` | hidden, 1 to 4 tools, full (4). On `--raised`, no Fitz, the tools as names with a remove button (not pills), and a quiet Compare button: the screen's yellow stays with its action. |
| Navigation | `.top` | on the page ground. Current page underlined (not a pill); no Find (the logo goes home); Compare only while the tray holds tools (the script shows it) and on /compare itself. Without the script, Compare is in the footer, which always links to it. Mobile menu (`details`). |
| Sidebar | `.side` | the request summary on results and the filters on browse |

## 6. Fitz on the page

| Moment | Asset | Where |
|---|---|---|
| Arriving at the home page | `states/fitz-hello.svg` | Hero, on the page ground beside the request card, `clamp(150px, 16vw, 220px)` |
| Waiting for input | `states/fitz-idle.svg` | Compact search bar on results |
| Search running | `states/fitz-searching.svg` | Loading panel, with a tape that unrolls |
| Picks found (model) | `states/fitz-recommending.svg` | Results header, over the answer, without a bubble (the hero's Fitz hides on results) |
| Clarifying question | `expressions/fitz-thinking.svg` | The question bubble |
| Nothing fits / no results | `expressions/fitz-sorry.svg` | Empty state |
| Built-in is enough | `expressions/fitz-surprised.svg` | "You may not need to install anything" |
| Model paused, busy, rate limited | `states/fitz-resting.svg` | Notices |
| Network or server error | `states/fitz-test-failed.svg` | Error notice |
| Verified record | `states/fitz-testing.svg` | /how: the Install stage (the home page's four steps are words only) |
| Install works (pass) | `states/fitz-success.svg` | Tool page header when a function-level run passed |
| Comparing | `states/fitz-comparing.svg` | Compare page header (the tray has no Fitz) |
| Hints and tips | `fitz-peek.svg` | Peeks over the top edge of a tip card |
| Favicon, nav mark | `icons/fitz-32.svg`, `icons/fitz-16.svg` | |
| 404 | `expressions/fitz-surprised.svg` | |

**One Fitz per screen** (11/1 distill, 11/3): Fitz speaks once, where something changed. Results carry one Fitz in the header; model-paused, partial-fit and clarifying notes are a quiet status list under it, not notices of their own. Page heads carry a 96px Fitz, so empty states and the legend dialog have none of their own. On the home page "How Fitz picks a tool" is four numbered steps in words; /how keeps the four Fitz. A tool page leads with pickfit's own clip of the app running when there is one (its chapters beside it); the head's Fitz is the only one on the page.

Rule from the mascot README: Fitz is happy or proud only next to something that passed a test. A partial or weak match gets `neutral` or `thinking`, and an unverified option gets no Fitz at all.

## 7. Motion

- **Easing:** `--ease-out: cubic-bezier(.16,1,.3,1)` for entrances, `--ease-in-out: cubic-bezier(.65,0,.35,1)` for state changes. **Durations:** 120ms (press), 200ms (hover, toggle), 360ms (reveal), 600ms (stitch draw).
- **The one authored moment:** when results arrive, the tickets settle in one after another (a short rise, transform only). Seams and tape meters render in their final state: they carry meaning, so they never depend on an animation running (a background tab or a paused timeline would otherwise leave them blank).
- Fitz's own loops live inside its SVGs and stop under reduced motion. The page adds only: the hero Fitz settling in once, the tape unrolling under the request while you type, the loading tape, the popover and dialog fade, and toast slide.
- `prefers-reduced-motion: reduce`: every animation and transition is off, and stitches and meters render in their final state.

## 8. Iconography and imagery

- Icons: Lucide (ISC), 24-unit grid, 1.75 stroke, round caps, `currentColor`. Only drawn icons; no emoji standing in for icons.
- OS marks: Tux and Apple from Simple Icons (CC0), a four-pane window for Windows, filled in `currentColor`, kept once per page as a sprite. Green: pickfit ran it there; grey: the README claims it.
- An icon replaces words only for a fact with a few fixed values that every card repeats. Evidence (README fixes, steps, match labels, the fit sentence) stays in words.
- An icon beside words that already say it is hidden (11/3, in CSS until the templates drop the `icon()` call): the condition chips, Find tools, the stats, a tool's kind, Browse filters, the verdict cells, a reason's mark, "Replayed from scratch" and "Works offline" in a run's facts, Test record, Copy, Source code and Homepage links. Kept: OS marks, the Browse search glass, disclosure chevrons, icon-only controls (Compare on a Browse card), the date and version marks in a run's facts (their only label), the run's level mark, and the file mark that opens a reason's citation.
- Illustration: Fitz and its props (package, leaf, tape) only. No stock photos, no 3D blobs, no gradients.
- Texture: none. One flat ground; the cutting-mat grid and rulers are retired.

## 9. Density (Impeccable distill, 11/1)

One focal point per view: the request card on the home hero; the first pick (Fitz's answer, with its steps and the one Copy) on results; on a tool page pickfit's recorded clip when there is one, with its play bar in the first view at any window height, and otherwise the "Use it" install box, which then comes before "What it does"; the list on Browse; the differing rows on Compare (identical rows collapse into "Same for all of them"). Home sections below the hero are a title plus one line each. Browse shows 30 cards and a "Show more"; the text filter searches all of them. What everyone shares is said once, and evidence stays one click away in a `<details>`, never deleted.

## 10. Refused (from Impeccable's craft floor, and ours)

No eyebrow labels over headings, no gradient text, no glass, no side-stripe accent borders, no hard offset shadows, no nested cards, no identical icon-tile rows as page structure, no "AI is thinking" pulse. Fitz does that job, honestly labelled. No status-chip clutter: at most three badges on a ticket. No number without its source.
