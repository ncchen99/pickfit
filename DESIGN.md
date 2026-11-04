# pickfit design system: the fitting room

Written 2026-11-01; the identity pass of 11/3 (no cards, the measurement sheet, straight edges with one cut corner, the pin) is folded in. Product context is in [PRODUCT.md](PRODUCT.md); the mascot's own rules are in [brand/mascot/README.md](brand/mascot/README.md). The code that implements this file is `worker/src/ui/` (tokens, components, shell, icons) and the pages in `worker/src/page.ts` and `worker/src/pages/`.

## 1. Idea

Fitz is a tailorbird. Real tailorbirds pick leaves and stitch them into a nest that fits. pickfit does the same for software. It takes your measurements (OS, CPU, budget, offline), tries each tool on in a sandbox, and hands you only what fits.

So the page is a **tailor's fitting room**, not a SaaS dashboard, and its pages read as a tailor's worksheet: facts written down in rows, ruled lines between them, nothing boxed. The identity comes from that skeleton, not from decoration. Each thing in it comes from the room and does a job:

| Tailor's world | What it does on the page |
|---|---|
| **The room itself** (one quiet floor) | Every page is one ground, `--paper`, header and footer included, with a hairline between parts. The cutting mat, its grid and the rulers under each band are retired (11/3): a quiet room lets the conversation stand out. |
| **The worksheet** (no cards) | Only two surfaces exist on the whole site: your request (`--raised`) and Fitz's answer (`--voice`). Every other group (a section, a list, a pick under "Also fits", a Browse entry, Use it, At a glance, an aside, a notice) sits on the ground, set apart by a 1px `--rule` and space. Never a box inside a box; on a phone this is strict. |
| **The cut label** | The two surfaces where you and Fitz talk have their top-right corner cut off, like a tailor's label. Nothing else is cut. |
| **Measuring tape** (yellow, ticked) | The one signature, where you talk: the request field's baseline is Fitz's tape, fine ticks at rest, unrolled in full yellow while you type. The waiting tape uses it too. The quality and popularity readings keep its ticks in ink. The one action per screen is tape yellow. |
| **Fitz's voice** (his own olive) | Fitz's words: the first pick on results (his answer) and what he says while you wait. The only coloured surface on the site. |
| **Stitching** (rufous running stitch) | Verification. A record pickfit ran is stitched; anything it has not verified gets no stitch. The missing stitch is the label. |
| **Fitting ticket** | A pick or a catalog entry: the claim on top, the evidence below the seam. Only the first pick is a surface (Fitz's answer); the others are rows on the ground. |
| **Measurements** (the conditions) | The request: the need in your words plus OS, CPU, free, offline as switches. |
| **Measurement record** (the sheet) | Facts are written like a tailor's measurement record: one row per fact, the label and its value joined by a dotted leader (`measure()`). The first pick's verdict and a tool's At a glance. |
| **Dressmaker's pin** | Compare is pinning: a straight pin with a round head marks every Compare toggle and the compare tray. The word stays "Compare". |
| **Verbatim** (a ruled margin) | A 2px `--line-ctl` rule down the left of a block means "word for word from the run": commands and the README quote on home. |
| **Fitz** | The person in the room. Fitz greets you, works while you wait, says sorry when nothing fits, and never celebrates an unverified result. |

**Personality:** picky, honest, warm. **Voice:** plain, specific, short sentences. We say "not verified" and "pickfit hasn't run it on Windows" rather than hedge. No hype words, no exclamation marks except Fitz's own `!`.

**Write for the person choosing software (11/3).** Home, results, a tool page, Browse, Compare, the legend and the popovers say what the software does, whether it runs and works on your system, whether it is safe, how to install it and what the README got wrong, plus the trust promises (no ads, ranked by fit, privacy). How pickfit decides lives on /how: score weights and caps, the hidden-gem thresholds, how candidates were drawn and counted, which model picked and how reasons were checked. A product page may link there ("How scores work") but never restates those rules. Truth still wins over brevity: a vulnerable tool is flagged before its install steps, and an unchecked thing reads as unchecked.

## 2. Colour

Strategy (11/3): **one ground; colour lives in the conversation.** Everything sits on `--paper` and most things are ink and hairlines. Colour is spent where you and Fitz talk: your request is the one raised surface, outlined in Fitz's line colour with his tape as its baseline; Fitz's answer is in his olive, `--voice`, edged in `--voice-edge`; and each screen has one solid tape-yellow action. Other colour only carries meaning: `--pass` for a run that passed, `--caution` and `--fail`, `--stitch` for stitches and the focus ring. Dark is not made darker to feel calm: the more something matters, the lighter its surface.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#F7F7F4` | `#161613` | The one ground: every page, header and footer included |
| `--tag` | `#FFFFFF` | `#242521` | The base the soft state tints mix into. No card uses it any more: Browse, Use it and At a glance sit on the ground |
| `--raised` | `#FFFFFF` | `#2E2E29` | Your request, popovers, the legend, the compare tray, toasts |
| `--voice` | `#F1F6E2` | `#1E2413` | Fitz's words only: the first pick, his words while you wait (one block per screen) |
| `--voice-line` | `#CDD7AB` | `#394129` | Hairlines inside Fitz's answer (the fold's rows, README against reality) |
| `--voice-edge` | `#A9B77E` | `#5E6B40` | The 1px edge of `--voice` (2.0:1 light, 3.15:1 dark), so its cut corner reads beside your request's |
| `--sunk` | `#F0F1EC` | `#0E0F0C` | Meter tracks |
| `--leader` | `--line-ctl` at 55% | same | The measurement sheet's dotted leader (decoration, so under 3:1 is fine) |
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

