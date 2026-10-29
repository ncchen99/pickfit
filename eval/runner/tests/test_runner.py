"""Tests for eval/runner/run.py with a fake `claude` (no model calls).

Run with: uv run --with pyyaml==6.0.2 --with pytest python -m pytest eval/runner/tests -q
(not under tests/, so the pickfit suite never collects eval code)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run  # noqa: E402

FAKE = """#!{python}
import json, sys, time, pathlib
args = sys.argv[1:]
here = pathlib.Path({here!r})
mode = (here / "mode.txt").read_text().strip() if (here / "mode.txt").exists() else "ok"
def val(flag):
    return args[args.index(flag) + 1] if flag in args else None
tools = val("--tools").split(",")
mcp = json.loads(pathlib.Path(val("--mcp-config")).read_text())["mcpServers"]
model = val("--model")
prompt = args[-1]
with (here / "calls.log").open("a") as log:
    log.write(json.dumps({{"prompt": prompt[-12:], "mcp": sorted(mcp)}}) + "\\n")
if mode == "crash":
    sys.exit(3)
if mode == "auth":
    print(json.dumps({{"type": "system", "subtype": "init", "model": model, "claude_code_version": "2.1.304",
                      "tools": tools, "mcp_servers": []}}), flush=True)
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "Invalid API key · Please run /login", "total_cost_usd": 0}}))
    sys.exit(1)
if mode == "wrong_model":
    model = "some-other-model"
status = "pending" if mode == "pending" else "connected"
mcp_tools = ["mcp__pickfit__find_alternatives", "mcp__pickfit__find_software", "mcp__pickfit__get_install_guide"] if mcp and status == "connected" else []
print(json.dumps({{"type": "system", "subtype": "init", "model": model, "claude_code_version": "2.1.304",
                  "tools": tools + mcp_tools, "mcp_servers": [{{"name": n, "status": status}} for n in mcp]}}), flush=True)
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "partial answer"}}]}}}}), flush=True)
if mode == "hang":
    time.sleep(60)
if mode in ("midstream_error", "recovered"):
    print(json.dumps({{"type": "assistant", "error": "server_error", "message": {{"content": [{{"type": "text", "text": "API Error: Server error mid-response. The response above may be incomplete."}}]}}}}), flush=True)
if mode == "recovered":
    print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "Use tool Y after retrying."}}]}}}}), flush=True)
if mode == "midstream_error":
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": "", "total_cost_usd": 0.02}}))
    sys.exit(0)
