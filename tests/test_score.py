"""Scores (B.3): components, caps, popularity, the rubric call, and keeping other fields; no network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import openai
import pytest
from queue_fakes import ROOT
from test_profiles import MODEL, README, add, extraction

import pickfit.env
from pickfit import meta
from pickfit.d1 import SqliteD1, sql
from pickfit.discover.store import PipelineDB
from pickfit.extract import build_sources, sources_sha
from pickfit.ledger import TAIPEI, Caps, Ledger
from pickfit.profiles import write_profiles
from pickfit.schema import (
    DocsRubric,
    DocsRubricItems,
    Outcomes,
    Pitfall,
    SoftwareRecord,
    Verification,
    VerificationRun,
)
from pickfit.score import (
    FORMULA_VERSION,
    Graded,
    compose_quality,
    fetch_outcomes,
    grade_docs,
    hygiene_parts,
    install_actions,
    maintenance_score,
    popularity,
    readme_fix,
    readme_fixes,
    refresh_scores,
    responsiveness_score,
    sandbox_score,
    score_records,
    treasure,
    usage_outcomes_weight,
    usage_score,
    weights,
)
from pickfit.verify.result import write_back

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=TAIPEI)
LATER = datetime(2026, 10, 31, 9, 0, tzinfo=TAIPEI)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


def run(run_id: str = "verify-1", *, level: str = "function", steps: int = 1, pitfalls: int = 0,
        checked_at: str = "2026-10-30T10:00:00+08:00") -> dict[str, Any]:
    data = {"id": run_id, "level": level, "os": "linux", "arch": "x86_64", "method": "sandbox",
            "checked_at": checked_at, "replayed": True,
            "steps": [{"command": f"step {i}", "purpose": None} for i in range(steps)],
            "smoke_tests": [{"command": "tinyq --help", "expected_signal": "Usage", "exit_code": 0,
                             "passed": True}],
            "pitfalls": [{"readme_said": "a", "actually_needed": "b"}] * pitfalls,
            "evidence": {"trace_path": f"runs/verify/{run_id}/report.json"}}
    if level == "failed":
        data.update(method="human", replayed=False, steps=[], blocking_error="no wheel")  # failed: a person's run
    return data


def verification(*runs: dict[str, Any]) -> Verification:
    parsed = [VerificationRun.model_validate(r) for r in runs]
    from pickfit.schema import best_level

    level = best_level(parsed)
    return Verification(level=level, unverified_reason="not_run" if level == "unverified" else None,
                        checked_at=max((r.checked_at for r in parsed), default=None), runs=parsed)


def items(score: int = 2, quote: str | None = "tiny jq-like query tool") -> dict[str, Any]:
    return {name: {"score": score, "quote": quote if score else None} for name in DocsRubricItems.model_fields}


def fake_grade(points: int = 2, calls: list[str] | None = None):
    def grade(sources: list[Any], *, model: str, run_id: str, scope: str, now: datetime, **_: Any) -> Graded:
        if calls is not None:
            calls.append(scope)
        rubric = DocsRubric(model=model, checked_at=now, sources_sha=sources_sha(sources),
                            items=DocsRubricItems.model_validate(items(points)))
        return Graded(rubric, cost_usd=0.015)
    return grade


# --- components ---------------------------------------------------------------------------------


def test_sandbox_component_follows_depth_steps_readme_fixes_and_failure() -> None:
    assert sandbox_score(verification(run(steps=3)), "dev_cli") == 1.0
    assert sandbox_score(verification(run(steps=5)), "dev_cli") == 0.85
    assert sandbox_score(verification(run(steps=7)), "dev_cli") == 0.7
    assert sandbox_score(verification(run(steps=2, pitfalls=1)), "dev_cli") == 0.85
    assert sandbox_score(verification(run(steps=2, pitfalls=2)), "dev_cli") == 0.7225
    assert sandbox_score(verification(run(level="install")), "dev_cli") == 0.6  # no README example ran
    assert sandbox_score(verification(run()), "local_ai") == 0.8  # a one-shot CLI run, no model served
    assert sandbox_score(verification(run(level="service")), "local_ai") == 0.9
    assert sandbox_score(verification(run(level="inference")), "local_ai") == 1.0
    assert sandbox_score(verification(run(level="failed")), "dev_cli") == 0.0
    assert sandbox_score(verification(), "dev_cli") is None


def test_install_actions_count_inside_chained_steps_but_not_looking_around() -> None:
    assert install_actions(["curl -fsSL https://x.dev/install.sh -o /tmp/i.sh && wc -c /tmp/i.sh && head -n 100 /tmp/i.sh",
                            "sh /tmp/i.sh"]) == 2
    assert install_actions(["mkdir -p ~/.local/bin && curl -fsSLO https://x/r.tgz && tar -xzf r.tgz && "
                            "install -m 0755 r ~/.local/bin/r && r --version"]) == 4
    assert install_actions(['TAG=$(curl -fsSL https://api.github.com/x | grep tag_name | cut -d\\" -f4) && '
                            "echo $TAG | tee /tmp/t && curl -fsSL -o /tmp/x.tgz https://x/$TAG.tgz"]) == 1
    # a checksum check by assignment only looks: 5 actions, not 7
    assert install_actions(["mkdir -p ~/.local/bin && curl -fsSL -o /tmp/z.tgz https://x/z.tgz",
                            "curl -fsSL -o /tmp/z.sha256 https://x/z.sha256 && E=$(cut -d' ' -f1 /tmp/z.sha256) && "
                            'A=$(sha256sum /tmp/z.tgz | cut -d\' \' -f1) && [ "$E" = "$A" ] && tar -xzf /tmp/z.tgz && '
                            "cp z ~/.local/bin/"]) == 5
    # heredoc lines are file content; writing a config file outside /tmp is one action
    assert install_actions(["mkdir -p ~/.config/t && cat > ~/.config/t/c.toml <<EOF\nmodel = \"tiny\"\nport = 1\nEOF"]) == 2
    assert install_actions(["curl -fsSL https://x.dev/i.sh > /tmp/i.sh && sh /tmp/i.sh",
                            "echo 'export PATH=x' >> ~/.bashrc", "cat > /tmp/input.json <<'EOF'\n{}\nEOF"]) == 3
    assert install_actions(["cd /tmp && rm -f old && npm view tool && npm install -g tool 2>&1; which tool"]) == 1
    assert install_actions(["curl -fsSL https://x.dev/install | sh", "export PATH=\"$HOME/.x/bin:$PATH\""]) == 2
    assert install_actions(["git clone https://github.com/a/b && cd b && npm install && npm run build && "
                            "npm install -g ."]) == 4
    assert install_actions(["echo 'a && b; c' && go version"]) == 0  # separators inside quotes stay put


@pytest.mark.parametrize(("said", "needed", "fix"), [
    ("tool --version", "use `tool version`; --version exits 2", False),  # pickfit's own check
    ("pip install tool", "uv tool install tool (PEP 668 externally-managed system)", False),
    ("go install github.com/a/tool@latest", "downloaded the release binary (no Go toolchain in the box)", False),
    ("sudo install -m 0755 tool /usr/local/bin", "install to ~/.local/bin", False),
    ("curl -fsSL https://x.dev/install.sh | sh", "download it first, read it, then run sh /tmp/install.sh", False),
    ("tool serve", "needs --backend cpu on a box with no NVIDIA driver", False),
    ("Visual C++ redistributable", "no redistributable needed on Linux", False),
    ("curl -fsSL https://x.dev/install.sh | sh", "run it with --skip-worker; the default run fails at worker install",
     True),
    ("run tool directly after install", "binary lands in ~/.tool/bin, which is not on PATH", True),
    ("tool link", "tool pair", True),
    ("bun add -g tool then tool --version works", "symlink ~/.bun/bin/tool into ~/.local/bin", True),
    # the README was right, the tool did it by itself, or only a note
    ("tool doctor", "tool doctor exits 1 when optional keys/services are missing; not an install failure", False),
    ("tool doctor checks the setup", "exits 1 when unconfigured — correct validator behavior for a fresh install",
     False),
    ("pipx install tool / pin tag v0.2.1", "uv tool install resolved tool==0.3.0, newer than the v0.2.1 tag", False),
    ("npm install -g tool installs tool", "first tool invocation downloads the prebuilt binary", False),
    ("npm install && npm run build", "npm install worked despite the pnpm pin; then npm run build", False),
])
def test_readme_fix_leaves_out_what_the_box_explains(said: str, needed: str, fix: bool) -> None:
    assert readme_fix(Pitfall(readme_said=said, actually_needed=needed)) is fix


def test_maintenance_counts_push_release_and_cadence_not_commits() -> None:
    as_of = datetime(2026, 10, 28, 12, 0, tzinfo=TAIPEI)
    repo = {"pushed_at": "2026-10-20T00:00:00Z", "created_at": "2025-01-01T00:00:00Z"}
    two = [{"published_at": "2026-10-01T00:00:00Z"}, {"published_at": "2026-06-01T00:00:00Z"}]
    assert maintenance_score({"repo": repo, "releases": two}, as_of) == 1.0
    assert maintenance_score({"repo": repo, "releases": two[:1]}, as_of) == 0.7  # one release, old repo
    young = {**repo, "created_at": "2026-08-01T00:00:00Z"}
    assert maintenance_score({"repo": young, "releases": two[:1]}, as_of) == 1.0
    assert maintenance_score({"repo": repo, "releases": []}, as_of) == 0.35
    stale = {**repo, "pushed_at": "2025-08-01T00:00:00Z"}
    assert maintenance_score({"repo": stale, "releases": []}, as_of) == 0.0
    assert maintenance_score({"repo": {"pushed_at": None}}, as_of) is None


def test_hygiene_parts_ignore_vendored_files() -> None:
    files = [".github/workflows/ci.yml", "tests/test_cli.py", "CHANGELOG.md", "uv.lock", "src/app.py"]
    assert hygiene_parts(files, [], True) == {"ci": True, "tests": True, "osi_license": True,
                                              "changelog": True, "lockfile": True}
    vendored = ["node_modules/x/CHANGELOG.md", "vendor/y/go.sum", "src/main.go", "pkg/run_test.go"]
    assert hygiene_parts(vendored, [{"body": "Fixed the --json flag on Windows."}], None) == {
        "ci": False, "tests": True, "osi_license": False, "changelog": True, "lockfile": False}


# Texts that the untagged rules read the other way, so each kind is seen deciding on its own.
LOOKS_LIKE_A_FIX = ("tool link", "tool pair")
LOOKS_LIKE_THE_BOX = ("sudo install tool", "install to ~/.local/bin (no sudo in the box)")


@pytest.mark.parametrize(("kind", "fix"), [("readme_wrong", True), ("sandbox", False), ("tool_handled", False),
                                           ("note", False)])
def test_a_tagged_pitfall_counts_as_a_readme_fix_only_when_readme_wrong(kind: str, fix: bool) -> None:
    for said, needed in (LOOKS_LIKE_A_FIX, LOOKS_LIKE_THE_BOX):
        assert readme_fix(Pitfall(readme_said=said, actually_needed=needed, kind=kind)) is fix
    assert readme_fix(Pitfall(readme_said=LOOKS_LIKE_A_FIX[0], actually_needed=LOOKS_LIKE_A_FIX[1]))  # untagged
    assert not readme_fix(Pitfall(readme_said=LOOKS_LIKE_THE_BOX[0], actually_needed=LOOKS_LIKE_THE_BOX[1]))


def test_kinds_and_untagged_pitfalls_mix_in_one_run() -> None:
    blocked = Pitfall(readme_said="tool generate path/to/repo", actually_needed="needs a model server", kind="sandbox")
    follows = Pitfall(readme_said="tool serve [path]", actually_needed='exits 1: Run "tool generate" first.')
    tagged_follows = Pitfall(readme_said="tool serve [path]", actually_needed='exits 1: Run "tool generate" first.',
                             kind="readme_wrong")
    note = Pitfall(readme_said="curl https://x.dev/i.sh | sh", actually_needed="the script was run without being read",
                   kind="note")
    assert readme_fixes([blocked, follows, note]) == 0  # a sandbox-tagged step blocks an untagged follower too
    assert readme_fixes([blocked, tagged_follows, note]) == 1  # a tagged follower keeps its kind
    notes = verification({**run(), "pitfalls": [{"readme_said": "a", "actually_needed": "b", "kind": "note"}] * 3})
    assert sandbox_score(notes, "dev_cli") == 1.0  # recording notes costs nothing
    wrong = verification({**run(), "pitfalls": [{"readme_said": "a", "actually_needed": "b", "kind": "readme_wrong"}]})
    assert sandbox_score(wrong, "dev_cli") == 0.85


def test_a_pitfall_that_follows_from_a_box_blocked_step_is_not_a_readme_fix() -> None:
    blocked = Pitfall(readme_said="tool generate path/to/repo",
                      actually_needed="`tool generate /tmp/r` exits 1: Cannot reach Ollama at localhost:11434")
    follows = Pitfall(readme_said="tool serve [path]",
                      actually_needed='`tool serve /tmp/r` exits 1: No wiki found. Run "tool generate" first.')
    other = Pitfall(readme_said="tool link", actually_needed="tool pair")
    assert readme_fix(follows) and readme_fixes([blocked, follows]) == 0
    assert readme_fixes([blocked, follows, other]) == 1


def issue(assoc: str = "NONE", *, closed_days: float | None = None, pr: bool = False, merged: bool = False,
          bot: bool = False, opened: str = "2026-10-01") -> dict[str, Any]:
    item: dict[str, Any] = {"author_association": assoc, "created_at": f"{opened}T00:00:00Z",
                            "closed_at": None, "user": {"login": "dependabot[bot]" if bot else "u", "type": "User"}}
    if closed_days is not None:
        day = datetime.fromisoformat(f"{opened}T00:00:00+00:00").day
        item["closed_at"] = f"{opened[:8]}{day + int(closed_days):02d}T00:00:00Z"
    if pr:
        item["pull_request"] = {"merged_at": "2026-10-03T00:00:00Z" if merged else None}
    return item


def test_responsiveness_counts_only_outside_issues_as_they_stood_at_the_snapshot() -> None:
    as_of = datetime(2026, 10, 28, 12, 0, tzinfo=TAIPEI)
    assert responsiveness_score(None, as_of) is None
    insiders = [issue("OWNER", closed_days=1), issue("MEMBER"), issue(bot=True), issue()]
    assert responsiveness_score(insiders, as_of) is None  # one outside issue is too few
    two = [issue(closed_days=2), issue()]
    assert responsiveness_score(two, as_of) == pytest.approx(0.5 * 0.5 + 0.5 * 1.0)
    prs = [issue(pr=True, merged=True), issue(pr=True, merged=True), issue(pr=True)]
    assert responsiveness_score(two + prs, as_of) == responsiveness_score(two, as_of)  # PRs are left out
    later = [issue(opened="2026-10-29"), issue(opened="2026-10-25"), issue(opened="2026-10-02", closed_days=27)]
    # opened after as_of, still open but under 7 days old, closed after as_of: only the last counts, as open
    assert responsiveness_score(two + later, as_of) == pytest.approx(0.5 * 1 / 3 + 0.5 * 1.0, abs=1e-4)


def test_usage_outcomes_need_three_external_reports_and_take_weight_from_four_components() -> None:
    outcomes = Outcomes.model_validate({"external": {"installed": 1, "install_failed": 1}})
    assert usage_score(outcomes) is None
    outcomes = Outcomes.model_validate({"external": {"installed": 3, "install_failed": 1, "still_using": 2,
                                                     "abandoned": 2}, "eval": {"installed": 50}})
    assert usage_score(outcomes) == pytest.approx((0.4 * 0.75 + 0.3 * 0.5) / 0.7, abs=1e-4)
    w = weights(20)
    assert sum(w.values()) == pytest.approx(100) and w["sandbox_verification"] == 40
    assert w["install_docs"] == pytest.approx(25 * (1 - 10 / 50), abs=1e-3)


ISSUED = datetime.fromisoformat("2026-10-30T12:00:00+00:00")


def _outcome_db(tmp_path: Path, rows: list[tuple[Any, ...]]) -> SqliteD1:
    """report_outcome rows as the Worker writes them: rec_id kept only when the report counted."""
    db = SqliteD1(tmp_path / "d1.sqlite", ROOT / "worker" / "migrations")
    for i, (rec, day, stage, success, reporter, *rest) in enumerate(rows):
        ts = (ISSUED + timedelta(days=day)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        db.execute(sql("INSERT INTO events (id, ts, type, rec_id, slug, stage, success, reporter, replaced_by, last_used) "
                       "VALUES (?1, ?2, 'outcome', ?3, 'tool-a', ?4, ?5, ?6, ?7, ?8)",
                       f"evt_{i}", ts, rec, stage, success, reporter, *(rest + [None, None])[:2]))
    return db


def test_usage_outcomes_count_still_using_check_ins_months_later(tmp_path: Path) -> None:
    rec = lambda c: "rec_" + c * 32  # noqa: E731
    db = _outcome_db(tmp_path, [
        (rec("1"), 1, "installed", 1, "external"),
        (rec("1"), 100, "still_using", 1, "external", None, "this_month"),  # day 100: inside 120
        (rec("2"), 2, "installed", 0, "external"),
        (rec("2"), 3, "installed", 1, "external"),  # failed, then fixed: installed
        (rec("2"), 20, "still_using", 1, "external", None, "this_week"),
        (rec("2"), 90, "still_using", 0, "external", None, "older"),  # the latest wins: abandoned
        (rec("3"), 60, "still_using", 0, "external", "other-tool"),
        (None, 130, "still_using", 1, "external"),  # past 120 days: stored, not counted
        (rec("4"), 50, "still_using", 1, "eval"),
    ])
    now = ISSUED + timedelta(days=131)
    outcomes = fetch_outcomes(db, now)["tool-a"]
    assert outcomes.external.model_dump() == {"installed": 2, "install_failed": 0, "first_run_ok": 0,
                                              "first_run_failed": 0, "still_using": 1, "replaced": 1, "abandoned": 1}
    assert outcomes.eval.still_using == 1 and outcomes.replaced_by == {"other-tool": 1}
    assert outcomes.last_report_at == ISSUED + timedelta(days=100) and outcomes.synced_at == now
    # Install 2/2, retention 1/3; no first-run reports, so that stage drops out.
    assert usage_score(outcomes) == pytest.approx((0.4 * 1 + 0.3 * 1 / 3) / 0.7, abs=1e-4)
    assert usage_outcomes_weight(outcomes.external.total()) == 10


def test_retention_alone_has_no_weight_until_three_external_reports(tmp_path: Path) -> None:
    rows = [("rec_" + c * 32, 30 + i, "still_using", 1, "external") for i, c in enumerate("ab")]
    rows += [("rec_" + c * 32, 40, "still_using", 1, "demo") for c in "cdef"]
    two = fetch_outcomes(_outcome_db(tmp_path, rows), ISSUED + timedelta(days=60))["tool-a"]
    assert two.external.total() == 2 and usage_score(two) is None
    quality = compose_quality({"sandbox_verification": 1.0, "usage_outcomes": usage_score(two)},
                              usage_outcomes_weight(two.external.total()), None)
    assert quality["components"]["usage_outcomes"]["score"] is None and quality["total"] == 100
    (tmp_path / "d1.sqlite").unlink()
    three = fetch_outcomes(_outcome_db(tmp_path, [*rows, ("rec_" + "9" * 32, 110, "still_using", 1, "external")]),
                           ISSUED + timedelta(days=120))["tool-a"]
    assert three.external.still_using == 3 and usage_score(three) == 1.0


def test_missing_components_leave_the_denominator_and_caps_bind() -> None:
    components = {"sandbox_verification": 1.0, "install_docs": 0.5, "maintenance": None,
                  "engineering_hygiene": None, "responsiveness": None, "usage_outcomes": None}
    q = compose_quality(components, 10, None)
    assert q["total"] == pytest.approx(100 * (40 + 12.5) / 65, abs=0.05) and q["confidence"] == 0.65
    assert compose_quality(components, 10, "unverified")["total"] == 69.0
    assert compose_quality(dict.fromkeys(components), 10, None)["total"] is None


def test_popularity_is_log_normalized_to_the_category_p95_with_velocity_after_90_days() -> None:
    signals = {"stars": 191, "forks": None, "release_downloads": None, "monthly_downloads": None,
               "dependents": 5_000, "hn_top_score": None, "registries_count": None}
    assert popularity(signals, "dev_cli", age_days=30) == 100.0  # dependents has no ref and is ignored
    assert popularity(signals, "local_ai", age_days=30) < 100.0
    median = {**signals, "stars": 17, "forks": 2}  # about the candidates' median
    young, old = popularity(median, "dev_cli", 60), popularity(median, "dev_cli", 720)
    assert 45 < young < 60 and old < young  # 17 stars over two years is slow growth
    unknown = {**median, "stars": 3, "forks": 0, "registries_count": 0, "hn_top_score": 0}
    assert popularity(unknown, "dev_cli", 60) < 30
    hn = {**unknown, "hn_top_score": 2}
    assert popularity(hn, "dev_cli", 60) - popularity(unknown, "dev_cli", 60) < 10  # a post with 2 points
    assert popularity(dict.fromkeys(signals), "dev_cli", 10) is None


# --- records ------------------------------------------------------------------------------------


def setup_records(tmp_path: Path, *, verified: bool = True) -> tuple[Path, Path]:
    db = PipelineDB(tmp_path / "pipeline.db")
    add(db, 7, "someone/tinyq", extraction())
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    if verified:
        path = out / "tinyq.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["verification"] = verification(run(steps=2)).model_dump(mode="json")
        record["install"]["linux"] = {"basis": "replayed", "run_id": "verify-1", "method": "other",
                                      "steps": [{"command": "step 0"}, {"command": "step 1"}]}
        record["evidence"].append({"field": "/verification", "source_id": "github_api", "quote": None,
                                   "method": "sandbox", "checked_at": "2026-10-30T10:00:00+08:00"})
        # as profiles and write-back write a record: normalized, indented
        path.write_text(json.dumps(SoftwareRecord.model_validate(record).model_dump(mode="json"), ensure_ascii=False,
                                   indent=2) + "\n")
    return tmp_path / "pipeline.db", out


def test_scoring_writes_only_scores_and_reuses_the_rubric(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    before = json.loads((out / "tinyq.json").read_text(encoding="utf-8"))
    calls: list[str] = []
    summary = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                            grade=fake_grade(calls=calls))
    assert summary.written == ["tinyq"] and calls == ["score:tinyq"] and not summary.errors
    after = json.loads((out / "tinyq.json").read_text(encoding="utf-8"))
    assert {k for k in after if after[k] != before.get(k)} == {"scores", "updated_at"}
    record = SoftwareRecord.model_validate(after)
    scores = record.scores
    assert scores.formula_version == FORMULA_VERSION and scores.docs_rubric.model == MODEL
    comps = scores.quality.components
    assert comps.sandbox_verification.score == 1.0 and comps.install_docs.score == 1.0
    assert comps.responsiveness.score is None and comps.usage_outcomes.score is None
    assert scores.quality.cap_reason is None and scores.popularity.signals.stars == 42
    assert scores.popularity.signals.registries_count is None and scores.popularity.packages == []
    assert scores.treasure.value > 0
    assert scores.treasure.is_treasure is (scores.quality.total >= 70 and scores.popularity.score <= 45)
    again = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                          grade=fake_grade(calls=calls))
    assert again.unchanged == ["tinyq"] and again.reused == 1 and calls == ["score:tinyq"]


def test_feature_coverage_rides_along_and_leaves_the_formula_alone(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    plain = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                          grade=fake_grade())
    assert plain.rows[0]["features"] is None
    path = out / "tinyq.json"
    record = json.loads(path.read_text())
    before = record["scores"]
    smoke = record["verification"]["runs"][0]["smoke_tests"]
    smoke.append({"command": "tinyq .a sample.jsonl", "expected_signal": "1", "exit_code": 0, "passed": True})
    record["verification"]["runs"][0]["features"] = [
        {"feature": "query JSON Lines", "status": "checked", "smoke_tests": [1]},
        {"feature": "stream from stdin", "status": "not_checked", "reason": "not_attempted"}]
    path.write_text(json.dumps(record))
    covered = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                            grade=fake_grade())
    assert covered.unchanged == ["tinyq"] and covered.rows[0]["features"] == {"checked": 1, "listed": 2}
    after = json.loads(path.read_text())
    assert after["scores"] == before and after["verification"]["runs"][0]["features"][0]["status"] == "checked"
    assert refresh_scores(after, LATER) is None  # write-back's refresh sees nothing to change either


def test_scores_of_an_older_formula_that_break_todays_rules_are_replaced_and_the_rubric_kept(
        tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade())
    path = out / "tinyq.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    q = data["scores"]["quality"]["total"]
    data["scores"]["formula_version"] = "older"
    data["scores"]["popularity"]["score"] = 10.0  # a treasure under a line below today's quality
    data["scores"]["treasure"] = {"is_treasure": True, "value": round(q * 0.9, 2)}
    data["scores"]["quality"]["total"] = q = 75.0
    data["scores"]["treasure"]["value"] = round(q * 0.9, 2)
    with pytest.raises(ValueError, match="is_treasure must be"):
        SoftwareRecord.model_validate(data)
    path.write_text(json.dumps(data))
    calls: list[str] = []
    summary = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False,
                            now=LATER, grade=fake_grade(calls=calls))
    assert summary.written == ["tinyq"] and not summary.errors and calls == []  # the rubric was reused
    scores = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8")).scores
    assert scores.formula_version == FORMULA_VERSION and scores.docs_rubric is not None


def test_a_rescore_without_lookups_keeps_the_stored_signals(tmp_path: Path) -> None:
    from pickfit.registries import RegistrySignals

    class Fixed:
        def lookup(self, *_: Any, **__: Any) -> RegistrySignals:
            return RegistrySignals(monthly_downloads=900, registries_count=1, hn_top_score=12, packages=["npm:tinyq"])

    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, now=NOW, grade=fake_grade(),
                  registries=Fixed())
    path = out / "tinyq.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    comps = {k: v["score"] for k, v in data["scores"]["quality"]["components"].items()}
    data["scores"]["quality"] = compose_quality({**comps, "responsiveness": 0.5}, 10, None)  # measured before
    data["scores"]["treasure"] = treasure(data["scores"]["quality"]["total"], data["scores"]["popularity"]["score"])
    path.write_text(json.dumps(data))
    before = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8")).scores
    again = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                          grade=fake_grade())
    after = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8")).scores
    assert again.unchanged == ["tinyq"] and after.quality == before.quality
    assert after.quality.components.responsiveness.score == 0.5
    assert after.popularity.signals == before.popularity.signals and after.popularity.packages == ["npm:tinyq"]


def test_unverified_records_are_capped_below_the_treasure_line(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path, verified=False)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade())
    scores = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text(encoding="utf-8")).scores
    assert scores.quality.cap_reason == "unverified" and scores.quality.total <= 69
    assert scores.quality.components.sandbox_verification.score is None
    assert not scores.treasure.is_treasure


def test_profiles_rewrite_keeps_scores(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade())
    scored = json.loads((out / "tinyq.json").read_text(encoding="utf-8"))
    again = write_profiles(PipelineDB(db_path), model=MODEL, out_dir=out, now=NOW)
    assert again.unchanged == ["tinyq"]
    assert json.loads((out / "tinyq.json").read_text(encoding="utf-8"))["scores"] == scored["scores"]


def test_write_back_keeps_scores_and_refreshes_what_follows_the_run(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path, verified=False)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade(1))
    before = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text(encoding="utf-8")).scores
    assert before.quality.cap_reason == "unverified"
    new_run = VerificationRun.model_validate(run("verify-2", steps=5, pitfalls=1))
    written, note = write_back(new_run, "tinyq", out)
    assert written and "scores refreshed" in note
    after = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text(encoding="utf-8"))
    assert after.verification.level == "function" and after.install.linux.run_id == "verify-2"
    s = after.scores
    assert s.quality.cap_reason is None
    assert s.quality.components.sandbox_verification.score == pytest.approx(0.85 * 0.85)
    assert s.docs_rubric == before.docs_rubric and s.popularity == before.popularity
    assert s.quality.components.install_docs == before.quality.components.install_docs


def test_refresh_moves_scores_of_a_refreshable_formula_and_score_refresh_writes_only_scores(tmp_path: Path) -> None:
    from pickfit.score import REFRESHABLE_FROM, refresh_records

    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade())
    path = out / "tinyq.json"
    data = json.loads(path.read_text())
    old = next(iter(REFRESHABLE_FROM))
    data["scores"]["formula_version"] = old
    data["verification"]["runs"][0]["pitfalls"] = [{"readme_said": "tool link", "actually_needed": "tool pair",
                                                    "kind": "note"},
                                                   {"readme_said": "a", "actually_needed": "b"}]  # written before kind
    path.write_text(json.dumps(data))
    before = SoftwareRecord.model_validate_json(path.read_text()).model_dump(mode="json")
    assert refresh_records(out, dry_run=True, now=LATER).written == ["tinyq"]
    assert json.loads(path.read_text()) == data  # a dry run writes nothing
    summary = refresh_records(out, now=LATER)
    assert summary.written == ["tinyq"] and "moved from formula" in summary.rows[0]["note"]
    after = json.loads(path.read_text())
    assert {k for k in after if after[k] != data.get(k)} == {"scores", "updated_at"}  # the file, key by key
    assert "kind" not in after["verification"]["runs"][0]["pitfalls"][1]  # no schema default added
    scores = SoftwareRecord.model_validate(after).scores
    assert scores.formula_version == FORMULA_VERSION and scores.docs_rubric == SoftwareRecord.model_validate(
        before).scores.docs_rubric  # other components kept as they were
    assert scores.quality.components.sandbox_verification.score == 0.85  # the note is not a fix; "a"/"b" is
    assert refresh_records(out, now=LATER).unchanged == ["tinyq"]
    after["scores"]["formula_version"] = "q0"  # not refreshable: left for a full rescore, never cleared
    path.write_text(json.dumps(after))
    summary = refresh_records(out, now=LATER)
    assert "tinyq" in summary.errors and json.loads(path.read_text())["scores"]["formula_version"] == "q0"


def test_refresh_clears_scores_of_another_formula() -> None:
    data = {"scores": {"formula_version": "q0"}}
    assert "rescore" in refresh_scores(data, NOW) and data["scores"] is None
    assert refresh_scores({"scores": None}, NOW) is None


# --- the paid call, with a mocked Meta API ----------------------------------------------------------


def reply(payload: dict[str, Any]) -> httpx2.Response:
    return httpx2.Response(200, json={
        "id": "resp_r", "object": "response", "created_at": 0, "model": MODEL, "status": "completed",
        "output": [{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(payload), "annotations": []}]}],
        "usage": {"input_tokens": 3000, "input_tokens_details": {"cached_tokens": 1000},
                  "output_tokens": 400, "output_tokens_details": {"reasoning_tokens": 200}, "total_tokens": 3400}})


def test_grade_docs_sends_a_strict_schema_and_zeroes_unquoted_items(tmp_path: Path) -> None:
    answer = items(2)
    answer["troubleshooting_uninstall"] = {"score": 2, "quote": "Run tinyq --doctor when it breaks"}
    answer["config_and_keys"] = {"score": 0, "quote": "stray"}
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return reply(answer)

    client = openai.OpenAI(api_key="sk-test-0123456789", base_url="https://api.meta.ai/v1", max_retries=0,
                           http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    ledger = Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    snapshot = {"full_name": "someone/tinyq", "readme": README, "readme_path": "README.md", "releases": [],
                "repo": {"full_name": "someone/tinyq", "html_url": "https://github.com/someone/tinyq",
                         "default_branch": "main"}}
    graded = grade_docs(build_sources(snapshot), model=MODEL, run_id="score-t", scope="score:tinyq",
                        now=NOW, client=client, ledger=ledger, runs_dir=tmp_path / "runs")
    body = sent[0]
    assert body["reasoning"]["effort"] == "low" and body["text"]["format"]["strict"] is True
    assert body["model"] == MODEL and "<source" in body["input"][0]["content"][0]["text"]
    rubric = graded.rubric
    assert rubric.unquoted == ["troubleshooting_uninstall"]
    assert rubric.items.troubleshooting_uninstall.score == 0 and rubric.items.config_and_keys.quote is None
    assert rubric.items.score() == pytest.approx(12 / 16) and graded.cost_usd > 0


def test_mcp_servers_have_their_own_popularity_refs() -> None:
    from pickfit.score import POPULARITY_REFS, VERIFICATION_DEPTH, popularity

    assert set(POPULARITY_REFS["mcp_server"]) == set(POPULARITY_REFS["dev_cli"])
    signals = {"stars": 40, "forks": 5, "monthly_downloads": 20000, "release_downloads": None, "dependents": None,
               "hn_top_score": 0, "registries_count": 1}
    # The same npm download count says less about an MCP server, which npx fetches on every client start.
    assert popularity(signals, "mcp_server", 60) < popularity(signals, "dev_cli", 60)
    assert VERIFICATION_DEPTH["mcp_server"]["function"] < VERIFICATION_DEPTH["mcp_server"]["service"] == 1.0


# --- hosted web apps: web.v1 -----------------------------------------------------------------

from pickfit.score import (  # noqa: E402
    WEB_FORMULA_VERSION,
    browser_facts_score,
    build_web_scores,
    hn_item_id,
    web_popularity,
    web_weights,
)

WEB_FIXTURE = ROOT / "worker" / "test" / "fixtures" / "software" / "fixture-web-sketch.json"


def web_record(**facts: Any) -> dict[str, Any]:
    """The fixture web app with its browser run's facts changed."""
    data = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    data["verification"]["runs"][0]["web"].update(facts)
    return data


