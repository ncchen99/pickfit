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

**Which model ran.** Two passes, each one run per app per arm. Rerun variance is large: quran-companion F3
passed in every rerun of the earlier comparison.
1. **open-modal:** the agent, all judges and the operator on Muse Spark Open (Modal); each run capped at $0.45.
   This pass was run because Meta's API answered 402 `billing_not_configured` from 04:21. The muse-spark-1.3 runs
   it cut short are dropped, not counted as failures.
2. **muse-spark-1.3 (production model):** through OpenRouter (`meta/muse-spark-1.3`, Meta as the only provider)
   once main routed Meta models there (eaf09788). Before it:
   - the branch was merged with main;
   - the old arm became a checkout of main at 05c0aeef.

   The agent and judges ran on muse-spark-1.3, the operator on open-modal. Each run was capped at $0.55 so
   that 20 runs stay under the $12 limit; production's cap is $0.80.

## Results, pass 1: open-modal
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

**Cost of the whole measurement, both passes:**
- Meta API $2.37: the muse-spark-1.3 pass cut short by the 402 $2.25, the extractions $0.11 and the probe $0.01;
- OpenRouter $7.75: pass 2, $7.29, plus the spot check, $0.46;
- Modal LLM $10.73:
  - open-modal arms $5.21;
  - operators of the cut-short pass $2.53;
  - operators of pass 2 $2.73;
  - the spot check's operator $0.22;
- boxes about $1.45.

## Results, pass 2: muse-spark-1.3 via OpenRouter
| app: feature | old (main 05c0aeef) | new (branch) |
|---|---|---|
| comic-book-reader: convert comic books | operator_limit; 2 ops (0 passed), 56 steps | no record; 2 ops (0), 39 steps |
| comic-book-reader: read CBZ … | other; 2 ops (0), 44 steps | no record; 1 op (1), 11 steps, 1 refused |
| comic-book-reader: single or double page | other; 1 op (1), 11 steps | no record; 1 op (1), 11 steps |
| hivemind: all three features | needs_account; 0 ops | needs_account; 0 ops |
| imageflow: convert video to GIF/WebP/AVIF | no record; 2 ops (0), 56 steps | no record; 2 ops (0), 56 steps |
| imageflow: the other two | no record; 0 ops | no record; 0 ops |
| nip4: process very large images | operator_limit; 2 ops (0), 56 steps | not_shown; 1 op (1), 6 steps |
| portfolio: copy, move and delete files | operator_limit; 2 ops (0), 56 steps | operator_limit; 2 ops (0), 56 steps |
| pysolfc: play Solitaire games | no record; 0 ops | no record; 0 ops |
| quran-companion: both features | not_attempted; 0 ops | no record; 0 ops |
| termul: multiple shells, split panes | no record; 2 ops (0), 56 steps | no record; 1 op (1), 15 steps |
| termul: project-based workspaces | no record; 2 ops (0), 56 steps | no record; 2 ops (0), 56 steps |
| termul: the other two | no record; 0 ops | no record; 0 ops |
| termy: keybindings, colors, themes | not_shown; 1 op (1), 4 steps | no record; 1 op (1), 6 steps, 1 refused |
| termy: GPU-accelerated rendering | not_shown; 1 op (1), 7 steps | no record; 1 op (1), 6 steps |
| termy: tmux control-mode sessions | other; 0 ops | no record; 1 op (1), 11 steps, 1 refused |
| termy: tabs, splits, search, layouts | not_shown; 1 op (1), 8 steps | no record; 2 ops (1), 23 steps, 1 refused |
| waywallen: smart playlists | operator_limit; 2 ops (0), 56 steps | no record; 2 ops (0), 56 steps |
| waywallen: discover plugins | **checked**; 1 op (1), 9 steps | no record; 2 ops (0), 10 steps, 2 refused |

