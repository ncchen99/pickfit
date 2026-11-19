# Applying the 11/19 proposals to the guarded files

The loop guard (scripts/loop_guard.py PROTECTED) keeps sessions from editing pickfit/schema.py, pickfit/score.py,
schema/ and pickfit/verify/judge.py, so these changes wait here as patches. Apply them in this order, on
`proposals/coverage` (or wherever pickfit/coverage.py is already merged), from the repository root:

```sh
git apply loop/proposals/security-schema.patch
git apply loop/proposals/video-captions.patch
git apply loop/proposals/tokens-t5-2-cli-judge-text-only.patch
git apply loop/proposals/coverage-scoring-b3v7.patch
git apply loop/proposals/coverage-rule6-unverified.patch
uv run pickfit score --refresh
uv run python scripts/export_schema.py --check
uv run pytest -q
```

Give them to `git apply` one at a time, in this order. Each call writes nothing when its patch does not apply. One
call with several patches does not work here: `git apply --check a.patch b.patch` checks b against the tree as it was
before a, so it fails on every file both touch (pickfit/schema.py, schema/software.v1.json).

| # | patch | what it changes |
|---|---|---|
| 1 | security-schema.patch | sec.v2 in pickfit/schema.py and schema/ (observation, assessment, coverage, gaps) |
| 2 | video-captions.patch | RunVideo captions, card-less chapters and R2 keys (schema.py, schema/); rebased onto 1 |
| 3 | tokens-t5-2-cli-judge-text-only.patch | the CLI judge sends a check's output once (judge.py and its test) |
| 4 | coverage-scoring-b3v7.patch | b3.v7 reworked for Verification Coverage (score.py, schema.py, schema/, scripts, tests); replaces scoring-b3v7.patch |
| 5 | coverage-rule6-unverified.patch | treasure rule 6 on (念誠 11/19): an unverified record loses the 69 cap and cannot be a treasure (schema.py, a score.py docstring, tests) |

The fourth patch's schema/software.v1.json is scripts/export_schema.py's output with all four applied, so the JSON is
never merged by hand. video-captions.patch was rebased onto security-schema.patch with no change in what it does:
its JSON hunks had landed 81 and 869 lines off (one out of order), which `patch` tolerates and `git apply` might
place differently. Checked on 11/19 in a copy outside every checkout, applying the four in order: every hunk lands
at its stated line (no offset, no fuzz), `export_schema.py --check` passes and the full Python suite passes;
security-schema.patch also passes `git apply --check` on the branch.

Patch 5 must be followed at once by `pickfit score --refresh` (offline, no model call): the stored scores still carry
the 69 cap, and records do not validate until they are rewritten. Checked on 11/19 the same way: treasures stay 161,
the 217 records at exactly 69.0 spread out, 108 unverified records with a sec.v1 known vulnerability move to the 79
cap (79.0: 150 -> 197), and the full suite passes after the refresh (2316 passed).

Through patch 4, with its default settings, nothing in a published quality total, confidence, cap or treasure moves. After the patches,
`pickfit score --refresh` moves the records to b3.v7 (formula version, scores.inputs, history, raw_total,
quality.security) and gives 124 records of "other" and the subject categories their pooled popularity (R8; none
gains or loses a treasure). The sec.v2 rescan (`pickfit security --all --write`) is the security patch's to run; its
effect on scores is the security level's, under the same default settings.

The treasure and cap rules 念誠 has not decided yet are settings (docs/proposals/coverage-distribution.md shows what
each would do): schema.SECURITY_CAP_LEVELS, SECURITY_NO_TREASURE_LEVELS, UNCHECKED_CAN_BE_TREASURE, UNVERIFIED_CAP,
TREASURE_MIN_SECURITY_COVERAGE, TREASURE_MIN_FUNCTION_COVERAGE, and score.SECURITY_EXPOSED_DEDUCTION and
STALE_FIX_PENALTY. Switching one is a one-line change in a guarded file, then `pickfit score --refresh`. Before turning
on a coverage threshold, add pickfit/coverage.py to PROTECTED: its measures would then decide treasures.

## 6. capabilities-area-features-1-6.patch (capabilities step 3, 11/19)

On feat/capabilities-step2 (from 2f982b20 on), from the repository root:

```sh
git apply loop/proposals/capabilities-area-features-1-6.patch
uv run python scripts/export_schema.py --check
uv run pytest -q
```

It changes pickfit/schema.py and schema/ only in two places, plus one test line:

- FEATURES_DESCRIPTION asks for the 1-6 main features the sources put forward instead of 2-4, matching rule 8 of the
  extraction prompt (pickfit/extract.py, already changed). Until it is applied the schema the model reads still says
  2-4 while the prompt says 1-6.
- Capability gets an optional `area` (at most 30 characters): the group a capabilities-only extraction gives each
  capability (formats, subcommands). pickfit/profiles.py writes it as soon as the field exists; before that, records
  keep label and items and the extraction rows keep the area.

Checked on a clean checkout of 2f982b20 with the patch applied: export_schema --check passes, pytest 2365 passed and 7
skipped (the added line checks that a record keeps the area), worker 330 passed, typecheck clean. No score moves:
neither field is read by pickfit/score.py.
