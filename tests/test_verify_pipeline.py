"""Agent -> replay -> judge -> VerificationRun -> write-back, with fake boxes and a mocked model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import pickfit.env
from pickfit import meta
from pickfit.ledger import Caps, Ledger
from pickfit.schema import SoftwareRecord, VerificationRun
from pickfit.verify.pipeline import verify_task
from pickfit.verify.result import infer_install_method
from pickfit.verify.task import load_fixture
from verify_fakes import FakeBox, FakeServer, finish, response, run_cmd

FIXTURES = Path(__file__).parent / "fixtures"
GRAPH = "cat > graph.json <<'EOF'\n{\"nodes\": [\"a\", \"b\"], \"edges\": [[\"a\", \"b\"]]}\nEOF"
SCRIPT = {
    "uv tool install graphtty": (0, "Installed 1 executable: graphtty", ""),
    "graphtty --version": (0, "graphtty 0.4.1", ""),
    "cat > graph.json": (0, "", ""),
    "graphtty graph.json": (0, "a ──▶ b", ""),
}
SMOKE = [{"command_id": 2, "setup_ids": [], "expected_signal": "0.4.1", "expected_exit_code": 0,
          "observed_excerpt": "graphtty 0.4.1"},
         {"command_id": 4, "setup_ids": [3], "expected_signal": "a ──▶ b", "expected_exit_code": 0,
          "observed_excerpt": "a ──▶ b"}]


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


def judge_answer(verdict: str) -> dict[str, Any]:
    text = json.dumps({"verdict": verdict, "observed": "An arrow from a to b.", "error_text": None,
                       "matches_expected_signal": verdict == "working",
                       "evidence_regions": [{"image": 1, "label": "edge", "box": {
                           "x_min": 0, "y_min": 500, "x_max": 400, "y_max": 800}}]})
    return {"id": "judge", "object": "response", "created_at": 0, "model": "muse-spark-1.3-contributor",
            "status": "completed", "output": [{"type": "message", "id": "m", "role": "assistant",
                                               "status": "completed",
                                               "content": [{"type": "output_text", "text": text,
                                                            "annotations": []}]}],
            "usage": {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 200,
                      "output_tokens_details": {"reasoning_tokens": 100}, "total_tokens": 2200}}


def agent_turns(level: str = "function") -> list[dict[str, Any]]:
    return [response("r1", run_cmd("uv tool install graphtty")),
            response("r2", run_cmd("graphtty --version")),
            response("r3", run_cmd(GRAPH)),
            response("r4", run_cmd("graphtty graph.json")),
            response("r5", finish(level=level, steps=[1], smoke=SMOKE, install_method="uv",
                                  tool_version="0.4.1",
                                  pitfalls=[{"readme_said": "pip install graphtty",
                                             "actually_needed": "uv tool install graphtty"}]))]


class Boxes:
    """Box factory: one FakeBox per role, scripted per role."""

    def __init__(self, scripts: dict[str, dict[str, tuple[int, str, str]]]) -> None:
        self.scripts = scripts
        self.made: list[tuple[str, FakeBox]] = []

    def __call__(self, run_id: str, role: str) -> FakeBox:
        box = FakeBox(dict(self.scripts.get(role, SCRIPT)))
        self.made.append((role, box))
        return box


def verify(tmp_path: Path, server: FakeServer, boxes: Boxes, **kw: Any):
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# graphtty\n")
    ledger = Ledger(tmp_path / "l.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    lines: list[str] = []
    outcome = verify_task(task, boxes, client=server.client(), ledger=ledger, runs_dir=tmp_path / "runs",
                          log=lines.append, run_id="verify-graphtty-20261029-000000-abcd", **kw)
    return outcome, lines


def test_full_pass_is_replayed_offline_and_judged(tmp_path: Path):
    server = FakeServer(*agent_turns(), judge_answer("working"))
    boxes = Boxes({})
    outcome, lines = verify(tmp_path, server, boxes)
    run = outcome.run
    assert outcome.passed and run.level == "function" and run.replayed
    assert run.judge.verdict == "working" and run.judge.model == "muse-spark-1.3-contributor"
    assert [s.command for s in run.steps] == ["uv tool install graphtty"]
    assert [(t.command, t.passed, t.exit_code, t.offline) for t in run.smoke_tests] == [
        ("graphtty --version", True, 0, True), ("graphtty graph.json", True, 0, True)]
    assert run.smoke_tests[0].setup == []
    assert [s.command for s in run.smoke_tests[1].setup] == [GRAPH]  # the input file it reads
    assert run.install_method == "uv" and run.tool_version == "0.4.1"
    assert run.pitfalls[0].actually_needed == "uv tool install graphtty"
    assert run.runner == "fake" and (run.os, run.arch, run.method) == ("linux", "x86_64", "sandbox")
    assert run.cost_usd and run.cost_usd > 0
    # Two fresh boxes, both closed; the replay ran the checks with the network off.
    assert [role for role, _ in boxes.made] == ["agent", "replay"]
    assert all(box.closed for _, box in boxes.made)
    replay_box = boxes.made[1][1]
    assert [c for c, _ in replay_box.ran] == ["uv tool install graphtty", GRAPH, "graphtty --version",
                                              "graphtty graph.json"]
    # Evidence next to the agent's report.
    saved = VerificationRun.model_validate_json((outcome.evidence_dir / "verification_run.json").read_text())
    assert saved == run
    for name in ("report.json", "replay.json", "judge.json", "outcome.json", "check-1-cmd4.judged.png"):
        assert (outcome.evidence_dir / name).exists(), name
    assert json.loads((outcome.evidence_dir / "outcome.json").read_text())["offline"] is True
    assert lines[-1].startswith("result · graphtty · level function · replayed True · judge working · "
                                "offline True")


def test_judge_that_sees_an_error_vetoes_the_pass(tmp_path: Path):
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("error_visible")), Boxes({}))
    run = outcome.run
    assert run.level == "unverified" and run.unverified_reason == "other" and run.replayed
    assert "screen judge did not confirm it (error_visible" in run.blocking_error


def test_failed_replay_skips_the_judge(tmp_path: Path):
    broken = {**SCRIPT, "uv tool install graphtty": (1, "", "error: Failed to fetch")}
    server = FakeServer(*agent_turns())  # no reply left for a judge call
    outcome, _ = verify(tmp_path, server, Boxes({"replay": broken}))
    run = outcome.run
    assert run.level == "unverified" and not run.replayed and run.judge is None
    assert "replay did not pass: step 1 exited 1" in run.blocking_error
    assert not (outcome.evidence_dir / "judge.json").exists()


BROKEN = {**SCRIPT, "graphtty --version": (1, "", "ModuleNotFoundError: No module named 'graphtty'")}


def failed_turns(blocking: str = "the wheel ships no code", failing: int | None = 2) -> list[dict[str, Any]]:
    return [response("r1", run_cmd("uv tool install graphtty")),
            response("r2", run_cmd("graphtty --version")),
            response("r3", finish(level="failed", steps=[1], smoke=SMOKE[:1], blocking_error=blocking,
                                  failing_command_id=failing))]


def test_a_failure_counts_only_when_a_fresh_box_repeats_it(tmp_path: Path):
    boxes = Boxes({"agent": BROKEN, "confirm": BROKEN})
    outcome, lines = verify(tmp_path, FakeServer(*failed_turns()), boxes)
    run = outcome.run
    assert run.level == "failed" and run.replayed and run.blocking_error == "the wheel ships no code"
    assert [role for role, _ in boxes.made] == ["agent", "confirm"] and boxes.made[1][1].closed
    assert [c for c, _ in boxes.made[1][1].ran] == ["uv tool install graphtty", "graphtty --version"]
    assert [(t.command, t.passed, t.exit_code) for t in run.smoke_tests] == [("graphtty --version", False, 1)]
    assert (outcome.evidence_dir / "confirm.json").exists() and "failure repeated" in "\n".join(lines)
    # The fresh box installs it fine: not the software's failure after all.
    outcome, _ = verify(tmp_path, FakeServer(*failed_turns()), Boxes({"agent": BROKEN}))
    run = outcome.run
    assert (run.level, run.unverified_reason, run.replayed) == ("unverified", "other", False)
    assert run.blocking_error.startswith("not confirmed in a fresh box (command 2 passed in a fresh box)")


def test_a_failure_the_box_explains_is_unverified_with_its_reason(tmp_path: Path):
    # The failing command's own output shows the box's limit: no box is spent confirming it.
    no_rust = {"uv tool install graphtty": (1, "", "error: can't find Rust compiler")}
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")),
                        response("r2", finish(level="failed", blocking_error="the wheel does not build",
                                              failing_command_id=1)))
    boxes = Boxes({"agent": no_rust})
    outcome, _ = verify(tmp_path, server, boxes)
    run = outcome.run
    assert (run.level, run.unverified_reason) == ("unverified", "needs_toolchain")
    assert [role for role, _ in boxes.made] == ["agent"]
    assert "the box, not the software, explains the failure (needs_toolchain)" in outcome.notes


def test_the_agents_words_decide_only_when_the_log_names_no_failure(tmp_path: Path):
    # A failing command whose output shows the tool's own fault: the description's mention of Rust
    # does not make it the box's.
    turns = failed_turns("graphtty crashes; its source build also requires Rust 1.91+")
    outcome, _ = verify(tmp_path, FakeServer(*turns), Boxes({"agent": BROKEN, "confirm": BROKEN}))
    assert outcome.run.level == "failed" and outcome.run.replayed
    # No failing command and no check passed: the description decides.
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")),
                        response("r2", finish(level="failed", blocking_error="needs Rust 1.91+, absent here")))
    outcome, _ = verify(tmp_path, server, Boxes({"agent": BROKEN}))
    assert (outcome.run.level, outcome.run.unverified_reason) == ("unverified", "needs_toolchain")


def test_a_step_that_fakes_a_system_command_keeps_the_run_from_passing(tmp_path: Path):
    shim = "printf '#!/bin/sh\\necho 0' > ~/.local/bin/nvidia-smi && chmod +x ~/.local/bin/nvidia-smi"
    smoke = [{**t, "command_id": t["command_id"] + 1, "setup_ids": [i + 1 for i in t["setup_ids"]]} for t in SMOKE]
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")), response("r2", run_cmd(shim)),
                        response("r3", run_cmd("graphtty --version")), response("r4", run_cmd(GRAPH)),
                        response("r5", run_cmd("graphtty graph.json")),
                        response("r6", finish(level="function", steps=[1, 2], smoke=smoke)), judge_answer("working"))
    outcome, _ = verify(tmp_path, server, Boxes({}))
    run = outcome.run
    assert (run.level, run.unverified_reason, run.replayed) == ("unverified", "other", True)
    assert "step 2 only works around the box: it replaces the system command nvidia-smi" in run.blocking_error
    # Cited only as a smoke test's setup, the shim still keeps the run from passing.
    smoke = [{**SMOKE[0], "command_id": 3, "setup_ids": [2]}]
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")), response("r2", run_cmd(SHIM)),
                        response("r3", run_cmd("graphtty --version")),
                        response("r4", finish(level="install", steps=[1], smoke=smoke)), judge_answer("working"))
    outcome, _ = verify(tmp_path, server, Boxes({}))
    assert (outcome.run.level, outcome.run.unverified_reason) == ("unverified", "other")
    assert "setup 2 only works around the box" in outcome.run.blocking_error


def test_a_failure_the_agents_shim_caused_is_neither_confirmed_nor_the_tools(tmp_path: Path):
    crashes = {**SCRIPT, "graphtty --version": (1, "", "ValueError: could not parse nvidia-smi output")}
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")), response("r2", run_cmd(SHIM)),
                        response("r3", run_cmd("graphtty --version")),
                        response("r4", finish(level="failed", steps=[1, 2], failing_command_id=3,
                                              blocking_error="graphtty crashes at startup with a ValueError")))
    boxes = Boxes({"agent": crashes, "confirm": crashes})
    outcome, _ = verify(tmp_path, server, boxes)
    run = outcome.run
    assert (run.level, run.unverified_reason, run.replayed) == ("unverified", "other", False)
    assert [role for role, _ in boxes.made] == ["agent"]  # no box spent confirming it
    assert "step 2 only works around the box: it replaces the system command nvidia-smi" in run.blocking_error


SHIM = "printf '#!/bin/sh\\necho 0' > ~/.local/bin/nvidia-smi && chmod +x ~/.local/bin/nvidia-smi"


def bare_record(data_dir: Path) -> Path:
    """The example record with no runs, as a profile has before verification."""
    data_dir.mkdir(exist_ok=True)
    record = json.loads((FIXTURES / "software_example.json").read_text())
    record.update(slug="graphtty", scores=None)
    record["verification"] = {"level": "unverified", "unverified_reason": "not_run", "checked_at": None, "runs": []}
    record["install"]["linux"] = None
    path = data_dir / "graphtty.json"
    path.write_text(json.dumps(record))
    return path


def test_write_back_keeps_a_repeated_failure_but_never_over_a_pass(tmp_path: Path):
    path = bare_record(tmp_path / "data")
    boxes = Boxes({"agent": BROKEN, "confirm": BROKEN})
    outcome, _ = verify(tmp_path, FakeServer(*failed_turns()), boxes, write=True, data_dir=path.parent)
    assert outcome.written
    record = SoftwareRecord.model_validate_json(path.read_text())
    assert record.verification.level == "failed" and record.verification.runs[0].id == outcome.run_id
    assert record.install.linux is None  # a failure is no install guide
    # A record with a passed linux run keeps it.
    passed = json.loads((FIXTURES / "software_example.json").read_text()) | {"slug": "graphtty"}
    path.write_text(json.dumps(passed))
    outcome, _ = verify(tmp_path, FakeServer(*failed_turns()), boxes, write=True, data_dir=path.parent)
    assert not outcome.written
    assert outcome.write_note == "not written: failed would sit beside the passed linux run run-20261031-linux-1"
    assert json.loads(path.read_text()) == passed


def test_write_back_records_the_box_reason(tmp_path: Path):
    path = bare_record(tmp_path / "data")
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")),
                        response("r2", finish(level="failed",
                                              blocking_error="No container engine in the box (neither docker nor podman)")))
    outcome, _ = verify(tmp_path, server, Boxes({"agent": BROKEN}), write=True, data_dir=path.parent)
    assert outcome.written
    verification = SoftwareRecord.model_validate_json(path.read_text()).verification
    assert (verification.level, verification.unverified_reason) == ("unverified", "needs_container")


def test_write_back_updates_the_record(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    record = json.loads((FIXTURES / "software_example.json").read_text())
    record["slug"] = "graphtty"
    (data_dir / "graphtty.json").write_text(json.dumps(record))
    outcome, lines = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), Boxes({}),
                            write=True, data_dir=data_dir)
    assert outcome.written and "write-back: written" in "\n".join(lines)
    updated = SoftwareRecord.model_validate_json((data_dir / "graphtty.json").read_text())
    linux = [r for r in updated.verification.runs if r.os == "linux"]
    assert [r.id for r in linux] == [outcome.run_id]  # replaces the earlier linux sandbox run
    guide = updated.install.linux
    assert guide.basis == "replayed" and guide.run_id == outcome.run_id
    assert [s.command for s in guide.steps] == ["uv tool install graphtty"]
    assert guide.check.command == "graphtty --version" and guide.first_task == "graphtty graph.json"
    assert updated.verification.level == "function"


def test_write_back_keeps_a_stronger_passed_run(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    record = json.loads((FIXTURES / "software_example.json").read_text()) | {"slug": "graphtty"}
    (data_dir / "graphtty.json").write_text(json.dumps(record))
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns("install"), judge_answer("working")), Boxes({}),
                        write=True, data_dir=data_dir)
    assert outcome.run.level == "install" and not outcome.written
    assert outcome.write_note == "not written: install would replace the stronger function run run-20261031-linux-1"


def test_write_back_skips_unpassed_runs_and_missing_records(tmp_path: Path):
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("inconclusive")), Boxes({}),
                        write=True, data_dir=tmp_path / "nowhere")
    assert not outcome.written
    assert outcome.write_note == "not written: unverified (other) says nothing about the software"
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), Boxes({}),
                        write=True, data_dir=tmp_path / "nowhere")
    assert not outcome.written and "does not exist yet" in outcome.write_note


def test_infer_install_method():
    assert infer_install_method(["pipx install evnx"]) == "pipx"
    assert infer_install_method(["curl -fsSL https://x.dev/install.sh | sh"]) == "script"
    assert infer_install_method(["curl -L -o t.tgz https://github.com/o/r/releases/download/v1/t.tgz "
                                 "&& tar xzf t.tgz"]) == "binary"
    assert infer_install_method(["npm install -g tldr"]) == "npm"
    assert infer_install_method(["make"], "source") == "source"


def test_a_claim_the_log_refuses_says_why(tmp_path: Path):
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty || true")),
                        response("r2", run_cmd("graphtty --version")),
                        response("r3", finish(level="function", steps=[1], smoke=SMOKE[:1])),
                        response("r4", finish(level="function", steps=[1], smoke=SMOKE[:1])))
    outcome, _ = verify(tmp_path, server, Boxes({}))
    run = outcome.run
    assert run.level == "unverified" and not run.replayed
    assert run.blocking_error.startswith("the command log does not support the claimed function: step 1 does "
                                         "not show a success (`||`")


def test_a_long_check_keeps_its_first_part_as_setup(tmp_path: Path):
    big = "cat > graph.json <<'EOF'\n" + '{"nodes": ["a", "b"]}\n' * 40 + "EOF"
    script = {**SCRIPT, "cat > graph.json": (0, "a ──▶ b", "")}
    long_check = f"{big}\ngraphtty graph.json"
    smoke = [SMOKE[0], {"command_id": 3, "setup_ids": [], "expected_signal": "a ──▶ b", "expected_exit_code": 0,
                        "observed_excerpt": "a ──▶ b"}]
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")),
                        response("r2", run_cmd("graphtty --version")),
                        response("r3", run_cmd(long_check)),
                        response("r4", finish(level="function", steps=[1], smoke=smoke)),
                        judge_answer("working"))
    outcome, _ = verify(tmp_path, server, Boxes({"agent": script, "replay": script}))
    test = outcome.run.smoke_tests[1]
    assert len(long_check) > 500 and outcome.run.level == "function"
    assert test.command == "graphtty graph.json" and [s.command for s in test.setup] == [big]


def test_the_guide_prefers_a_first_task_that_worked_offline():
    from pickfit.schema import SmokeTest
    from pickfit.verify.result import install_guide

    record = json.loads((FIXTURES / "software_example.json").read_text())
    run = VerificationRun.model_validate(record["verification"]["runs"][0])
    tests = [SmokeTest(command="tool --version", expected_signal="1.0", exit_code=0, passed=True, offline=True),
             SmokeTest(command="npx tool@latest", expected_signal="ok", exit_code=0, passed=True, offline=False),
             SmokeTest(command="tool scan --offline", expected_signal="ok", exit_code=0, passed=True, offline=True)]
    guide = install_guide(run.model_copy(update={"smoke_tests": tests}))
    assert guide.first_task == "tool scan --offline" and guide.check.command == "tool --version"
