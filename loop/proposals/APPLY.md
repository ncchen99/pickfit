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
| 6 | coverage-rule1-conditional.patch | treasure rule 1 on (decided 11/20, after the sec.v2 rescan): conditional loses the 79 cap, blocked and exposed keep it (schema.py, a score.py docstring, tests, the How page and its worker test) |

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

## 11/20: rule 1 (coverage-rule1-conditional.patch)

Patches 1-5 are on main since 11/19, and the sec.v2 rescan is on postlaunch/20261120. On that branch, from the
repository root, apply the sixth on its own and refresh at once (the stored scores still carry the conditional cap,
and the records do not validate until they are rewritten):

```sh
git apply loop/proposals/coverage-rule1-conditional.patch
uv run pickfit score --refresh
uv run python scripts/export_schema.py --check
uv run pytest -q
```

Checked on 11/20 in a copy outside every checkout: the refresh rewrites 305 records, treasures 165 -> 203, records at
exactly 79.0 186 -> 5, the schema check passes (the JSON schema does not change), 2369 passed; the Worker builds,
typechecks and passes its tests but test/cloudrun.test.ts (aws4fetch missing there). A conditional record's
security.status still reads vulnerable, so the MCP server and the page still warn about it.

## 11/20: what the feature judge reads (feature-judge-output-head-and-colour.patch)

On feat/opt-worker-judges, from the repository root:

```sh
git apply loop/proposals/feature-judge-output-head-and-colour.patch
uv run pytest -q tests/test_verify_features.py
```

pickfit/verify/feature_judge.py (guarded) and one test. Why: of the features the judge did not see working
(`function.not_shown`, 492 features in 273 records), the 53 whose runs this machine kept show two causes on pickfit's
side, besides checks that showed nothing (fixed in the agent's guide, pickfit/verify/features.py, not guarded):

- The judge got only the last 1,500 characters of each check's output; 16 of the 53 had printed more than 3,000, so a
  result printed first was cut off. Now an output of up to 3,000 characters goes whole, and a longer one keeps its
  first 1,200 and its last 1,800.
- Terminal colour codes were removed without a word, so a feature that colours its output (`dog --color=always`,
  delta's syntax highlighting) could never be shown working. Now the judge is told how many colour or style codes
  the output carried before they were removed.

Nothing is judged again by applying it: it changes new runs. The feature judge cost about US$0.005 a run on the ledger
(549 calls, US$2.91), and the longer input adds about a third at most. `pickfit verify --rejudge-features` only lowers
checked features; recovering the 492 not_shown ones from saved evidence needs a mode that also restores a feature the
judge now confirms (rebuilding its smoke-test indexes from report.json and replay.json), about US$1.5-2 for the 273
records whose evidence is on the machine that ran them. Not written yet.

## 11/21: limits checks for harness-installed packages and the services box (limits-sysdeps-services.patch)

On feat/priv-packages-services (or wherever pickfit/verify/sysdeps.py and the eight-kind pickfit/verify/services.py
are merged), from the repository root:

```sh
git apply loop/proposals/limits-sysdeps-services.patch
uv run pytest -q tests/test_verify_limits_packages.py tests/test_verify_gui.py tests/test_verify_modal.py
```

pickfit/verify/limits.py (guarded), one new test file and twelve lines of tests/test_verify_gui.py (its display box
has a root channel, so the limits test now installs a package in it). What the limits test gains:

- `package_held`, on a Linux box whose root pickfit can use (Modal, EC2; not DockerBox): pickfit's root is asked for
  a .deb, a URL, an option, sudo and an unknown name and installs none of them, then installs `jq`; the box user
  runs it, finds none of its files, dpkg's status, apt's sources or policy-rc.d writable, and fails to remove it,
  to add a package source, and to run dpkg or apt-get itself.
- `package_needs_network`: with the network off, pickfit's root installs nothing.
- `services_loopback`, on a services box: the box user starts all eight kinds; each port answers on 127.0.0.1 (the
  control) and on no other address the box has; `pickfit-services check llm-stub` round-trips a chat completion.
- `services_offline`: with the network off every service still answers and the model endpoint still round-trips
  (nothing is fetched at run time).

A plain box without a root channel runs exactly the probes it ran before (23 on the fake box of
tests/test_verify_modal.py). Checked on 11/21 in a copy outside every checkout: the patch applies with `patch -p1`
and `git apply --check`, and the limits tests of every lane pass with it (modal, gui, ec2, tart, windows, mac
host). Not run against a real box: the new probes are the first time MariaDB, moto, llama.cpp's server, the mail
sink and the git host start in a box, so a first `--limits-test --services` that fails `services_loopback` points
at a service to fix, not at the isolation.

Once limits.py reads them, pickfit/verify/sysdeps.py and pickfit/verify/services.py decide what a limits test
checks: consider adding both to scripts/loop_guard.py PROTECTED in the same review.

## 11/21: the full-privilege VM box's limits test (limits-root-vm-hook.patch)

On feat/priv-root-vm-box (docs/proposals/privileges.md P6), from the repository root:

```sh
git apply loop/proposals/limits-root-vm-hook.patch
uv run pytest -q tests/test_verify_limits_root.py tests/test_verify_root_box.py tests/test_verify_ec2_root.py
```

pickfit/verify/limits.py and scripts/loop_guard.py (both guarded), 14 added lines, nothing removed:

- `limits.run_limits_test` and `limits.limits_test` hand a box whose `capabilities.full_privilege` is true to
  pickfit/verify/limits_root.py. In that box the box user has root, so limits.py's own probes (uid 1000 with no
  capabilities, no user namespaces, the metadata route) cannot hold and would read as a broken box; limits_root
  checks what holds the machine from outside it. Any other box runs limits.py's probes exactly as before.
- `pickfit/verify/limits_root.py` joins PROTECTED: once the full-privilege lane takes real records, its probes
  decide whether that lane may run, as limits.py's do for the others.

Until it is applied nothing is unguarded in practice: `pickfit verify --runner ec2 --runtime rootvm --limits-test`
calls limits_root itself (pickfit/verify/cli.py), and no record is routed to the lane. Apply it before the lane is
wired into pickfit.watch.

Checked on 11/21 against a copy of limits.py outside every checkout with the patch applied, loaded under another
module name and driven with the fake boxes of tests/test_verify_limits_root.py: `run_limits_test` on a
full-privilege box runs limits_root's 25 probes (24 hold; peer_unreachable fails by design there, since that entry
point starts no second box), `limits_test` starts the two boxes and all 27 hold, and a plain box still starts with
limits.py's `non_root`. `limits_test` makes one box to read its capabilities and never starts it; an unstarted
Ec2RootBox holds no slot and no AWS resource. `git apply --check` passes on feat/priv-root-vm-box at 79e6ca48.
No real instance was started: the first real run of the limits test is a human's (the report of 11/21 has the
commands).