if mode == "api_error":
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "API Error: 529 overloaded", "total_cost_usd": 0.01}}))
    sys.exit(1)
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": "Use tool X.", "total_cost_usd": {cost}, "num_turns": 3}}))
"""


def make_fake(tmp_path: Path, cost: float = 0.1) -> Path:
    fake = tmp_path / "fake_claude"
    fake.write_text(FAKE.format(python=sys.executable, here=str(tmp_path), cost=cost))
    fake.chmod(0o755)
    return fake


def config_for(fake: Path, **overrides) -> dict:
    config = json.loads(run.CONFIG_PATH.read_text())
    config.update({"claude_bin": str(fake), "timeout_s": 5, "per_run_budget_usd": 1.0})
    config.update(overrides)
    return config


QUESTIONS = [{"id": f"q{n:02d}", "prompt": f"need number {n}"} for n in range(1, 5)]


def mode(tmp_path: Path, value: str) -> None:
    (tmp_path / "mode.txt").write_text(value)


def quiet(*_args) -> None:
    pass


def test_run1_order_alternates_and_rules_only_goes_last() -> None:
    assert run.run1_order("q01") == ["control", "experimental", "rules_only"]
    assert run.run1_order("q02") == ["experimental", "control", "rules_only"]
    assert run.run1_order("q19") == ["control", "experimental", "rules_only"]


def test_rerun_order_is_c2_e2_e3_c3() -> None:
    assert run.rerun_order([2, 3]) == [("control", 2), ("experimental", 2), ("experimental", 3), ("control", 3)]
    assert run.rerun_order([2]) == [("control", 2), ("experimental", 2)]


def test_command_gives_only_web_tools_and_pickfit_only_where_due(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    prompt = run.build_prompt(config, {"prompt": "  find me a tool  "})
    assert prompt == config["preamble"] + "\n\nfind me a tool"
    control = run.build_cmd(config, "control", tmp_path / "m.json", prompt)
    experimental = run.build_cmd(config, "experimental", tmp_path / "m.json", prompt)
    assert control[control.index("--tools") + 1] == "WebFetch,WebSearch"
    assert "mcp__pickfit" not in control and "mcp__pickfit" in experimental
    assert "--strict-mcp-config" in control and "--bare" not in control
    assert control[-1] == prompt and control[control.index("--model") + 1] == config["model"]


def test_env_is_isolated(tmp_path: Path) -> None:
    env = run.isolated_env(tmp_path, "k")
    assert set(env) == {"HOME", "PATH", "ANTHROPIC_API_KEY", "DISABLE_AUTOUPDATER", "LANG", "MCP_TIMEOUT"}
    assert env["HOME"] == str(tmp_path) and env["DISABLE_AUTOUPDATER"] == "1"


def test_run1_runs_every_slot_in_order_and_completes(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    assert run.cmd_run1(None, config, QUESTIONS, "k", base, quiet) == 0
    assert (base / "run1-complete.json").exists()
    calls = [json.loads(line) for line in (tmp_path / "calls.log").read_text().splitlines()]
    assert [c["mcp"] for c in calls[:6]] == [[], ["pickfit"], ["pickfit"], ["pickfit"], [], ["pickfit"]]
    meta = json.loads((base / "run1/q01/control/attempt-1/meta.json").read_text())
    assert meta["valid"] and meta["config_problems"] == [] and meta["cost_exact"]
    assert (base / "run1/q01/control/attempt-1/answer.md").read_text() == "Use tool X."
    estimate = json.loads((base / "run1-estimate.json").read_text())
    assert estimate["projected_usd"] == pytest.approx(0.1 * 12)


def test_resume_skips_settled_slots(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    run.cmd_run1(None, config, QUESTIONS, "k", base, quiet)
    before = len((tmp_path / "calls.log").read_text().splitlines())
    run.cmd_run1(None, config, QUESTIONS, "k", base, quiet)
    assert len((tmp_path / "calls.log").read_text().splitlines()) == before


def test_api_error_is_invalid_and_retried_twice_then_not_run(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "api_error")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    metas = run.attempts("run1", "q01", "control", base)
    assert len(metas) == 3 and not any(m["valid"] for m in metas)
    assert metas[0]["invalid_reason"].startswith("api_error")


def test_crash_without_result_is_invalid(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "crash")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    meta = run.attempts("run1", "q01", "control", base)[0]
    assert not meta["valid"] and meta["invalid_reason"].startswith("runner_crash")


def test_timeout_is_valid_and_keeps_the_last_assistant_message(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path), timeout_s=2)
    base = tmp_path / "runs"
    mode(tmp_path, "hang")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    meta = run.attempts("run1", "q01", "control", base)[0]
    assert meta["valid"] and meta["timed_out"] and not meta["cost_exact"]
    assert (base / "run1/q01/control/attempt-1/answer.md").read_text() == "partial answer"


def test_misconfigured_group_stops_the_round(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "wrong_model")
    assert run.cmd_run1(None, config, QUESTIONS, "k", base, quiet) == 1
    assert (base / "run1-control-misconfigured.json").exists()
    assert len((tmp_path / "calls.log").read_text().splitlines()) == 1


def test_projection_over_the_cap_stops_after_the_estimate_questions(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path, cost=0.5), caps_usd={"run1": 5.0, "reruns": 60.0, "grading": 20.0})
    base = tmp_path / "runs"
    questions = [{"id": f"q{n:02d}", "prompt": "p"} for n in range(1, 21)]
    assert run.cmd_run1(None, config, questions, "k", base, quiet) == 1
    assert not (base / "run1/q03").exists()
    stopped = json.loads((base / "run1-stopped.json").read_text())
    assert "9.2" in stopped["reason"]


def test_reruns_plan_and_stop_at_the_deadline(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path, cost=0.1))
    base = tmp_path / "runs"
    run.cmd_run1(None, config, QUESTIONS, "k", base, quiet)
    assert run.plan_reruns(config, base) == [2, 3]
    tight = dict(config, caps_usd={"run1": 30.0, "reruns": 1.0, "grading": 20.0})
    assert run.plan_reruns(tight, base) == [2]
    start = run.first_start(base)
    ticks = iter([start] * 5 + [start + dt.timedelta(hours=25)])  # q01: 4 slot checks and 1 after
    assert run.cmd_reruns(None, config, QUESTIONS, "k", base, lambda: next(ticks), quiet) == 1
    stopped = json.loads((base / "reruns-stopped.json").read_text())
    assert stopped["not_run"] == ["q02"] and "24-hour" in stopped["reason"]
    assert len(run.attempts("run3", "q01", "control", base)) == 1


def test_check_reports_a_wrong_tool_list(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    assert run.cmd_check(argparse.Namespace(round="run1"), config, base, quiet) == 0
    stream = base / "run1/q01/experimental/attempt-1/stream.jsonl"
    lines = stream.read_text().splitlines()
    init = json.loads(lines[0])
    init["tools"] = ["WebFetch", "WebSearch", "Bash"]
    stream.write_text("\n".join([json.dumps(init), *lines[1:]]) + "\n")
    assert run.cmd_check(argparse.Namespace(round="run1"), config, base, quiet) == 1


def test_deadline_passing_during_a_question_makes_that_question_not_run(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path, cost=0.1))
    base = tmp_path / "runs"
    run.cmd_run1(None, config, QUESTIONS, "k", base, quiet)
    start = run.first_start(base)
    ticks = iter([start] * 4 + [start + dt.timedelta(hours=25)])
    assert run.cmd_reruns(None, config, QUESTIONS, "k", base, lambda: next(ticks), quiet) == 1
    assert json.loads((base / "reruns-stopped.json").read_text())["not_run"] == ["q01"]


def test_auth_or_billing_error_stops_everything_and_is_not_a_run(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "auth")
    assert run.cmd_run1(None, config, QUESTIONS, "k", base, quiet) == 1
    metas = run.attempts("run1", "q01", "control", base)
    assert len(metas) == 1 and not metas[0]["valid"] and metas[0]["invalid_reason"].startswith("setup_error")
    assert "setup error" in json.loads((base / "run1-stopped.json").read_text())["reason"]


def test_crash_before_init_is_retried_not_called_misconfigured(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "crash")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    assert len(run.attempts("run1", "q01", "control", base)) == 3
    assert not list(base.glob("*misconfigured.json"))


def test_interrupted_attempt_is_sealed_and_the_next_attempt_runs(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    (base / "run1/q01/control/attempt-1").mkdir(parents=True)
    (base / "run1/q01/control/attempt-1/stream.jsonl").write_text("")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    metas = run.attempts("run1", "q01", "control", base)
    assert [m["valid"] for m in metas] == [False, True]
    assert metas[0]["invalid_reason"].startswith("runner_crash: interrupted")


def test_a_run_that_ends_on_a_server_error_is_invalid_but_a_recovered_one_is_valid(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    mode(tmp_path, "midstream_error")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", tmp_path / "a", quiet)
    assert run.attempts("run1", "q01", "control", tmp_path / "a")[0]["invalid_reason"].startswith("api_error")
    mode(tmp_path, "recovered")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", tmp_path / "b", quiet)
    meta = run.attempts("run1", "q01", "control", tmp_path / "b")[0]
    assert meta["valid"]
    assert (tmp_path / "b/run1/q01/control/attempt-1/answer.md").read_text() == "Use tool X."


def test_pickfit_not_connected_is_a_valid_run_not_a_misconfiguration(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "pending")
    assert run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet) == 0
    meta = run.attempts("run1", "q01", "experimental", base)[0]
    assert meta["valid"] and meta["config_problems"] == [] and meta["pickfit_unavailable"] == ["pickfit: pending"]


def test_void_moves_a_misconfigured_group_aside_and_unblocks_the_round(tmp_path: Path) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    mode(tmp_path, "wrong_model")
    run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet)
    assert run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet) == 2  # blocked until voided
    run.cmd_void(argparse.Namespace(round="run1", group="control"), base, quiet)
    mode(tmp_path, "ok")
    assert run.cmd_run1(None, config, QUESTIONS[:1], "k", base, quiet) == 0
    assert list((base / "voided").glob("run1-control-*/q01/control/attempt-1/meta.json"))


def test_cap_pressure_cuts_rules_only_before_the_primary_groups(tmp_path: Path, monkeypatch) -> None:
    config = config_for(make_fake(tmp_path))
    base = tmp_path / "runs"
    real = run.run_one_slot
    pressure = {"left": 1}

    def slot(config, question, group, *rest, **kw):
        if question["id"] == "q02" and group == "experimental" and pressure["left"]:
            pressure["left"] -= 1
            raise run.OverCap("cap pressure")
        return real(config, question, group, *rest, **kw)

    monkeypatch.setattr(run, "run_one_slot", slot)
    assert run.cmd_run1(None, config, QUESTIONS[:3], "k", base, quiet) == 0
    assert json.loads((base / "run1-rules-only-cut.json").read_text())["from_question"] == "q02"
    assert run.attempts("run1", "q01", "rules_only", base)
    assert not run.attempts("run1", "q02", "rules_only", base) and not run.attempts("run1", "q03", "rules_only", base)
    assert run.attempts("run1", "q02", "experimental", base) and run.attempts("run1", "q03", "control", base)


def test_snapshot_problems_catch_data_the_deployments_do_not_serve() -> None:
    config = json.loads(run.CONFIG_PATH.read_text())
    good = {"git_dirty": [], "claude_code_version": "2.1.304 (Claude Code)", "served_data_sha256": "aa",
            "evidence_manifest_sha256": "ee",
            "deployments": {"experimental": {"matches_expectation": True, "root": {"data_sha256": "aa"}},
                            "rules_only": {"matches_expectation": True, "root": {"data_sha256": "aa"}}}}
    assert run.record_problems(good, config) == []
    bad = json.loads(json.dumps(good))
    bad["deployments"]["rules_only"]["root"]["data_sha256"] = "bb"
    problems = run.record_problems(bad, config)
    assert any("serves data bb" in p for p in problems) and any("different data" in p for p in problems)


def test_served_digest_matches_the_index_formula(tmp_path: Path) -> None:
    import hashlib
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text('{"x": 1}')
    expected = hashlib.sha256(b"a.json\0" + b'{"x": 1}' + b"\0" + b"b.json\0" + b"{}" + b"\0").hexdigest()
    assert run.served_data_sha256(tmp_path) == expected


def test_compare_lists_what_changed() -> None:
    before = {"git_head": "1", "model": "m", "deployments": {"experimental": {"root": {"data_sha256": "aa"}, "latest_deployment": {"id": "v1"}}}}
    after = {"git_head": "2", "model": "m", "deployments": {"experimental": {"root": {"data_sha256": "aa"}, "latest_deployment": {"id": "v2"}}}}
    assert run.compare_records(before, after) == ["git_head: 1 -> 2", "experimental.deployment: v1 -> v2"]
