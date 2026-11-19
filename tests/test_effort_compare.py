"""scripts/effort_compare.py on saved conversations with a fake client: nothing leaves the process."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import Ledger
from pickfit.meta import PROD_MODEL

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("effort_compare", ROOT / "scripts" / "effort_compare.py")
effort_compare = importlib.util.module_from_spec(_SPEC)
sys.modules["effort_compare"] = effort_compare  # its dataclasses look their module up
_SPEC.loader.exec_module(effort_compare)


def call(name: str, cid: str, **args: Any) -> dict[str, Any]:
    block = {"type": "tool_use", "id": cid, "name": name, "input": args}
    return {"type": "function_call", "call_id": cid, "name": name, "arguments": json.dumps(args),
            "anthropic_block": block}


def thought(text: str) -> dict[str, Any]:
    return {"type": "reasoning", "summary": [], "anthropic_block": {"type": "thinking", "thinking": "",
                                                                  "signature": f"sig-{text}"}}


def output(cid: str, text: str) -> dict[str, Any]:
    return {"type": "function_call_output", "call_id": cid, "output": text}


HISTORY = {
    "model": PROD_MODEL, "reasoning_effort": "medium", "instructions": "You verify tools.",
    "tools": [{"type": "function", "name": "run_command", "parameters": {"type": "object", "properties": {}}}],
    "input": [
        {"type": "message", "role": "user", "content": "Task: tinyq."},
        thought("1"), call("run_command", "c1", command="pipx install tinyq", timeout_s=300),
        output("c1", "exit_code: 0"),
        thought("2"), call("run_command", "c2", command="tinyq --version"),
        output("c2", "exit_code: 0\ntinyq 1.0"),
        {"type": "message", "role": "user", "content": "Continue with the tools; call finish when you are done."},
        thought("3"), call("finish", "c3", level="install"),
    ],
}


class Client:
    """Answers like pickfit's Anthropic client: medium repeats the run, low differs at turn 2."""

    returns_whole_response = True
    api_key = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = self

    def create(self, *, stream: bool = False, conversation: bool = False, **request: Any) -> dict[str, Any]:
        effort = request["reasoning"]["effort"]
        self.calls.append({"effort": effort, "conversation": conversation, "items": len(request["input"])})
        turn = sum(1 for item in request["input"] if item.get("type") == "function_call") + 1
        name, args = {1: ("run_command", {"command": "pipx install tinyq", "timeout_s": 120}),
                      2: ("run_command", {"command": "tinyq --version" if effort == "medium" else "tinyq --help"}),
                      3: ("finish", {"level": "install"})}[turn]
        return {"id": f"msg_{len(self.calls)}", "object": "response", "model": PROD_MODEL, "status": "completed",
                "output": [{"type": "function_call", "call_id": f"x{turn}", "name": name,
                            "arguments": json.dumps(args)}],
                "usage": {"input_tokens": 1000, "output_tokens": 300 if effort == "medium" else 120,
                          "total_tokens": 1300, "input_tokens_details": {"cached_tokens": 0}}}


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    saved = tmp_path / "runs" / "verify" / "verify-tinyq-20261119-100000-abcd"
    saved.mkdir(parents=True)
    (saved / "report.json").write_text("{}")
    (saved / "history.json").write_text(json.dumps(HISTORY))
    old = tmp_path / "runs" / "verify" / "verify-old-20261116-100000-abcd"
    old.mkdir(parents=True)
    (old / "report.json").write_text("{}")
    return tmp_path / "runs"


def test_every_answer_in_a_saved_conversation_is_a_decision_point(runs: Path):
    points, skipped = effort_compare.load_points([runs])
    assert [p.turn for p in points] == [1, 2, 3] and len(skipped) == 1 and "verify-old" in skipped[0]
    assert [len(p.input) for p in points] == [1, 4, 8]  # the input before each answer, thinking kept
    assert points[1].input[1]["anthropic_block"]["signature"] == "sig-1"
    assert [p.recorded[0]["name"] for p in points] == ["run_command", "run_command", "finish"]
    assert effort_compare.action(points[0].recorded[0]) == ("run_command", "pipx install tinyq")
    assert effort_compare.action(None) is None


def test_both_efforts_are_asked_in_run_order_and_the_disagreement_is_listed(runs: Path, tmp_path: Path):
    points, _ = effort_compare.load_points([runs])
    client = Client()
    ledger = Ledger(tmp_path / "ledger.sqlite")
    answers = {e: [effort_compare.ask(p, e, run_id="cmp", max_usd=1.0, client=client, ledger=ledger,
                                      runs_dir=tmp_path / "runs") for p in points] for e in ("medium", "low")}
    assert [(c["effort"], c["items"]) for c in client.calls] == [("medium", 1), ("medium", 4), ("medium", 8),
                                                                ("low", 1), ("low", 4), ("low", 8)]
    assert all(c["conversation"] for c in client.calls)  # a run's later point reads the earlier prefix
    report = effort_compare.compare(points, answers, ("medium", "low"))
    assert (report["same_tool"], report["same_action"]) == (1.0, round(2 / 3, 3))
    assert report["medium_as_recorded"] == 1.0 and report["low_as_recorded"] == round(2 / 3, 3)
    assert [(d["turn"], d["low"]) for d in report["disagreements"]] == [(2, ("run_command", "tinyq --help"))]
    assert report["output_tokens"] == {"medium": 900, "low": 360} and report["cost_usd"]["low"] > 0


def test_the_dry_run_counts_points_and_estimates_without_a_call(runs: Path, capsys: pytest.CaptureFixture[str]):
    assert effort_compare.main(["--runs-dir", str(runs), "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert "3 decision points" in err and "1 runs skipped" in err and "about $" in err
    points, _ = effort_compare.load_points([runs])
    cached, uncached = effort_compare.estimate_usd(points, ("medium", "low"))[::-1]
    assert 0 < cached <= uncached
