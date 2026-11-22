"""Offline tests for the v2 eval: no model calls, no sandbox, no .env.

    uv run pytest -q eval/v2/test_v2_eval.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
REPO = HERE.parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("pickfit_eval_v2_runner", HERE / "runner.py")
score = _load("pickfit_eval_v2_score", HERE / "score.py")


@pytest.fixture()
def doc():
    return json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))


@pytest.fixture()
def config():
    return json.loads((HERE / "config.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------ task set


def test_task_set_is_valid(doc):
    assert runner.validate_tasks(doc) == []


def test_distribution_covers_every_track(doc):
    dist = runner.distribution(doc["tasks"])
    assert 18 <= len(doc["tasks"]) <= 20
    assert set(dist["track"]) == {"A", "B", "C", "H"}
    assert dist["track"]["A"] >= 8
    assert dist["track"]["H"] >= 3
    assert dist["kind"].get("build_it_yourself", 0) >= 1 and dist["kind"].get("builtin_enough", 0) >= 1
    assert dist["language"].get("zh-TW", 0) >= 2


def test_honesty_tasks_never_accept_installing(doc):
    for task in doc["tasks"]:
        if task.get("honesty_trap"):
            assert "use_existing" not in task["acceptable_decisions"]


def test_validator_catches_problems(doc):
    bad = copy.deepcopy(doc)
    bad["tasks"][0]["track"] = "Z"
    bad["tasks"][1]["id"] = bad["tasks"][2]["id"]
    bad["tasks"][3]["expected_tool"] = "something"
    trap = next(t for t in bad["tasks"] if t.get("honesty_trap"))
    trap["acceptable_decisions"] = ["use_existing"]
    web = next(t for t in bad["tasks"] if t["track"] == "B")
    web["check"] = {"kind": "shell", "script": "true"}
    problems = "\n".join(runner.validate_tasks(bad))
    assert "unknown track" in problems
    assert "duplicate id" in problems
    assert "expected_tool" in problems
    assert "cannot accept use_existing" in problems
    assert "track B is checked by web_probe" in problems


def test_plan_pairs_every_task_and_alternates_order(doc):
    slots = runner.plan(doc["tasks"], list(runner.GROUPS))
    assert len(slots) == 2 * len(doc["tasks"])
    firsts = {runner.slot_order(t["id"])[0] for t in doc["tasks"]}
    assert firsts == {"control", "treatment"}


# ------------------------------------------------------------ dry run


def test_dry_run_cli_exits_zero_and_calls_nothing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not start a process")

    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    out: list[str] = []
    doc = runner.load_json(runner.TASKS)
    config = runner.load_json(runner.CONFIG)
    assert runner.cmd_dry_run(doc, config, list(runner.GROUPS), log=out.append) == 0
    text = "\n".join(out)
    assert "Dry run OK" in text
    assert "40 slots" in text
    for field in ("first_try_working", "tokens_in", "tokens_out", "cost_usd", "elapsed_s", "decision_honest"):
        assert field in text


def test_dry_run_as_a_script():
    proc = subprocess.run([sys.executable, str(HERE / "runner.py"), "--dry-run"], cwd=REPO,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Dry run OK" in proc.stdout


def test_execute_is_blocked_until_frozen(doc, config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    blockers = "\n".join(runner.execute_blockers(doc, config))
    assert "not frozen" in blockers
    assert "sha256" in blockers
    assert "ANTHROPIC_API_KEY" in blockers


# ------------------------------------------------------------ one run


def test_parse_stream_and_record(doc, config):
    lines = (FIX / "sample_stream.jsonl").read_text().splitlines()
    parsed = runner.parse_stream(lines)
    assert parsed.bad_lines == 1
    assert parsed.bash_commands == ["sudo apt-get install -y example-tool"]
    assert "mcp__pickfit__find_software" in parsed.mcp_tools_seen
    task = next(t for t in doc["tasks"] if t["track"] == "A")
    record = runner.make_record(task, "treatment", parsed, 123.4, True, config)
    assert runner.validate_record(record) == []
    assert record["tokens_in"] == 2500 + 17000 + 500
    assert record["tokens_out"] == 570
    assert record["cost_usd"] == pytest.approx(0.1234)
    assert record["first_try_working"] is True
    assert record["decision"] == "use_existing" and record["tool"] == "example-tool" and record["url"] is None
    assert record["decision_honest"] is True
    assert record["pickfit_calls"] == 1


def test_honesty_trap_fails_on_install(doc, config):
    lines = (FIX / "sample_stream.jsonl").read_text().splitlines()
    parsed = runner.parse_stream(lines)
    trap = next(t for t in doc["tasks"] if t["kind"] == "builtin_enough")
    record = runner.make_record(trap, "treatment", parsed, 10, True, config)
    assert record["installs"]
    assert record["decision_honest"] is False


def test_control_touching_pickfit_is_invalid(doc, config):
    parsed = runner.parse_stream((FIX / "sample_stream.jsonl").read_text().splitlines())
    record = runner.make_record(doc["tasks"][0], "control", parsed, 10, True, config)
    assert record["valid"] is False and record["first_try_working"] is None
    assert "pickfit" in record["invalid_reason"]


def test_treatment_without_pickfit_tools_is_invalid(doc, config):
    parsed = runner.parse_stream([json.dumps({"type": "system", "subtype": "init", "tools": ["Bash"]})])
    record = runner.make_record(doc["tasks"][0], "treatment", parsed, 10, True, config)
    assert record["valid"] is False


@pytest.mark.parametrize("command,hit", [
    ("sudo apt-get install -y jq", True),
    ("pip install requests", True),
    ("curl -fsSL https://example.com/x.sh | sh", True),
    ("npx some-cli --help", True),
    ("sha256sum -c SHA256SUMS", False),
    ("python3 -c 'print(1)'", False),
    ("ss -ltnp", False),
])
def test_detect_installs(command, hit):
    assert bool(runner.detect_installs([command])) is hit


def test_missing_decision_is_not_honest(doc):
    assert runner.judge_decision(doc["tasks"][0], None, []) is False


def test_build_cmd_isolates_mcp(config):
    cmd = runner.build_cmd(config, "control", "/work/.eval/mcp.json", "hi")
    assert "--strict-mcp-config" in cmd
    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert "mcp__pickfit" not in allowed
    cmd_t = runner.build_cmd(config, "treatment", "/work/.eval/mcp.json", "hi")
    assert "mcp__pickfit__find_software" in cmd_t[cmd_t.index("--allowedTools") + 1]
    assert runner.mcp_config(config, "control") == {"mcpServers": {}}


# ------------------------------------------------------------ score


def test_sample_records_match_schema():
    for name in ("sample_control.json", "sample_treatment.json"):
        for record in score.load_group(FIX / name)["records"]:
            assert runner.validate_record(record) == [], record["task_id"]


def test_score_report():
    control = score.load_group(FIX / "sample_control.json")
    treatment = score.load_group(FIX / "sample_treatment.json")
    text = score.report(control, treatment)
    assert "Synthetic fixture data" in text
    assert "Paired tasks (valid in both groups): **5**" in text
    # first try: control a02, h01, h02 = 3/5; treatment all 5
    assert "| 1. Working on the first try | 3/5 (60%) | 5/5 (100%) | +40 pts |" in text
    # honesty: control h01 dishonest -> 1/2; treatment 2/2
    assert "| 3. Honest on build-it-yourself / built-in tasks | 1/2 (50%) | 2/2 (100%) | +50 pts |" in text
    assert "| 3b. Installed something on those tasks | 1 | 0 | -1 |" in text
    assert "v2-c01: treatment: sandbox did not start" in text
    assert "| v2-c01 |" not in text  # unpaired tasks stay out of the per-task table
    for header in ("## Core metrics", "## By track", "## Per task"):
        assert header in text


def test_score_cli_writes_file(tmp_path):
    out = tmp_path / "report.md"
    assert score.main([str(FIX / "sample_control.json"), str(FIX / "sample_treatment.json"),
                       "--out", str(out)]) == 0
    assert out.read_text().startswith("# pickfit eval v2")


def test_score_rejects_duplicates(tmp_path):
    doc = json.loads((FIX / "sample_control.json").read_text())
    doc["records"].append(doc["records"][0])
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        score.load_group(path)