Retired with the mat: `--mat`, `--mat-deep`, `--mat-line`, `--mat-line-2`, `--on-mat`, `--on-mat-2`, `--code`, `--code-ink`. Until the templates drop the `mat` class they are aliases of the new values (`--mat` is `--paper`, `--on-mat` is `--ink`). Retired with the code box (11/3): `--code-bg` (commands are left-ruled on the ground).

Soft tints of the state colours (`--pass-soft`, `--caution-soft`, `--fail-soft`, `--info-soft`) are the colour mixed into `--tag` at 12 to 18%. Fitz's palette (`brand/mascot/README.md`) is never recoloured; the UI takes its colours from him: `--voice` from his body's hue, `--tape` is his tape, `--stitch` his cap, `--fitz-line` his outline, `--tape-tab` the tape's tab.

Rules: body text is ≥4.5:1 on its ground, large text and controls ≥3:1. **One solid yellow per screen:** Find tools on home, the first pick's Copy on results (quiet when its steps ran on another OS than the one you chose), the tool page's Next (Open the site for a web app), Send it to Fitz on /submit. /agents has none: its Copy buttons look alike, so none reads as more important. "Connect your agent" on home is a quiet link. Meters, gems, counts and headline words are never yellow. Saturated green is only Fitz, a `--pass` fact or one block of `--voice`; in a measurement sheet green colours only a value a run proved (how far it got, offline when it worked, your system when it ran there). In dark mode shadows don't show, so lifts are hairlines. Every text and control pair was checked in both schemes for the 11/3 redesign (WCAG 2.x relative luminance).

## 3. Type

| Role | Face | Size / line height | Notes |
|---|---|---|---|
| Display | Bricolage Grotesque 700, opsz 96 | `clamp(2.3rem, 4.1vw, 3.5rem)` / 1.04; page heads `clamp(2rem, 3.2vw, 2.75rem)` | Hero and page titles. Tracking -0.03em. No yellow word. |
| Title | Bricolage Grotesque 700 | `clamp(1.6rem, 2.6vw, 2.2rem)` / 1.1 | Section titles, tool names on detail |
| Heading | Bricolage Grotesque 700 | 1.25rem / 1.25 | Ticket names, group headings |
| Label | Bricolage Grotesque 600 | 0.875rem / 1.2 | Buttons, chips, badges, table heads |
| Body | System UI stack | 1rem (17px root on desktop) / 1.55 | Reading text, max 68ch |
| Small | System UI stack | 0.875rem / 1.45 | Citations, captions |
| Measurement row | System UI stack | label 400 0.92rem in `--ink-3`; value 500 0.95rem in `--ink` / 1.45 | The measurement sheet: tabular figures, a dotted leader between |
| Code and readings | System mono stack | 0.875rem / 1.55 | Commands, tape readings, versions. Never as a costume. |