def web_scores(data: dict[str, Any], *, stars: int | None = None, hn: int | None = 4) -> dict[str, Any]:
    return build_web_scores(SoftwareRecord.model_validate(data), stars=stars, hn=hn, now=NOW)


def test_web_quality_is_the_browser_run_and_its_facts_with_no_readme_or_repo_parts() -> None:
    scores = web_scores(web_record())
    q = scores["quality"]
    assert scores["formula_version"] == WEB_FORMULA_VERSION and scores["docs_rubric"] is None
    assert {k: c["weight"] for k, c in q["components"].items() if c["weight"]} == {
        "sandbox_verification": 50, "browser_facts": 40, "usage_outcomes": 10}
    assert (q["total"], q["confidence"], q["cap_reason"]) == (100.0, 0.9, None)
    # The record validates with these scores, and weights still sum to 100.
    data = web_record()
    data["scores"] = scores
    assert SoftwareRecord.model_validate(data).scores.quality.components.browser_facts.weight == 40


@pytest.mark.parametrize(("facts", "expected"), [
    ({}, 1.0),
    ({"ads_seen": True}, 0.8),
    ({"account_needed": True}, 0.7),
    ({"data_sent": "observed", "data_sent_note": None}, 0.7),
    # unknown drops out: 0.3 + 0.2 + 0.2 of 0.7
    ({"data_sent": "unknown"}, 1.0),
    ({"offline": "not_offline"}, 0.8),
    ({"ads_seen": None, "account_needed": None, "data_sent": "unknown", "offline": "not_tested", "pwa": False}, 0.0),
])
def test_browser_facts_score_what_the_run_saw_and_drop_what_it_could_not_tell(facts: dict[str, Any], expected: float) -> None:
    verification = SoftwareRecord.model_validate(web_record(**facts)).verification
    assert browser_facts_score(verification) == expected