## Totals, both passes (24 features, one run per arm)
| | old, open-modal | new, open-modal | old, muse-spark-1.3 | new, muse-spark-1.3 |
|---|---|---|---|---|
| checked | 0 | 1 | 1 | 0 |
| false failures (an operation passed pickfit's check, the check or goal could not show the feature) | 8 | 7 | 5 | 2 |
| features with an operation that passed pickfit's check (agent's box) | 6 | 17 | 5 | 8 |
| operations spent | 26 | 30 | 21 | 21 |
| specs refused at spec time | 11 (old kinds) | 19 (13 new kinds) | 2 (old kinds) | 6 (2 new kinds) |
| operator steps | 408 | 518 | 475 | 362 |
| apps whose install was verified (features recorded) | 6 of 10 | 5 of 10 | 7 of 10 | 3 of 10 |
| runs that hit the per-run cap | 0 | 3 | 2 | 5 |
| model spend | Modal LLM $2.36 | Modal LLM $2.85 | OpenRouter $3.50 | OpenRouter $3.79 |
| boxes | $0.26 | $0.28 | $0.25 | $0.20 |

**Why the new arm lost records on muse-spark-1.3.** It lost 7 of 10 apps' records:
- **five reached the $0.55 cap before finish:** imageflow, pysolfc, quran-companion, termul, termy;
- **comic-book-reader:** an install step piped into `head`;
- **waywallen:** a download step failed in the replay (curl exit 23).

The old arm lost 3: imageflow crashed, and pysolfc and termul reached the cap.

On OpenRouter, replay mode resends the whole history every turn, so a run costs about $0.35-0.55. The new agent's
extra turns (rewrites after refusals) and the screenshot it carries in every later turn put it over a cap that
main mostly stayed under. Its OpenRouter spend per run was 8% higher ($0.38 against $0.35).

**A defect the rerun found, now fixed.**
- **What happened:** for waywallen's "discover wallpapers via plugins", the new agent expected the library to
  list "photo.png", the name of the sample image pickfit wrote, as `loaded`. The rule accepted only text inside an
  input file, so it refused the check. The agent relabeled it `computed`, and it then failed.
- **The comparison:** in main's run the same feature passed with a similar check ("mywall") and was checked.
- **The fix:** `loaded` now also accepts an input file's name (commit after the runs, with a test).
- **The spot check:** waywallen rerun alone in the new arm with the fix.
  - The `loaded` check on "wallpaper.png" was now accepted and ran twice.
  - Both times the operator stopped at the step cap without reaching the listing.
  - The run then hit its $0.55 cap before finish.
  - Inconclusive: the rule no longer blocks the check, and nothing yet shows the check passing.

## Reading it
- **Neither pass shows a coverage gain.**
  - open-modal: 1 against 0 checked;
  - muse-spark-1.3: 0 against 1;
  - in each pass, 24 features with one run per arm.
- **What the change does do.**
  - More operations pass pickfit's own check: 17 against 6, and 8 against 5.
  - Fewer runs end in a check or goal failure: 7 against 8, and 2 against 5.
  - The new spec rules refused 15 specs of the new kinds across both passes, at no command cost.
- **What it costs.**
  - The feature judge still refuses most passing checks that are not the feature's own result. termy's checks
    were shell outputs that the agent labeled `computed`.
  - The new agent spends more turns per run. Under a tight per-run cap it loses more apps' records: 3 against 0
    on open-modal, 5 against 2 on muse-spark-1.3. That cost outweighed the gain in these runs.
  - One rule (`loaded`) was too strict and is now fixed.
- **Before merging, two things are worth doing:**
  - give the agent room: the production cap of $0.80, or fewer refusals by stating the rules in the tool
    description, which it already partly does;
  - rerun at least two runs per arm at the production cap.

## Suggestions (not done)
- **Show the feature judge the check's named effect**, and refuse at the judge an effect that is only a command's
  output or an action occurring. Or state the judge's criteria to the agent at spec time.
- **Cut the agent's extra turns.** Send the screenshot once instead of in every later turn: replay mode resends
  the history, and the image with it.
- **The refusal message** for expected text in the goal now says the operator "can type it or read it off the
  goal". The rule refuses any expected text the goal names, not only typed text (e.g. "wait for PAGE ONE"). The
  open-modal runs carried the earlier wording; the rule itself is unchanged.
