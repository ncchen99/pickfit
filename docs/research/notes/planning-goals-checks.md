# Planning agent: GUI goals and checks, before and after (11/3)

Branch `claude/planning-goals-checks`, off main. The reruns only measured: nothing was written back to
data/software.

## What changed (the planning agent and its spec checks only)
1. **The agent sees the app's window before it writes goals.**
   - After a `launch_gui` shows a window, the agent's next turn carries pickfit's screenshot of it: the part of
     the screen the app draws on, as the operator sees it.
   - The rules ask for goals that name the controls the screen shows, not shortcuts or screens guessed from the
     README.
   - A live probe confirmed that muse-spark-1.3 reads an image sent with tool outputs in a chained turn; Muse
     Spark Open read them in the reruns.
2. **Impossible checks are refused at spec time, before an operation is spent.** The refusal costs no command;
   the agent gets the reason and rewrites the spec.
   - **Expected text the goal names** (whole words, case kept): the operator can type it or read it off the goal.
     Allowed only when it is stored in a file the app saves.
   - **Text the launch screenshot already shows** (screen_text): the screen reader reads that screenshot once for
     the expected texts without {nonce}.
   - **Text expected inside a file whose raw bytes cannot show it**: a compressed container, a PDF, an image or
     media.
3. **Every check names the feature's effect it proves**: `check.effect` (a few words) and `check.effect_kind`.

   | `effect_kind` | means | rule |
   |---|---|---|
   | `computed` | a value the app computes, converts or generates | |
   | `converted_file` | a file in another format | needs `format` |
   | `loaded` | text of an input file the app opens or finds | the text must be in an input file |
   | `stored` | something the app creates or saves | the only kind that may hold typed text, in a saved file |

   Specs without them are refused, and refused specs are kept in the run's trace (`refused_specs`). Replays of
   older operations, which have no effect fields, are not affected.