def test_a_web_app_that_only_loaded_scores_lower_and_an_unverified_one_is_capped_with_no_total() -> None:
    data = web_record(operations=[], data_sent="unknown")
    run = data["verification"]["runs"][0]
    run.update(level="install", features=[])
    data["verification"]["level"] = "install"
    q = web_scores(data)["quality"]
    assert q["components"]["sandbox_verification"]["score"] == 0.6
    assert q["total"] == round(100 * (0.6 * 50 + 1.0 * 40) / 90, 1)  # 77.8: not a treasure
    run.update(level="unverified", unverified_reason="not_run", smoke_tests=[])
    run["web"].update(screen="sign_in_wall")
    data["verification"].update(level="unverified", unverified_reason="not_run")
    q = web_scores(data)["quality"]
    assert (q["total"], q["cap_reason"], q["cap"]) == (None, "unverified", 69)


def test_web_popularity_is_stars_with_a_repo_else_the_cited_show_hn_points() -> None:
    assert web_popularity({"stars": None, "hn_top_score": 4}) == 41.7
    assert web_popularity({"stars": 31, "hn_top_score": None}) == 49.8
    assert web_popularity({"stars": None, "hn_top_score": None}) is None
    # The selection bands (2..5 points, 3..31 stars) sit about 20..50: good and not famous can be a treasure.
    assert [web_popularity({"hn_top_score": p}) for p in (2, 5)] == [28.4, 46.4]
    assert [web_popularity({"stars": s}) for s in (3, 1048)] == [19.9, 100.0]
    no_repo = web_scores(web_record(), stars=500, hn=4)
    assert no_repo["popularity"]["signals"]["stars"] is None and no_repo["popularity"]["score"] == 41.7
    with_repo = web_record()
    with_repo.update(repo_id="gh:900000999", repo={"url": "https://example.invalid/fixture/sketch", "full_name": "fixture/sketch",
                                                    "created_at": "2026-05-01T00:00:00Z", "archived": False})
    scored = web_scores(with_repo, stars=31, hn=200)
    assert scored["popularity"]["signals"]["hn_top_score"] is None and scored["popularity"]["score"] == 49.8
    assert scored["treasure"]["is_treasure"] is False  # 49.8 > 45


