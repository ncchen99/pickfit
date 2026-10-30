"""Feature coverage: the agent checks each advertised feature, the log and a fresh box decide which held."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

import pickfit.env
from pickfit import meta
from pickfit.ledger import Caps, Ledger
from pickfit.schema import Cited, SoftwareRecord, VerificationRun
from pickfit.verify.agent import FINISH_TOOL, AgentLimits, render_task
from pickfit.verify.features import FinishFeature
from pickfit.verify.pipeline import verify_task
from pickfit.verify.plan import plan_for
from pickfit.verify.task import VerifyTask, load_fixture
from verify_fakes import FakeBox, FakeServer, finish, response, run_cmd

FIXTURES = Path(__file__).parent / "fixtures"
GRAPH = "cat > graph.json <<'EOF'\n{\"nodes\": [\"a\", \"b\"], \"edges\": [[\"a\", \"b\"]]}\nEOF"
NEON = "graphtty graph.json --theme neon"
FEATURES = [("render a graph as ASCII art", "Turn any directed graph into colored ASCII art"),
            ("switch color themes", "graphtty --list-themes"),
            ("show the graph in a browser", "open it in your browser"),
            ("export to SVG", "--svg out.svg")]


def script(**overrides: tuple[int, str, str]) -> dict[str, tuple[int, str, str]]:
    """The box's answers; longer commands first, since the first matching substring wins."""
    base = {
        NEON: (1, "", "Error: unknown theme 'neon'"),
        "graphtty --list-themes": (0, "default\nmono\nneon-dark", ""),
        "uv tool install graphtty": (0, "Installed 1 executable: graphtty", ""),
        "graphtty --version": (0, "graphtty 0.4.1", ""),
        "cat > graph.json": (0, "", ""),
        "graphtty graph.json": (0, "a ──▶ b", ""),
    }
    return {**overrides, **{k: v for k, v in base.items() if k not in overrides}}


SMOKE = [{"command_id": 2, "setup_ids": [], "expected_signal": "0.4.1", "expected_exit_code": 0,
          "observed_excerpt": "graphtty 0.4.1"},
         {"command_id": 4, "setup_ids": [3], "expected_signal": "a ──▶ b", "expected_exit_code": 0,
          "observed_excerpt": "a ──▶ b"},
         {"command_id": 5, "setup_ids": [3], "expected_signal": "a ──▶ b", "expected_exit_code": 0,
          "observed_excerpt": "Error: unknown theme 'neon'"}]


def feature(n: int, status: str, ids: list[int] | None = None, reason: str | None = None,
            failure: str | None = None, note: str = "") -> dict[str, Any]:
    return {"feature": n, "status": status, "command_ids": ids or [], "reason": reason, "failure": failure,
            "note": note}


REPORTED = [feature(1, "checked", [4]), feature(2, "test_failed", [5], failure="tool", note="unknown theme"),
            feature(3, "not_checked", reason="needs_display", note="no browser in the box")]


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


def graphtty(features: list[tuple[str, str]] = FEATURES) -> VerifyTask:
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# graphtty\n")
    cited = [Cited[str](value=label, quote=quote) for label, quote in features]
    return dataclasses.replace(task, extraction=task.extraction.model_copy(update={"features": cited}))


def judge_answer() -> dict[str, Any]:
    text = json.dumps({"verdict": "working", "observed": "An arrow from a to b.", "error_text": None,
                       "matches_expected_signal": True, "evidence_regions": []})
    return {"id": "judge", "object": "response", "created_at": 0, "model": "muse-spark-1.3-contributor",
            "status": "completed", "output": [{"type": "message", "id": "m", "role": "assistant",
                                               "status": "completed",
                                               "content": [{"type": "output_text", "text": text,
                                                            "annotations": []}]}],
            "usage": {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 200,
                      "output_tokens_details": {"reasoning_tokens": 100}, "total_tokens": 2200}}


def turns(features: list[dict[str, Any]], fifth: str = NEON, smoke: list[dict[str, Any]] = SMOKE
          ) -> list[dict[str, Any]]:
    return [response("r1", run_cmd("uv tool install graphtty")),
            response("r2", run_cmd("graphtty --version")),
            response("r3", run_cmd(GRAPH)),
            response("r4", run_cmd("graphtty graph.json")),
            response("r5", run_cmd(fifth)),
            response("r6", finish(level="function", steps=[1], smoke=smoke, install_method="uv",
                                  tool_version="0.4.1", features=features))]


class Boxes:
    def __init__(self, agent: dict[str, tuple[int, str, str]], replay: dict[str, tuple[int, str, str]]) -> None:
        self.scripts = {"agent": agent, "replay": replay}
        self.made: list[tuple[str, FakeBox]] = []

    def __call__(self, run_id: str, role: str) -> FakeBox:
        box = NetBox(dict(self.scripts[role]))
        self.made.append((role, box))
        return box