## How it was measured
**The features.** From `unchecked-causes.json` (branch claude/unchecked-causes), the Linux features whose cause
was check design (`not_shown`, can't pass, check failed, no checkable result) or operator circling or limits:
- 24 features on 10 apps without a GPU: comic-book-reader, hivemind, imageflow, nip4, portfolio, pysolfc,
  quran-companion, termul, termy, waywallen;
- freeorion, usdx and vimix (GPU boxes) were left out.

**The tasks.** `scripts/rerun_planning.py prepare` built one fixture per app, used by both arms:
- the repository and README from GitHub;
- a fresh muse-spark-1.3 extraction ($0.11);
- as its features, only the affected ones, each with its record's README quote.

**The two arms.** Each ran the full verify pipeline (agent, fresh-box replay, judges) with write-back off, in the
same window, on the same boxes (Modal; hivemind VM, the rest gVisor with display) and the same tasks:
- **old** = a checkout of main (bc4ee316);
- **new** = this branch.

**Which model ran.** The first pass ran the agent on muse-spark-1.3. Meta's API began answering 402
`billing_not_configured` at 04:21, so most of those runs died in the agent or the judges. They are dropped, not
counted as failures. The comparison below is a second pass:
- **agent and all judges:** Muse Spark Open on Modal (`open-modal`, both arms);
- **operator:** open-modal;
- **each run's spend:** capped at $0.45.

One run per app per arm. Rerun variance is large: quran-companion F3 passed in every rerun of the earlier
comparison.

## Results (open-modal, one run per arm)
"Before" is the cause recorded for the feature's last run (unchecked-causes). Each cell gives the recorded status
(or "no record" when the run's install was not verified, so no feature is recorded), then:
- the operations spent, with how many passed pickfit's own check in the agent's box;
- the operator steps used;
- specs refused at spec time.

| app: feature | before (record) | old (main) | new (branch) |
|---|---|---|---|
| comic-book-reader: convert comic books | operator loop | operator_limit; 1 op (0 passed), 28 steps | no record; 2 ops (0), 46 steps, 2 refused |
| comic-book-reader: read CBZ … | check: text typed / already on screen | operator_limit; 1 op (0), 28 steps | no record; 2 ops (1), 22 steps, 2 refused |
| comic-book-reader: single or double page | judge: not shown | operator_limit; 0 ops | no record; 0 ops |
| hivemind: build workspace views and widgets | judge: check passed, not shown | not_shown; 1 op (1), 8 steps | not_shown; 1 op (1), 21 steps, 1 refused |
| hivemind: run coding agents side by side | operator loop | check_not_met; 2 ops (0), 15 steps | not_shown; 1 op (1), 7 steps |
| hivemind: steer other agents via hive ctl | check: cited command failed | not_shown; 2 ops (1), 30 steps | **checked**; 1 op (1), 8 steps |
| imageflow: configure conversion parameters | operator loop (note) | no record; 1 op (0), 28 steps | no record; 0 ops |
| imageflow: convert video to GIF/WebP/AVIF | operator misclicked (note) | no record; 1 op (0), 28 steps | no record; 2 ops (0), 56 steps |
| imageflow: select video time range | operator misclicked (note) | no record; 1 op (0), 28 steps | no record; 0 ops |
| nip4: process very large images | operator loop | needs_service; 2 ops (0), 56 steps | not_shown; 2 ops (1), 32 steps, 2 refused |
| portfolio: copy, move and delete files | operator loop | check_not_met; 2 ops (0), 34 steps | operator_limit; 2 ops (0), 56 steps, 1 refused |
| pysolfc: play Solitaire games | operator step cap (note) | no record; 0 ops | no record; 1 op (1), 13 steps, 1 refused |
| quran-companion: download recitations | operator loop | no record; 0 ops | no record; 1 op (1), 28 steps, 1 refused |
| quran-companion: search Quran verses | check: text typed / already on screen | no record; 0 ops | no record; 2 ops (1), 56 steps, 2 refused |
| termul: AI agent chat | could not reach it (note) | no record; 0 ops | no record; 1 op (1), 28 steps |
| termul: Git integration | could not reach it (note) | no record; 2 ops (0), 11 steps | no record; 1 op (1), 9 steps |
| termul: multiple shells, split panes | operator loop (note) | no record; 2 ops (0), 25 steps | no record; 2 ops (1), 36 steps |
| termul: project-based workspaces | could not reach it (note) | no record; 2 ops (1), 31 steps | no record; 1 op (1), 26 steps, 2 refused |
| termy: keybindings, colors, themes | judge: not shown | not_attempted; 0 ops | not_shown; 2 ops (1), 6 steps |
| termy: GPU-accelerated rendering | no checkable result | not_shown; 2 ops (1), 8 steps | not_shown; 1 op (1), 3 steps, 1 refused |
| termy: tmux control-mode sessions | judge: not shown | not_attempted; 0 ops | not_shown; 1 op (1), 3 steps |
| termy: tabs, splits, search, layouts | judge: not shown | not_shown; 1 op (1), 6 steps | not_shown; 1 op (1), 3 steps |
| waywallen: smart playlists | operator loop | operator_limit; 2 ops (0), 28 steps | operator_limit; 2 ops (0), 56 steps, 1 refused |
| waywallen: discover plugins | judge: not shown | other (fresh box did not repeat); 1 op (1), 16 steps | other; 1 op (1), 3 steps, 3 refused |

| totals (24 features) | old (main) | new (branch) |
|---|---|---|
| checked | 0 | 1 |
| false failures: an operation passed pickfit's check, but the check or goal could not show the feature (`not_shown`, or pickfit's check refused an echo or text already on screen) | 8 | 7 |
| features with an operation that passed pickfit's check in the agent's box | 6 | 17 |
| operations spent | 26 | 30 |
| specs refused at spec time | 11 in the logs (none of the new kinds) | 19 (13 by the new rules) |
| operator steps | 408 | 518 |
| apps whose install was verified (features recorded) | 6 of 10 | 5 of 10 |
| model spend (Modal LLM) | $2.36 | $2.85 |
| boxes | $0.26 | $0.28 |

- **Refusals in the new arm.**

  | refused because | count | rule |
  |---|---|---|
  | a README label | 6 | old |
  | expected text in the goal | 5 | new |
  | `loaded` text in no input file | 4 | new |
  | text already on the launch screen | 1 | new |
  | `converted_file` without a format | 1 | new |
  | malformed input or check | 2 | old |

  Main's 11 logged refusals were all of the old kinds: per-feature operation limits, README labels, a file check
  with neither text nor format.
- **Why apps were unverified.** In both arms this was mostly the install proof: a smoke test that crashed,
  `head` hiding an exit code, an uncited script, the agent not finishing. In the new arm, three runs
  (comic-book-reader, quran-companion, termul) hit the $0.45 per-run cap before finish: the rewrites after
  refusals and the screenshot cost turns. With the production cap ($0.80) they would likely have finished. As
  run, the cap cost the new arm three apps' records.
- **The earlier muse-spark-1.3 pass, before the 402.** Only main's quran-companion run finished cleanly in both
  agent and judges (function, "search Quran verses" checked). The rest lost the agent or the judges to the 402;
  the raw rows are in the scratch tally, not used here.

**Cost of the whole measurement:**
- Meta $2.37: the first muse-spark-1.3 pass $2.25, the extractions $0.11 and the probe $0.01;
- Modal LLM $7.74: both open-modal arms $5.21, and the operators of the first pass $2.53;
- boxes about $0.95.

## Reading it
- **More operations now pass pickfit's own check: 17 features against 6.** Goals written from the screenshot
  reach the result more often; termul's four features each got one. The refusals moved checks away from echoes
  and on-screen labels.
- **The feature judge still refuses most of them (`not_shown` 7 against 4), so features checked moved only from
  0 to 1.**
  - The new rules stop checks that cannot pass. They do not make a check show the feature.
  - The `effect` an agent names is a claim. termy's "computed" checks were shell outputs (a keybinding list, help
    text, a theme name), which the judge rightly refused.
- **Costs.** The changes cost more operator steps (518 against 408) and more agent turns, and three apps' records
  at a tight cap.
- **Caveats.**
  - One run per arm.
  - The agent here is Muse Spark Open, not muse-spark-1.3 (which production uses).
  - Several features stayed unmeasured because the install did not verify.

  This is not evidence that the change raises coverage yet. It does show that the spec refusals work as
  intended (19 refused at no command cost; no refusal blocked a feature that then passed differently in the old
  arm).

## Suggestions (not done)
- **Show the feature judge the check's named effect**, and refuse at the judge an effect that is only an action
  occurring.
- **Or give the agent the judge's criteria at spec time**: a result must be something the feature makes, not a
  command's output or a list the app always prints.
- **Rerun on muse-spark-1.3 once billing works**, at the production cap, two runs per arm, before drawing a
  coverage conclusion.
- **The refusal message** for expected text in the goal now says the operator "can type it or read it off the
  goal". The rule refuses any expected text the goal names, not only typed text (e.g. "wait for PAGE ONE"). The
  measured runs carried the earlier wording "the operator types it"; the rule itself is unchanged.