def test_usage_weight_comes_out_of_browser_facts() -> None:
    assert {k: v for k, v in web_weights(20).items() if v} == {"sandbox_verification": 50, "browser_facts": 30, "usage_outcomes": 20}
    assert sum(web_weights(30).values()) == 100


def test_score_records_scores_a_web_app_from_its_hn_post_with_no_model_or_github_call(tmp_path: Path) -> None:
    out = tmp_path / "software"
    out.mkdir()
    (out / "fixture-web-sketch.json").write_text(WEB_FIXTURE.read_text(encoding="utf-8"))
    assert hn_item_id(SoftwareRecord.model_validate_json(WEB_FIXTURE.read_text(encoding="utf-8"))) == 1

    class HN:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get_json(self, url: str, params: Any = None) -> Any:
            self.urls.append(url)
            return {"id": 1, "score": 4, "type": "story"}

    hn = HN()
    summary = score_records(out, db_path=None, model=MODEL, use_github=False, now=NOW, registries=hn,
                            grade=lambda *a, **k: pytest.fail("no rubric for a web app"))
    assert summary.written == ["fixture-web-sketch"] and summary.cost_usd == 0
    assert hn.urls == ["https://hacker-news.firebaseio.com/v0/item/1.json"]
    scores = SoftwareRecord.model_validate_json((out / "fixture-web-sketch.json").read_text(encoding="utf-8")).scores
    assert (scores.formula_version, scores.quality.total, scores.popularity.score, scores.treasure.is_treasure) == (
        "web.v1", 100.0, 41.7, True)
    # Without lookups, the stored points stay; the same scores are not rewritten.
    again = score_records(out, db_path=None, model=MODEL, use_github=False, use_registries=False, now=LATER)
    assert again.unchanged == ["fixture-web-sketch"]
    # --kind picks records by kind.
    assert score_records(out, db_path=None, model=MODEL, kind="cli_tool", use_github=False, use_registries=False).rows == []
    assert len(score_records(out, db_path=None, model=MODEL, kind="web_app", use_github=False, use_registries=False).rows) == 1