Not applied on feat/privileges-aws-integration (11/21), where the other three patches of that day are: as first
written it collides with both of them (the same paragraph of limits.py's docstring as limits-sysdeps-services.patch,
the same lines of PROTECTED as privileges-guard-policy.patch), and the session that integrated the branches ran
under the loop guard, which refused the command that would have resolved it. The patch file was rebased onto that
branch instead, with no change in what it adds (the same 14 lines in the same places: the docstring paragraph now
follows the packages and services one, and limits_root.py's line in PROTECTED still follows limits.py's).
`git apply --check loop/proposals/limits-root-vm-hook.patch` passes there, so the command above applies it as it is;
on a tree without the other two patches, take the patch from feat/priv-root-vm-box.

## 11/21: grants and fidelity in the record (privileges-schema.patch)

On feat/priv-records-request (docs/proposals/privileges.md P1; the harness side is pickfit/verify/grants.py), from the
repository root:

```sh
git apply loop/proposals/privileges-schema.patch
uv run python scripts/export_schema.py --check
uv run pytest -q
```

pickfit/schema.py, schema/software.v1.json (scripts/export_schema.py's output) and a new tests/test_grants_schema.py:

- VerificationRun gets `grants` (at most 20, each listed once): what the run's boxes were given beyond the plain box.
  A Grant has `kind` (system_package, service, model_endpoint, root, container_engine, test_identity, virtual_device,
  extra_machine), `name` (one plain name), `tier` (1-5 on the proposal's ladder), `requested_by` (agent or plan) and
  `shown_in_guide`.
- FeatureCheck gets an optional `fidelity`: real, compatible or stand_in. A feature not checked has none.

Both are left out of the JSON when empty, so no record changes, nothing is migrated and no score moves (neither
pickfit/score.py nor pickfit/coverage.py reads them). A record from before loads with no grants and no fidelity, and is
written back as it was.

Until it is applied, pickfit/verify/result.py writes neither field (it looks for them, as pickfit/profiles.py does for
Capability.area). Nothing is lost meanwhile: each run's grants.json, beside its report, holds its grants in full, the
fidelity of each feature, every request and its answer, and the install guide's lines are made from that file. Runs
verified before the patch do not get the two fields afterwards: a record takes them from its next run.

Checked on 11/21 in a copy of the branch outside every checkout, applied with `patch -p1` (and `git apply --check` on
the branch): every hunk lands at its stated line, `export_schema.py --check` passes, pytest 2569 passed and 7 skipped
(2565 and 7 before the patch; the four added tests are the new file's).

Not in this patch: the page and the MCP answer do not read `fidelity` yet (pickfit/index.py's feature coverage, the
Worker). Until they do, a feature checked against a stand-in still shows as checked there, as it does today for a check
against the HTTP mock. That belongs with the coverage proposal's page work.

### privileges-guard-policy.patch (for 念誠 to decide)

```sh
git apply loop/proposals/privileges-guard-policy.patch
uv run pytest -q tests/test_loop_guard.py
```

One line in scripts/loop_guard.py: pickfit/verify/grants_policy.json joins PROTECTED. The table decides what a box may
be given on the agent's request and how much a record may spend, so a loop session that could edit it could widen its
own grants. Without the patch the table is an ordinary file. PICKFIT_GRANTS_POLICY names another table for one process
(a trial with the table switched on); a loop's environment is set by scripts/loop.sh, which is guarded already.