Bricolage Grotesque (OFL, self-hosted, Latin subset, `worker/public/assets/fonts/`) was picked for its ink-trap, slightly hand-cut shapes: crafted, warm and sturdy, like a tailor's ticket print, and still legible at UI sizes. Numbers in tables and meters use `font-variant-numeric: tabular-nums`.

## 4. Shape, depth, space

- **Straight edges (11/3):** 4px (`--r-card`, `--r-ctl`) for everything that is not a switch. 999px (a pill, `--r-pill`) only for switches: the chips (Free, Offline, Data stays local, the Browse filters and More filters' choices), the chosen option of the OS segmented control, the CPU select and the Compare toggle. Badges are plain text. Media is not a card: the clip's player keeps its dark frame with square corners.
- **The cut corner:** only the two conversation surfaces, your request (`.ask-card`) and Fitz's answer (the first pick, his waiting words in `.bubble`), have their top-right corner cut: `border-top-right-radius: var(--r-cut)` (16px) with `corner-top-right-shape: bevel`, inside `@supports (corner-shape: bevel)`. A browser without it shows the plain 4px corner. Playwright's Chromium 156 supports it (`CSS.supports('corner-shape','bevel')` is true; the computed shape is `superellipse(0)`).
- **Depth:** the two surfaces are flat: your request has its 2px outline and no shadow; Fitz's answer has its 1px `--voice-edge`. Lifts are only for what comes up to meet you: `--lift-3` (menus, popovers, the legend dialog), `--lift-2` (toasts, a chapter's tip); the compare tray has its own top shadow. Shadows with offset and blur in light, hairline rings in dark. Never a border and a wide shadow together.
- **Hairlines, not boxes:** every other group sits on the ground under a 1px `--rule` (inside Fitz's answer, `--voice-line`). Where a list already ends on a rule, the next group does not draw its own (a phone's single column included), so two rules never stack.
- **Outline:** a 2px `--fitz-line` outline is reserved for your request (it thickens to 3px while you type). Fitz's words are not outlined: they are in his colour, `--voice`. So you and Fitz each have one surface.
- **Stitch:** the `.seam` element, 7px stitches. Full width on the first pick; three stitches (31px) on every other verified item (Also fits, Browse cards). Used only on verified evidence: no stitch means not verified.
- **Space scale (px):** 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Groups are tight and sections are generous. A heading has more space above it than below.
- **Layout:** content max 1240px, 24px gutter (16px on phones). Reading columns max 68ch.

## 5. Components

Every component is a string helper in `worker/src/ui/kit.ts` with its CSS in `worker/src/ui/styles.ts`.