def test_refresh_follows_the_web_run_and_clears_a_web_app_scored_by_another_formula() -> None:
    data = web_record()
    data["scores"] = web_scores(data)
    data["verification"]["runs"][0]["web"]["ads_seen"] = True
    assert refresh_scores(data, LATER) == "scores refreshed from the record"
    assert data["scores"]["quality"]["components"]["browser_facts"]["score"] == 0.8
    assert data["scores"]["popularity"]["score"] == 41.7  # kept: refresh makes no call
    assert refresh_scores(data, LATER) is None
    data["scores"]["formula_version"] = FORMULA_VERSION
    assert "rescore" in refresh_scores(data, LATER) and data["scores"] is None


# --- usability in quality: gui.v1 and web.v2 (off until the ease.v1 pilot passes) -----------------------

from pickfit import score as score_module  # noqa: E402
from pickfit.schema import Scores  # noqa: E402
from pickfit.score import GUI_WEIGHTS, WEB2_WEIGHTS, build_scores  # noqa: E402

CHAT_FIXTURE = ROOT / "worker" / "test" / "fixtures" / "software" / "fixture-chat-tui.json"


def ease(run_id: str, score: float = 85.0) -> dict[str, Any]:
    level = 2.0 if score >= 70 else 1.0
    return {"version": "ease.v1", "run_id": run_id, "basis": "operated", "score": score,
            "verdict": "easy" if score >= 70 else "some_friction" if score >= 40 else "hard",
            "dimensions": {k: {"score": level, "status": "scored"} for k in ("ready", "findable", "responsive", "comfortable")},
            "operations": 1, "screens": 4, "sandbox": "Xvfb 1280x800x24", "model": "muse-spark-1.3",
            "prompt_version": "ease.v1", "samples": 2, "inputs_sha": "0" * 64,
            "checked_at": "2026-11-02T23:00:00+08:00", "cost_usd": 0.05}


