# Why desktop features end up "other": causes from saved evidence (11/3)

Script: `scripts/unchecked_causes.py` (rules only; `--ask-model` would send leftovers to Muse Spark Open, but
none were left, so the cost was $0). Per-feature rows: `unchecked-causes.json`.

## The set
For each desktop app's latest run per OS, the features `not_checked` with reason `other` or `not_shown`: 263 in
all.

| | features | of them |
|---|---|---|
| install-only runs | 170 (Linux 155, macOS 15) | clear cause, recorded as `other` with the note "install-only run" |
| rest, classified below | 93 (Linux 61, macOS 32) | 48 carry "no failed check in the log" (below), 20 are `not_shown` |

**The rewrite.** `resolve_features` kept a `test_failed` claim only when it cited a `run_command`. A failed
GUI operation the agent reported as `test_failed` therefore became `other` with "no failed check in the log; ...".
The harness's own record of why the operation stopped never reached the feature.

Each feature was read against its run's trace (`~/.pickfit/evidence/<run>/report.json`):
- the agent's claim and the commands it cited;
- every GUI operation for the feature: why it stopped, whether it looped (`circling`), and what pickfit's check
  found;
- the feature judge's verdict.

7 Linux runs (19 features) have no trace on this machine; those were classified from the note alone (marked
"note"):
- camelid, gemrb, imageflow, pysolfc, readany, termul, termy.

## Causes
| cause | Linux (note only) | macOS |
|---|---|---|
| GUI operator: going in circles | 10 (2) | 2 |
| GUI operator: other limits (out of steps 1, misclicks 2, could not reach it 3, gave up 1) | 7 (6) | 1 |
| app crashed, hung on a black screen, or showed an error | 10 | 0 |
| desktop piece missing (portal / file chooser, URL handler, Wayland, folder chooser) | 5 | 1 |
| dialog or result clipped off-screen | 3 (3) | 0 |
| check failed: operator said done but pickfit's check found nothing | 1 | 3 |
| check can't pass: expected text typed by the operator, on screen before the first action, or inside a zip | 2 | 2 |
| check failed: the cited command's check | 1 | 1 |
| feature judge: the check passed, the output did not show the feature (`not_shown`) | 9 (3) | 11 |
| replay: passed in the agent's box, not in the fresh box | 0 | 2 |
| no checkable result (visual-only, system effect, global hotkey) | 3 (1) | 4 |
| needs a model or download | 2 (1) | 0 |
| needs input data (ROM, game data, a book) | 2 (2) | 2 |
| needs a service or account | 2 | 0 |
| needs an OS permission or device (accessibility, microphone, sound card) | 1 | 2 |
| no desktop build in the box | 1 (1) | 1 |
| harness: daily budget, screenshot copy error | 2 | 0 |
| truly unknown | 0 | 0 |
| total | 61 (19) | 32 |

So about half of Linux's unclear features are the GUI operator (17) or the app itself (10). Earlier today's
comparison (`linux-gui-comparison.md`) found that more steps do not fix the operator cases.

The app's own log already showed some causes and was never kept on its own. portfolio's launch printed
"Unable to acquire session bus", which is the missing portal behind its unopened files.

## Built on branch claude/unchecked-causes
1. **Four finer reasons in `FeatureGap`:**

   | reason | means |
   |---|---|
   | `operator_limit` | out of steps, going in circles, or gave up |
   | `check_not_met` | the operator finished, but pickfit's check found nothing |
   | `app_error` | no window, a crash, or an error |
   | `needs_desktop` | a portal, URL handler or Wayland the display lacks |

   - `resolve_features` derives the first three from pickfit's own record of how the operation stopped (`step_cap`
     and `give_up` → `operator_limit`, `done` → `check_not_met`, `no_window` → `app_error`). It does this when
     every operation for a feature failed and the agent's reason is vague (`other`, `not_attempted`,
     `needs_display` or none, including a feature the agent left out of finish). The note starts with what the
     harness saw, e.g. "operation stopped: step_cap after 27 actions; check: file ~/pickfit-out/a.png: missing;
     <agent's note>".
   - `no_window` is `app_error` only when the harness had no error of its own:
     - box-user processes it could not stop: the reason stays `other`, with the error in the note;
     - no simulated microphone: `needs_hardware`;
     - a window whose screenshot pickfit could not read: the reason stays `other`.
   - `needs_display` left after that, in a box that launched a GUI, becomes `needs_desktop`.
   - The finish tool names `needs_desktop` and says that a failed `operate_gui` is reported `not_checked`, citing
     its command id.
   - Also updated: the Worker texts (`features.ts`; an unknown reason already falls back to `other`), the
     regenerated `schema/software.v1.json`, and the guarded write-back, which counts `needs_desktop` as a box limit.
2. **Install-only runs report `not_attempted`** instead of `other` (the rule in `agent.py`).
3. **`log_path` is filled.**
   - The pipeline writes `app.log` beside the trace: every GUI launch's and operation's own stdout and stderr,
     agent and replay, under a header naming the command (the last 3 KB each, as the launch keeps it).
   - `RunEvidence.log_path` points to it.
   - The operator's screenshots of every step, failed operations included, were already saved in the evidence
     directory.
4. **Reason `other` needs a note.**
   - The schema refuses `other` without one, whatever the status.
   - `resolve_features` writes "the agent named no cause" with a problem when the agent gave none (any status).
   - Coverage falls back to "no cause recorded" for a failed check that printed nothing.
   - Every existing record complies (no `other` without a note); the index builds 961 entries.

Tests: Python 1,549 passed; Worker 248 passed; the TypeScript check is clean.

## Not done (proposals)
- Records written before this change keep `other`.
  - Rewriting the 170 install-only features to `not_attempted`, and the 93 above to the new reasons, is a data
    write to data/software. It is the coordinator's call: `unchecked-causes.json` has the mapping.
  - The 19 note-only features would need their runs' traces, which are not on this machine. Evidence lives only
    on the machine that ran it, so uploading traces with the run would keep this from recurring.
- Two more codes, if wanted:
  - `no_checkable_result` (7: the feature's effect is visual or system-wide);
  - `needs_input` (4: a ROM, game data, a book).
- The structured-output review's progress-field variant for the operator (arm D) was not run within this time box.
