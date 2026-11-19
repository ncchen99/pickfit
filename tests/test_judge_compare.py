"""scripts/judge_compare.py on saved evidence with a fake client: nothing leaves the process."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pickfit.ledger import Ledger
from pickfit.meta import BULK_MODEL, PROD_MODEL
from pickfit.verify.web_verify import WebTarget

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("judge_compare", ROOT / "scripts" / "judge_compare.py")
judge_compare = importlib.util.module_from_spec(_SPEC)
sys.modules["judge_compare"] = judge_compare  # its dataclasses look their module up
_SPEC.loader.exec_module(judge_compare)

RUN = "verify-tinyq-20261118-100000-abcd"


def ran(cid: int, command: str, stdout: str, **more: Any) -> dict[str, Any]:
    return {"command_id": cid, "command": command, "exit_code": 0, "seconds": 1.0, "timed_out": False,
            "stdout": stdout, "stderr": "", "network": False, **more}


def check(cid: int, command: str, kind: str, run: dict[str, Any]) -> dict[str, Any]:
    return {"command_id": cid, "command": command, "kind": kind, "expected_exit_code": 0, "expected_signal": "ok",
            "passed": True, "offline": True, "run": run, "problems": [], "offline_problems": [], "setup": []}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "verify" / RUN
    run_dir.mkdir(parents=True)
    Image.new("RGB", (1280, 800), (30, 30, 30)).save(run_dir / "replay-3-1.png")
    gone = "/Users/someone/.claude/worktrees/gone/runs/verify/" + RUN + "/replay-3-1.png"  # a removed worktree
    window = {"x": 100, "y": 100, "width": 600, "height": 400, "title": "tinyq"}
    checks = [check(2, "tinyq --version", "version", ran(2, "tinyq --version", "tinyq 1.0")),
              check(3, "tinyq-gui", "gui", ran(3, "tinyq-gui", "gui tier: window", screenshot=gone,
                                              gui={"tier": "window", "windows": [window], "log_tail": ""}))]
    (run_dir / "replay.json").write_text(json.dumps({"plan": {}, "result": {"passed": True, "checks": checks}}))
    failed = tmp_path / "runs" / "verify" / "verify-broken-20261118-100000-abcd"
    failed.mkdir(parents=True)
    (failed / "replay.json").write_text(json.dumps({"plan": {}, "result": {"passed": False, "checks": checks}}))
    return tmp_path


class Client:
    """The judges' answers: Haiku calls the GUI's sign-in wall a main screen and sees the web feature Opus does not."""

    returns_whole_response = True
    api_key = None

    def __init__(self) -> None:
        self.models: list[str] = []
        self.responses = self

    def create(self, *, stream: bool = False, **request: Any) -> dict[str, Any]:
        model, kind = request["model"], request["text"]["format"]["name"]
        self.models.append(model)
        haiku = model == BULK_MODEL
        answer = {
            "screen_judge": {"verdict": "working", "observed": "Version shown.", "error_text": None,
                             "matches_expected_signal": True, "evidence_regions": [], "evidence": []},
            "gui_screen_judge": {"screen": "main_ui" if haiku else "crash_or_error", "observed": "A window.",
                                 "error_text": None, "evidence_regions": []},
            "web_function_judge": {"feature_shown": haiku, "feature": None, "observed": "Changed.",
                                   "result_visible": None},
        }[kind]
        return {"id": f"msg_{len(self.models)}", "object": "response", "model": model, "status": "completed",
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
                "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
                          "input_tokens_details": {"cached_tokens": 0}}}


def test_saved_replays_give_a_cli_case_and_a_gui_case_and_failed_runs_none(root: Path):
    cli, gui = judge_compare.replay_cases([root / "runs"])
    assert [c.key for c in cli] == [c.key for c in gui] == [RUN]
    launch = gui[0].data["check"]
    assert launch.run.screenshot == str(root / "runs" / "verify" / RUN / "replay-3-1.png")  # found beside it


def test_each_kind_is_asked_on_both_models_and_a_lenient_cheap_model_is_counted(root: Path, tmp_path: Path):
    cli, gui = judge_compare.replay_cases([root / "runs"])
    shots = tmp_path / "shots"
    shots.mkdir()
    for name in ("before.png", "after.png"):
        Image.new("RGB", (320, 200), (200, 200, 200)).save(shots / name)
    web = judge_compare.Case("web", "web-tinyq-1", "tinyq", {
        "target": WebTarget(slug="tinyq", name="tinyq", url="https://tinyq.example", use_case="Queries.",
                            features=["run a query"]),
        "before": shots / "before.png", "after": shots / "after.png", "outcome": {"done": True},
        "check": {"passed": True}})
    cases = [*cli, *gui, web]
    client, ledger = Client(), Ledger(tmp_path / "ledger.sqlite")
    answers: dict[str, list[Any]] = {}
    for model in judge_compare.MODELS:
        answers[model] = []
        for i, case in enumerate(cases):
            work = tmp_path / f"work-{model}-{i}"
            work.mkdir()
            answers[model].append(judge_compare.ask(case, model, work, run_id="cmp", max_usd=1.0, client=client,
                                                    ledger=ledger, runs_dir=tmp_path / "runs-out"))
    assert sorted(set(client.models)) == sorted([PROD_MODEL, BULK_MODEL]) and len(client.models) == 6
    assert not (root / "runs" / "verify" / RUN / "replay-3-1.app.png").exists()  # the evidence is left alone
    report = judge_compare.compare(cases, answers)
    assert report["cli"]["same_verdict"] == 1 and report["cli"]["cheap_passes_prod_does_not"] == []
    assert report["gui"]["cheap_passes_prod_does_not"] == [RUN]
    assert report["gui"]["differences"] == [{"case": RUN, PROD_MODEL: "crash_or_error", BULK_MODEL: "main_ui"}]
    assert report["web"]["cheap_passes_prod_does_not"] == ["web-tinyq-1"]
    assert report["switch_condition"] == {"cheap_passes_prod_does_not": 2, "needs": 0}


def test_the_dry_run_counts_and_estimates_without_a_call(root: Path, capsys: pytest.CaptureFixture[str]):
    def no_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no call in a dry run")

    assert judge_compare.main([str(root), "--dry-run", "--data-dir", str(root / "none")], ask_one=no_call) == 0
    assert "1 cli, 1 gui, 0 web cases saved" in capsys.readouterr().err