def desktop_record(score: float = 85.0) -> dict[str, Any]:
    data = json.loads(CHAT_FIXTURE.read_text(encoding="utf-8"))
    data["kind"] = "desktop_app"
    run_ = data["verification"]["runs"][0]
    run_["gui"] = {"tier": "ui_rendered", "screen": "main_ui", "command": "chat --gui", "display": "Xvfb 1280x800x24"}
    data["usability"] = ease(run_["id"], score)
    return data


def test_usability_stays_out_of_quality_until_the_pilot_passes() -> None:
    assert score_module.EASE_SCORED is False
    data = web_record()
    data["usability"] = ease(data["verification"]["runs"][0]["id"])
    scores = web_scores(data)
    assert scores["formula_version"] == WEB_FORMULA_VERSION and "usability" not in scores["quality"]["components"]
    desk = build_scores(SoftwareRecord.model_validate(desktop_record()), None, None, None, now=NOW)
    assert desk["formula_version"] == FORMULA_VERSION and "usability" not in desk["quality"]["components"]


def test_gui_v1_weighs_usability_and_a_treasure_needs_seventy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(score_module, "EASE_SCORED", True)
    assert sum(GUI_WEIGHTS.values()) == 100 and sum(WEB2_WEIGHTS.values()) == 100
    scores = build_scores(SoftwareRecord.model_validate(desktop_record()), None, None, None, now=NOW)
    assert scores["formula_version"] == "gui.v1"
    components = scores["quality"]["components"]
    assert {k: c["weight"] for k, c in components.items()} == GUI_WEIGHTS
    assert components["usability"]["score"] == 0.85 and components["sandbox_verification"]["score"] == 0.6
    assert scores["quality"]["total"] == round(100 * (0.6 * 25 + 0.85 * 30) / 55, 1)
    Scores.model_validate(scores)
    # A command-line tool keeps b3.v5 and no usability component.
    tool = json.loads(CHAT_FIXTURE.read_text(encoding="utf-8"))
    assert build_scores(SoftwareRecord.model_validate(tool), None, None, None, now=NOW)["formula_version"] == FORMULA_VERSION
    high = {"total": 90.0, "components": {"usability": {"score": 0.69, "weight": 30}}}
    assert treasure(high, 30.0, ease=True)["is_treasure"] is False
    assert treasure(high | {"components": {"usability": {"score": 0.7, "weight": 30}}}, 30.0, ease=True)["is_treasure"]
    assert treasure(high, 30.0)["is_treasure"]  # b3.v5 and web.v1 do not look at usability
    shown = scores | {"popularity": scores["popularity"] | {"score": 30.0},
                      "quality": scores["quality"] | {"total": 90.0, "components": components | {
                          "usability": {"score": 0.69, "weight": 30}}},
                      "treasure": {"is_treasure": True, "value": 63.0}}
    with pytest.raises(ValueError, match="usability >= 0.7"):
        Scores.model_validate(shown)