class NetBox(FakeBox):
    """Remembers whether the network was on for each command."""

    network_enabled = True

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None):
        result = super().exec(command, timeout_s, cwd=cwd)
        self.ran[-1] = (command, timeout_s, self.network_enabled)  # type: ignore[assignment]
        return result


def verify(tmp_path: Path, replies: list[dict[str, Any]], boxes: Boxes, task: VerifyTask | None = None, **kw: Any):
    ledger = Ledger(tmp_path / "l.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    lines: list[str] = []
    outcome = verify_task(task or graphtty(), boxes, client=FakeServer(*replies).client(), ledger=ledger,
                          runs_dir=tmp_path / "runs", log=lines.append,
                          run_id="verify-graphtty-20261031-000000-abcd", **kw)
    return outcome, lines


def by_name(run: VerificationRun) -> dict[str, Any]:
    return {f.feature: f for f in run.features}


# ---------------------------------------------------------------- the task and the finish tool


def test_the_task_lists_each_feature_with_its_readme_quote():
    task = graphtty()
    text = render_task(task, plan_for(task.extraction, "linux"), FakeBox(), AgentLimits())
    assert 'F1. render a graph as ASCII art (README: "Turn any directed graph into colored ASCII art")' in text
    assert "F4. export to SVG" in text and "Feature checks:" in text
    assert "Feature checks:" not in render_task(graphtty([]), plan_for(task.extraction, "linux"), FakeBox(),
                                                AgentLimits())
    props = FINISH_TOOL["parameters"]["properties"]
    assert "features" in FINISH_TOOL["parameters"]["required"]
    item = props["features"]["items"]
    assert set(item["required"]) == {"feature", "status", "command_ids", "reason", "failure", "note"}


def test_finish_feature_takes_null_strings_and_unknown_reasons():
    claim = FinishFeature.model_validate({"feature": 2, "status": "not_checked", "command_ids": [],
                                          "reason": "needs_microphone", "failure": "null", "note": ""})
    assert (claim.reason, claim.failure, claim.note) == ("other", None, None)


# ---------------------------------------------------------------- end to end


def test_each_feature_is_checked_failed_or_not_checked_with_a_reason(tmp_path: Path):
    boxes = Boxes(script(), script())
    outcome, lines = verify(tmp_path, [*turns(REPORTED), judge_answer()], boxes)
    run = outcome.run
    assert run.level == "function" and run.replayed
    features = by_name(run)
    assert list(features) == [label for label, _ in FEATURES]
    render = features["render a graph as ASCII art"]
    assert (render.status, [run.smoke_tests[i].command for i in render.smoke_tests]) == (
        "checked", ["graphtty graph.json"])
    themes = features["switch color themes"]
    assert (themes.status, themes.failure, themes.note) == ("test_failed", "tool", "unknown theme")
    failed = run.smoke_tests[themes.smoke_tests[0]]
    assert (failed.command, failed.passed, failed.exit_code, failed.offline) == (NEON, False, 1, None)
    assert [s.command for s in failed.setup] == [GRAPH] and "unknown theme" in failed.observed_excerpt
    browser = features["show the graph in a browser"]
    assert (browser.status, browser.reason, browser.note) == ("not_checked", "needs_display", "no browser in the box")
    svg = features["export to SVG"]
    assert (svg.status, svg.reason) == ("not_checked", "not_attempted")
    # The replay reran the passing checks offline, then the failed feature check once, online.
    replay = [(c, net) for c, _, net in boxes.made[1][1].ran]
    assert replay[-1] == (NEON, True) and replay.count((NEON, True)) == 1
    assert ("graphtty graph.json", False) in replay
    assert any(line.startswith("  features: 1 checked · 1 test_failed · 2 not_checked") for line in lines)
    # The record keeps it, and the schema holds the coverage to the smoke tests.
    assert VerificationRun.model_validate(run.model_dump(mode="json")) == run


def test_a_box_limit_in_the_output_makes_a_failure_the_sandboxes(tmp_path: Path):
    oom = {NEON: (137, "", "Killed: out of memory")}
    outcome, _ = verify(tmp_path, [*turns(REPORTED), judge_answer()], Boxes(script(**oom), script(**oom)))
    themes = by_name(outcome.run)["switch color themes"]
    assert (themes.status, themes.failure, themes.reason) == ("test_failed", "sandbox", "needs_more_resources")


def test_the_tool_is_not_blamed_unless_the_agent_says_so(tmp_path: Path):
    said = [feature(2, "test_failed", [5], failure=None, reason="needs_service", note="registry offline")]
    outcome, _ = verify(tmp_path, [*turns(said), judge_answer()], Boxes(script(), script()))
    themes = by_name(outcome.run)["switch color themes"]
    assert (themes.status, themes.failure, themes.reason) == ("test_failed", "sandbox", "needs_service")


def test_a_failure_the_fresh_box_does_not_repeat_is_not_kept(tmp_path: Path):
    fixed = {NEON: (0, "a ──▶ b", "")}
    outcome, lines = verify(tmp_path, [*turns(REPORTED), judge_answer()], Boxes(script(), script(**fixed)))
    run = outcome.run
    themes = by_name(run)["switch color themes"]
    assert (themes.status, themes.reason, themes.smoke_tests) == ("not_checked", "other", [])
    assert "not again in a fresh box" in themes.note
    assert NEON not in [t.command for t in run.smoke_tests]
    assert "feature 'switch color themes': its failed check did not fail again in the fresh box" in outcome.notes


def test_a_check_that_does_not_pass_again_in_the_fresh_box_does_not_cover(tmp_path: Path):
    smoke = [*SMOKE[:2], {"command_id": 5, "setup_ids": [], "expected_signal": "neon-dark",
                          "expected_exit_code": 0, "observed_excerpt": "neon-dark"}]
    reported = [feature(1, "checked", [4]), feature(2, "checked", [5])]
    broken = {"graphtty --list-themes": (1, "", "Error: themes directory missing")}
    outcome, _ = verify(tmp_path, [*turns(reported, fifth="graphtty --list-themes", smoke=smoke), judge_answer()],
                        Boxes(script(), script(**broken)))
    run = outcome.run
    assert run.level == "function"  # the README example still holds the level
    themes = by_name(run)["switch color themes"]
    assert (themes.status, themes.reason) == ("not_checked", "other")
    assert by_name(run)["render a graph as ASCII art"].status == "checked"


def test_a_version_check_or_a_failing_check_never_covers_a_feature(tmp_path: Path):
    reported = [feature(1, "checked", [2]), feature(2, "checked", [5]), feature(3, "test_failed", [4])]
    outcome, lines = verify(tmp_path, [*turns(reported), judge_answer()], Boxes(script(), script()))
    features = by_name(outcome.run)
    assert [(f.status, f.reason) for f in features.values()][:3] == [("not_checked", "other")] * 3
    assert any("F1 render a graph as ASCII art: no cited smoke test that passed" in line for line in lines)
    assert any("F3 show the graph in a browser: no cited command ran after the install and failed" in line
               for line in lines)


def test_a_finish_without_features_goes_back_once(tmp_path: Path):
    first = turns([])
    again = response("r7", finish(level="function", steps=[1], smoke=SMOKE, install_method="uv",
                                  tool_version="0.4.1", features=REPORTED))
    outcome, lines = verify(tmp_path, [*first, again, judge_answer()], Boxes(script(), script()))
    assert "  finish sent back once: no features reported" in lines
    assert by_name(outcome.run)["render a graph as ASCII art"].status == "checked"


def test_no_listed_features_means_no_coverage_and_no_send_back(tmp_path: Path):
    outcome, lines = verify(tmp_path, [*turns([]), judge_answer()], Boxes(script(), script()), task=graphtty([]))
    assert outcome.run.features == [] and not any("sent back" in line for line in lines)
    assert "features" not in outcome.run.model_dump(mode="json")


def test_an_unverified_run_records_no_coverage(tmp_path: Path):
    broken = {"graphtty graph.json": (1, "", "boom"), "graphtty --version": (1, "", "boom")}
    outcome, _ = verify(tmp_path, turns(REPORTED), Boxes(script(), script(**broken)))
    assert outcome.run.level == "unverified" and outcome.run.features == []


def test_write_back_keeps_the_coverage(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    record = json.loads((FIXTURES / "software_example.json").read_text()) | {"slug": "graphtty"}
    record["features"] = [label for label, _ in FEATURES]
    (data_dir / "graphtty.json").write_text(json.dumps(record))
    outcome, _ = verify(tmp_path, [*turns(REPORTED), judge_answer()], Boxes(script(), script()), write=True,
                        data_dir=data_dir)
    assert outcome.written
    saved = SoftwareRecord.model_validate_json((data_dir / "graphtty.json").read_text())
    run = next(r for r in saved.verification.runs if r.id == outcome.run_id)
    assert [f.status for f in run.features] == ["checked", "test_failed", "not_checked", "not_checked"]
    assert saved.install.linux.first_task == "graphtty graph.json"  # a failed feature check is never the first task


def test_a_container_engine_the_box_lacks_is_named_as_such(tmp_path: Path):
    docker = {NEON: (1, "", "Cannot connect to the Docker daemon at unix:///var/run/docker.sock")}
    outcome, _ = verify(tmp_path, [*turns(REPORTED), judge_answer()], Boxes(script(**docker), script(**docker)))
    themes = by_name(outcome.run)["switch color themes"]
    assert (themes.status, themes.failure, themes.reason) == ("test_failed", "sandbox", "needs_container")
