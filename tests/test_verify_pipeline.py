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
    assert [(t.command, t.passed, t.exit_code) for t in run.smoke_tests] == [
        ("graphtty --version", True, 0), ("graphtty graph.json", True, 0)]
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


def test_failed_claim_is_recorded_without_replay(tmp_path: Path):
    server = FakeServer(response("r1", run_cmd("uv tool install graphtty")),
                        response("r2", finish(level="failed", blocking_error="no wheel for py3.12")))
    boxes = Boxes({"agent": {"uv tool install": (1, "", "no wheel")}})
    outcome, _ = verify(tmp_path, server, boxes)
    assert outcome.run.level == "failed" and outcome.run.blocking_error == "no wheel for py3.12"
    assert [role for role, _ in boxes.made] == ["agent"]


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


def test_write_back_skips_unpassed_runs_and_missing_records(tmp_path: Path):
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("inconclusive")), Boxes({}),
                        write=True, data_dir=tmp_path / "nowhere")
    assert not outcome.written and outcome.write_note == "not written: level unverified, replayed True"
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