def test_refresh_moves_records_to_the_usability_formulas_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    data = desktop_record()
    data["scores"] = build_scores(SoftwareRecord.model_validate(data), None, None, None, now=NOW)
    web = web_record()
    web["usability"] = ease(web["verification"]["runs"][0]["id"], 60.0)
    web["scores"] = web_scores(web)
    monkeypatch.setattr(score_module, "EASE_SCORED", True)
    assert refresh_scores(data, LATER) == "scores moved from formula b3.v5 to gui.v1, refreshed from the record"
    assert data["scores"]["quality"]["components"]["usability"]["score"] == 0.85
    assert refresh_scores(web, LATER) == "scores moved from formula web.v1 to web.v2, refreshed from the record"
    components = web["scores"]["quality"]["components"]
    assert components["usability"] == {"score": 0.6, "weight": 35} and components["browser_facts"]["weight"] == 30
    assert web["scores"]["treasure"]["is_treasure"] is False
    for record in (data, web):
        SoftwareRecord.model_validate(record)
    # A re-verified record whose usability read a run it no longer has drops the component until judged again.
    data["usability"]["run_id"] = "verify-gone"
    assert refresh_scores(data, LATER) == "scores refreshed from the record"
    assert data["scores"]["quality"]["components"]["usability"]["score"] is None
    monkeypatch.setattr(score_module, "EASE_SCORED", False)
    assert refresh_scores(data, LATER) == "scores moved from formula gui.v1 to b3.v5, refreshed from the record"
    assert "usability" not in data["scores"]["quality"]["components"]
    assert refresh_scores(web, LATER) == "scores moved from formula web.v2 to web.v1, refreshed from the record"
    SoftwareRecord.model_validate(data)