| Component | Class | States |
|---|---|---|
| Button | `.btn` + `.btn-primary` (tape, the one per screen, 1px `--tape-edge`) / `.btn-quiet` (transparent, 1px `--line-ctl`) / `.btn-ghost`; 4px corners | hover, active (press 1px), focus-visible (3px stitch ring), disabled, `aria-busy` (Fitz dots) |
| Request field | `.ask-card` + `.ask`: one of the two surfaces, flat, the cut corner | empty (placeholder shows a real example), focus (the outline thickens 2px to 3px as a ring, so nothing shifts, and the tape unrolls under your words with its tab; no transition under reduced motion), invalid (fail tint and message). Stacked on a phone, the field is the card's full width and grows to the whole sentence. |
| Chip / toggle | `.chip` (checkbox or radio inside): a pill, since it is a switch | off (1px `--line-ctl`), on (a faint ink tint, an ink ring, a check and bolder words: the same treatment as a selected segment, never a solid fill), hover, focus, disabled. A chip's icon is hidden (its word says it), except the Compare toggle's pin |
| Segmented control | `.seg` | the OS choice; radio inputs, keyboard arrows native. The options sit on the ground with no outline around the group (inside the request that would be a box in a box); the chosen one is ringed, a pill. The marks are 3:1 or more |
| Compare toggle and pin | `compareToggle()`, `icon('pin')` | the dressmaker's pin (pickfit's own drawing: a straight shaft and a solid round head, 24-unit grid, 1.75 stroke, round caps, `currentColor`) before the word Compare; pinned, the chip's check takes the pin's place. On a Browse entry the pin is the whole button (its name for screen readers and on hover) |
| OS tabs | `.os-tabs` (Use it on a tool page) | text tabs on a hairline, not a switch: the chosen system in ink, underlined 2px; the others `--ink-2` |
| Stage tabs | `.stage-tabs` (Install, Check it works, Start using it) | numbered text tabs, the current one underlined; a finished stage's number turns `--pass`. Every stage keeps its name on a phone (the row wraps) |
| Badge | `.badge` + `-pass` / `-gem` / `-free` / `-caution` / `-quiet`: plain text in its tone, not a pill; `marks` makes it icons only, named in a tooltip | static |
| Marks | `kindTag()`, `levelIcon()`, `osList()`, `sysTag()`, `runFacts()` | facts every card repeats (kind, how far the run got, OSes, where and when it ran) as one mark each, named on hover and for screen readers; `marksLegend()` explains them in the ticket legend and on /how |
| Check marks | `checkMark()`, `visualMark()`, `securityMark()` in tool.ts: `.check-marks` | a tool page's At a glance ends with its checks, one mark each and no sentence: an eye for the visual check of pickfit's screenshots (desktop and web apps) and a shield for known high or critical vulnerabilities (OSV.dev). Strokes in the state's tone, never a filled tile: green (`--pass`) checked and fine; an amber eye or a red shield with the count found, which opens what it counts (the eye opens a popover of what looks wrong; the shield jumps to the warning before the install steps); the same icon basted (dashed) in `--ink-3` when not checked, so it never reads as clean. The fact, with its source and day, is the tooltip (hover and focus, so a tap shows it) and the visually hidden name. `marksLegend()` has a row for each |
| Tape meter | `tape()` | value (an ink reading with the tape's ticks, never yellow), empty (not scored: hatched track and "not scored") |
| Coverage bar | `coverage()` | checked / not checked / failed segments with counts |
| Fitting ticket | `.pick` | resting, `:target` (stitch ring), entering (a short rise). The answer comes first: the first pick is Fitz's answer on `--voice`, the cut corner and nothing boxed inside it: name, fit sentence, the verdict as a measurement sheet beside the fit sentence on a wide screen and under it on a narrow one (your system or where it ran, how far the run got, offline when checked, setup, price), "On Linux instead? Use babelscribe." when another pick ran on a system it did not (the run's own level words), the full seam, then every step (up to three) in one left-ruled block with the screen's one solid-yellow Copy at the answer's right edge, and the README fix in full. A vulnerable pick says so after the seam, before its commands, on every ticket: the red shield, the count, OSV.dev and the day, and "See the list" to the tool page's warning (nothing for clean or unchecked). A step with sudo gets a Copy of its own; steps that ran on another OS than the one chosen say so first and their Copy is quiet. On a phone, one joined command gives its Copy to the Install line so the command has the full width. The others follow under "Also fits", rows on the ground under a hairline: name, kind, fit sentence, three stitches and the sheet's values on one line; their steps and README fix are in the fold and on the tool page. Reasons with citations, meters, the test record and the full steps (folded when they are all above) sit behind one "Why it fits and how we know" expander, which opens to rows on hairlines. |
| Measurement sheet | `measure(rows)` in kit.ts: `<dl class="measure">` | one row per fact: the label (`--ink-3`, system face, through `L()` so zh-TW reads 價格, 離線…), a dotted `--leader` that fills the gap, the value (`--ink`, tabular figures) at the right. A tone colours the value only: pass (a run proved it), caution (partial, another system, not verified), quiet ("not stated"). A row is never dropped: an empty value reads "not stated". A value never repeats its label ("Offline … Works", "Runs … On your machine"). Systems are OS marks, named on hover and for screen readers. At most 30rem wide; a row too long for its sheet puts its value under its label (container queries from `MEASURE_FITS`). Used for the first pick's verdict and a tool's At a glance; the scores under At a glance are tape readings whose tracks are all one length |
| Seam | `.seam` | verified evidence only |
| Command | `command()`, `.cmd` | a left-ruled block of monospace on the ground it sits on: no fill, no box, a 2px `--line-ctl` rule down its left (verbatim from the run). It wraps instead of scrolling, at a space: a word with a hyphen or a slash in it is kept whole (`.w`, a span that adds no text), so `--appdir` never splits into `--` and `appdir`; only a word longer than the line breaks inside. A wrapped part hangs 2ch in, and each line of several is its own block, so a continuation never reads as the next command. Copy is a quiet text button right after the command on its first line (yellow only where it is the screen's one action). Copy copies the text exactly as run. |
| Disclosure | `<details>` | one mark everywhere: a chevron before the words, pointing down, up once open. Works without the script. |
| Fitz says | `.says` | his words in a `--voice` bubble (the cut corner) with a Fitz state; `role="status"` when it reports progress. Over the results he stands without a bubble: the answer below is his. |
| Notice | `.notice` + `-busy` / `-error` / `-info` | with a Fitz state |
| Skeleton | `.skel` | the answer's shape on the ground under a hairline (a name, the fit, a dotted leader, a ruled command), no outline; it doesn't pulse (the unrolling tape is the only motion while Fitz looks) |
| Popover | `[popover]` + `.pop` | native popover API; opens on click or Enter; Esc closes |
| Dialog | `<dialog class="sheet">` | the ticket legend, on `--raised` over the `--scrim`, with no Fitz of its own (the page's is behind it); Esc closes and focus returns |
| Toast | `.toast` | copy and compare-tray feedback on `--raised`, `role="status"` |
| Compare tray | `.tray` | hidden, 1 to 4 tools, full (4). On `--raised`, no Fitz, each tool a name with its pin and a remove button (not pills); on a phone the names hide and one pin before the count says what it counts. A quiet Compare button: the screen's yellow stays with its action. While it shows, a tool page's clip gives up its height (`--tray-h`), so the play bar stays in the first view. |
| Navigation | `.top` | on the page ground. Current page underlined (not a pill); no Find (the logo goes home); Compare only while the tray holds tools (the script shows it) and on /compare itself. Without the script, Compare is in the footer, which always links to it. Mobile menu (`details`). |
| Sidebar | `.side` | the filters on Browse and At a glance on a tool page: groups under a hairline, no panel |
| Browse catalogue | `.cat-grid`, `.cat-card` | entries on the ground under hairlines, in columns where there is room (one on a phone): name, kind, one line, three stitches (verified), the OS marks, "Hidden gem" in words, Free, the pin. Not verified: a dashed (basting) line and no stitch |
| Use it | `.use-it` (tool page) | a section on the ground: OS tabs, stage tabs, numbered steps with left-ruled commands, README against reality as rows on hairlines, Next as the screen's yellow |
| Run ledger | `.runs-list`, `.fix` (home) | Recently tested: one row per run between hairlines (day, tool and its line, kind and system); beside it one README the run corrected, as a left-ruled quote |
| Level mark | `.level-i`, `.check` | a run's level as its mark drawn in `--pass` beside the words, never on a filled tile (results, tool page, legend, /how) |

## 6. Fitz on the page

| Moment | Asset | Where |
|---|---|---|
| Arriving at the home page | `states/fitz-hello.svg` | Hero, on the page ground beside the request card, `clamp(150px, 16vw, 220px)` |
| Waiting for input | `states/fitz-idle.svg` | Compact search bar on results |
| Search running | `states/fitz-searching.svg` | Loading panel, with a tape that unrolls |
| Picks found (model) | `states/fitz-recommending.svg` | Results header, over the answer, without a bubble (the hero's Fitz hides on results) |
| Clarifying question | `expressions/fitz-thinking.svg` | The question bubble |
| Nothing fits / no results | `expressions/fitz-sorry.svg` | Empty state |
| Model paused, busy, rate limited | `states/fitz-resting.svg` | Notices |
| Network or server error | `states/fitz-test-failed.svg` | Error notice |
| Verified record | `states/fitz-testing.svg` | /how: the Install stage (the home page's four steps are words only) |
| Install works (pass) | `states/fitz-success.svg` | Tool page header when a function-level run passed |
| Comparing | `states/fitz-comparing.svg` | Compare page header (the tray has no Fitz) |
| Hints and tips | `fitz-peek.svg` | Peeks over the top edge of a tip card |
| Favicon, nav mark | `icons/fitz-32.svg`, `icons/fitz-16.svg` | |
| 404 | `expressions/fitz-surprised.svg` | |

**One Fitz per screen** (11/1 distill, 11/3): Fitz speaks once, where something changed. The header's logo is the brand mark, not a second Fitz. Results carry one Fitz in the header; model-paused, partial-fit and clarifying notes are a quiet status list under it, not notices of their own, and "You may not need to install anything" is an aside in words. Page heads carry a 96px Fitz, so empty states and the legend dialog have none of their own. On the home page "How Fitz picks a tool" is four numbered steps in words; /how keeps the four Fitz. A tool page leads with pickfit's own clip of the app running when there is one (its chapters beside it); the head's Fitz is the only one on the page.

Rule from the mascot README: Fitz is happy or proud only next to something that passed a test. A partial or weak match gets `neutral` or `thinking`, and an unverified option gets no Fitz at all.

## 7. Motion

- **Easing:** `--ease-out: cubic-bezier(.16,1,.3,1)` for entrances, `--ease-in-out: cubic-bezier(.65,0,.35,1)` for state changes. **Durations:** 120ms (press), 200ms (hover, toggle), 360ms (reveal), 600ms (stitch draw).
- **The one authored moment:** when results arrive, the tickets settle in one after another (a short rise, transform only). Seams and tape meters render in their final state: they carry meaning, so they never depend on an animation running (a background tab or a paused timeline would otherwise leave them blank).
- Fitz's own loops live inside its SVGs and stop under reduced motion. The page adds only: the hero Fitz settling in once, the tape unrolling under the request while you type, the loading tape, the popover and dialog fade, and toast slide.
- `prefers-reduced-motion: reduce`: every animation and transition is off, and stitches and meters render in their final state.

## 8. Iconography and imagery

- Icons: Lucide (ISC), 24-unit grid, 1.75 stroke, round caps, `currentColor`. Only drawn icons; no emoji standing in for icons. Only the icons a page uses are kept in `icons.ts`. The pin is pickfit's own drawing on the same grid, its head filled.
- OS marks: Tux and Apple from Simple Icons (CC0), a four-pane window for Windows, filled in `currentColor`, kept once per page as a sprite. Green: pickfit ran it there; grey: the README claims it.
- An icon replaces words only for a fact with a few fixed values that every card repeats (the OS marks) and for a tool page's two checks (the eye and the shield under At a glance), whose words are their tooltip. Evidence (README fixes, steps, match labels, the fit sentence) stays in words, and so does "Hidden gem" on Browse and the outside links on Compare (Source code, Homepage): a stock glyph on every row is wallpaper, not a fact.
- An icon beside words that already say it is hidden (11/3, in CSS until the templates drop the `icon()` call): the condition chips, Find tools, the stats, a tool's kind, Browse filters, "Replayed from scratch" and "Works offline" in a run's facts, Test record, Copy, Source code and Homepage links. Kept: OS marks, the Browse search glass, disclosure chevrons, the pin (every Compare toggle, the icon-only Compare on a Browse entry, the tray), the date and version marks in a run's facts (their only label), the run's level mark (drawn in `--pass`, no tile), and the file mark that opens a reason's citation. A reason has no mark of its own any more.
- Illustration: Fitz and its props (package, leaf, tape) only. No stock photos, no 3D blobs, no gradients.
- Texture: none. One flat ground; the cutting-mat grid and rulers are retired.

## 9. Density (Impeccable distill, 11/1)

One focal point per view: the request card on the home hero; the first pick (Fitz's answer, with its steps and the one Copy) on results; on a tool page pickfit's recorded clip when there is one, with its play bar in the first view at any window height (the compare tray included), and otherwise the "Use it" section, which then comes before "What it does"; the list on Browse; the differing rows on Compare (identical rows collapse into "Same for all of them"). Home sections below the hero are a title plus one line each. Browse shows 30 entries and a "Show more"; the text filter searches all of them. What everyone shares is said once, and evidence stays one click away in a `<details>`, never deleted.

## 10. Refused (from Impeccable's craft floor, and ours)

No cards beyond the two conversation surfaces, and never a box inside a box. No eyebrow labels over headings, no gradient text, no glass, no hard offset shadows, no identical icon-tile rows as page structure, no filled icon tiles, no stock glyph repeated on every row, no "AI is thinking" pulse. No side-stripe accent borders: the one left rule allowed is the 2px `--line-ctl` rule that means verbatim from the run (commands, the README quote on home), never a coloured stripe for emphasis. No pills except switches, and no cut corner except on the two conversation surfaces. Fitz does that job, honestly labelled. No status-chip clutter: at most three badges on a ticket. No number without its source.
