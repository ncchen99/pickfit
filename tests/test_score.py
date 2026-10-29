"""Scores (B.3): components, caps, popularity, the rubric call, and keeping other fields; no network."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx2
import openai
import pytest
from test_profiles import MODEL, README, add, extraction

import pickfit.env
from pickfit import meta
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
    grade_docs,
    hygiene_parts,
    install_actions,
    maintenance_score,
    popularity,
    readme_fix,
    refresh_scores,
    responsiveness_score,
    sandbox_score,
    score_records,
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
        data.update(replayed=False, steps=[], blocking_error="no wheel")
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


def test_sandbox_component_follows_steps_pitfalls_and_failure() -> None:
    assert sandbox_score(verification(run(steps=3))) == 1.0
    assert sandbox_score(verification(run(steps=5))) == 0.85
    assert sandbox_score(verification(run(steps=7))) == 0.7
    assert sandbox_score(verification(run(steps=2, pitfalls=1))) == pytest.approx(0.8)
    assert sandbox_score(verification(run(level="failed"))) == 0.0
    assert sandbox_score(verification()) is None


def test_install_actions_count_inside_chained_steps_but_not_looking_around() -> None:
    assert install_actions(["curl -fsSL https://x.dev/install.sh -o /tmp/i.sh && wc -c /tmp/i.sh && head -n 100 /tmp/i.sh",
                            "sh /tmp/i.sh"]) == 2
    assert install_actions(["mkdir -p ~/.local/bin && curl -fsSLO https://x/r.tgz && tar -xzf r.tgz && "
                            "install -m 0755 r ~/.local/bin/r && r --version"]) == 4
    assert install_actions(['TAG=$(curl -fsSL https://api.github.com/x | grep tag_name | cut -d\\" -f4) && '
                            "echo $TAG | tee /tmp/t && curl -fsSL -o /tmp/x.tgz https://x/$TAG.tgz"]) == 2
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
    assert sum(w.values()) == pytest.approx(100) and w["sandbox_verification"] == 35
    assert w["install_docs"] == pytest.approx(20 * (1 - 10 / 55), abs=1e-3)


def test_missing_components_leave_the_denominator_and_caps_bind() -> None:
    components = {"sandbox_verification": 1.0, "install_docs": 0.5, "maintenance": None,
                  "engineering_hygiene": None, "responsiveness": None, "usage_outcomes": None}
    q = compose_quality(components, 10, None)
    assert q["total"] == pytest.approx(100 * (35 + 10) / 55, abs=0.05) and q["confidence"] == 0.55
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
        record = json.loads(path.read_text())
        record["verification"] = verification(run(steps=2)).model_dump(mode="json")
        record["install"]["linux"] = {"basis": "replayed", "run_id": "verify-1", "method": "other",
                                      "steps": [{"command": "step 0"}, {"command": "step 1"}]}
        record["evidence"].append({"field": "/verification", "source_id": "github_api", "quote": None,
                                   "method": "sandbox", "checked_at": "2026-10-30T10:00:00+08:00"})
        path.write_text(json.dumps(record))
    return tmp_path / "pipeline.db", out


def test_scoring_writes_only_scores_and_reuses_the_rubric(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    before = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text()).model_dump(mode="json")
    calls: list[str] = []
    summary = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                            grade=fake_grade(calls=calls))
    assert summary.written == ["tinyq"] and calls == ["score:tinyq"] and not summary.errors
    after = json.loads((out / "tinyq.json").read_text())
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


def test_unverified_records_are_capped_below_the_treasure_line(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path, verified=False)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade())
    scores = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text()).scores
    assert scores.quality.cap_reason == "unverified" and scores.quality.total <= 69
    assert scores.quality.components.sandbox_verification.score is None
    assert not scores.treasure.is_treasure


def test_profiles_rewrite_keeps_scores(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade())
    scored = json.loads((out / "tinyq.json").read_text())
    again = write_profiles(PipelineDB(db_path), model=MODEL, out_dir=out, now=NOW)
    assert again.unchanged == ["tinyq"]
    assert json.loads((out / "tinyq.json").read_text())["scores"] == scored["scores"]


def test_write_back_keeps_scores_and_refreshes_what_follows_the_run(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path, verified=False)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW, grade=fake_grade(1))
    before = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text()).scores
    assert before.quality.cap_reason == "unverified"
    new_run = VerificationRun.model_validate(run("verify-2", steps=5, pitfalls=1))
    written, note = write_back(new_run, "tinyq", out)
    assert written and "scores refreshed" in note
    after = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text())
    assert after.verification.level == "function" and after.install.linux.run_id == "verify-2"
    s = after.scores
    assert s.quality.cap_reason is None
    assert s.quality.components.sandbox_verification.score == pytest.approx(0.85 * 0.8)
    assert s.docs_rubric == before.docs_rubric and s.popularity == before.popularity
    assert s.quality.components.install_docs == before.quality.components.install_docs


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