# --- measurable visual defects in quality: gui.v2 and web.v3 ------------------------------------------------

from pickfit.score import GUI_VISUAL_WEIGHTS, WEB_VISUAL_WEIGHTS  # noqa: E402


def visual(run_id: str, score: int = 1) -> dict[str, Any]:
    defects = {2: [], 1: [("minor", "raw_markup")], 0: [("major", "overlap")]}[score]
    return {"version": "comfort.v1", "run_id": run_id, "score": score, "status": "scored",
            "defects": [{"item": "comfortable", "operation": None, "cause": "app", "problem": "x", "screenshot": "a.png",
                         "box": [0, 0, 10, 10], "quote": "x", "found_by": "ocr", "kind": kind, "severity": severity}
                        for severity, kind in defects],
            "screens": 2, "model": "muse-wonder-1.0", "effort": "medium", "inputs_sha": "0" * 64,
            "checked_at": "2026-11-03T20:00:00+08:00", "cost_usd": 0.03}


def test_a_visual_check_moves_desktop_and_web_apps_to_gui_v2_and_web_v3() -> None:
    assert sum(GUI_VISUAL_WEIGHTS.values()) == 100 and sum(WEB_VISUAL_WEIGHTS.values()) == 100
    desk = desktop_record()
    desk.pop("usability")
    desk["visual_check"] = visual(desk["verification"]["runs"][0]["id"], 1)
    scores = build_scores(SoftwareRecord.model_validate(desk), None, None, None, now=NOW)
    assert scores["formula_version"] == "gui.v2"
    assert scores["quality"]["components"]["visual_quality"] == {"score": 0.5, "weight": 15}
    assert scores["quality"]["total"] == round(100 * (0.6 * 35 + 0.5 * 15) / 50, 1)
    Scores.model_validate(scores)
    web = web_record()
    web["visual_check"] = visual(web["verification"]["runs"][0]["id"], 2)
    scores = web_scores(web)
    assert scores["formula_version"] == "web.v3" and scores["quality"]["components"]["visual_quality"]["score"] == 1.0
    assert scores["quality"]["components"]["browser_facts"]["weight"] == 30
    # A command-line tool, or an app without a check, keeps its formula.
    assert web_scores(web_record())["formula_version"] == WEB_FORMULA_VERSION
    plain = desktop_record()
    plain.pop("usability")
    assert build_scores(SoftwareRecord.model_validate(plain), None, None, None, now=NOW)["formula_version"] == FORMULA_VERSION


def test_refresh_moves_records_in_and_out_of_the_visual_formulas() -> None:
    desk = desktop_record()
    desk.pop("usability")
    desk["scores"] = build_scores(SoftwareRecord.model_validate(desk), None, None, None, now=NOW)
    web = web_record()
    web["scores"] = web_scores(web)
    desk["visual_check"] = visual(desk["verification"]["runs"][0]["id"], 0)
    web["visual_check"] = visual(web["verification"]["runs"][0]["id"], 1)
    assert refresh_scores(desk, LATER) == "scores moved from formula b3.v5 to gui.v2, refreshed from the record"
    assert desk["scores"]["quality"]["components"]["visual_quality"]["score"] == 0.0
    assert refresh_scores(web, LATER) == "scores moved from formula web.v1 to web.v3, refreshed from the record"
    for record in (desk, web):
        SoftwareRecord.model_validate(record)
        assert refresh_scores(record, LATER) is None
    # A re-verified record whose check read a run it no longer has goes back until it is checked again.
    desk["visual_check"]["run_id"] = "verify-gone"
    assert refresh_scores(desk, LATER) == "scores moved from formula gui.v2 to b3.v5, refreshed from the record"
    assert "visual_quality" not in desk["scores"]["quality"]["components"]


def test_a_visual_check_score_must_follow_its_defects() -> None:
    from pickfit.schema import VisualCheck

    VisualCheck.model_validate(visual("run-1", 0))
    for wrong in ({"score": 2}, {"score": None}, {"status": "sandbox_broken"}):
        with pytest.raises(ValueError):
            VisualCheck.model_validate(visual("run-1", 0) | wrong)
    with pytest.raises(ValueError, match="desktop_app and web_app only"):
        tool = json.loads(CHAT_FIXTURE.read_text(encoding="utf-8"))
        tool["visual_check"] = visual(tool["verification"]["runs"][0]["id"], 2)
        SoftwareRecord.model_validate(tool)
