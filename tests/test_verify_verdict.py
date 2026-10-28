"""The verdict comes from the command log: masked exit codes, cited ids, supported levels."""

from __future__ import annotations

from typing import Any

import pytest

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.verdict import check_kind, log_verdict, masked_exit


@pytest.mark.parametrize("command", [
    "pipx install evnx",
    "evnx sync && evnx validate",
    "echo '{\"a\": 1}' | tinyq .a",
    "cd sub; graphtty graph.json",
    "graphtty graph.json 2>&1",
    "llama-server -m m.gguf &> server.log && curl -s localhost:8080/health",
    "echo 'a || b; echo $?' > notes.txt && cat notes.txt | wc -l > n && tool n",
    "cat > graph.json <<'EOF'\n{\"nodes\": [\"a\"]; \"x\": 1 || 2}\nEOF\ngraphtty graph.json",
    "python3 -c 'import sys; sys.exit(0)' && tool --help",
    "tool --format=\"a|b\" input.txt",
])
def test_honest_commands_are_not_masked(command: str):
    assert masked_exit(command) is None


@pytest.mark.parametrize(("command", "why"), [
    ("pipx install evnx || true", "`||`"),
    ("evnx validate; echo $?", "`echo`"),
    ("evnx validate; echo exit=$?", "`echo`"),
    ("tool --help | head -20", "`head`"),
    ("pip install x 2>&1 | tail -5", "`tail`"),
    ("tool --version | grep 1.2", "`grep`"),
    ("tool run &", "background"),
    ("tool check\nexit 0", "`exit`"),
    ("if tool --version; then echo ok; fi", "`if`"),
    ("! tool --broken", "`!`"),
    ("set +e; tool x", "`set +e`"),
    ("tool x || :", "`||`"),
    ("cat > in.txt <<EOF\nhello\nEOF\ntool in.txt; true", "`true`"),
])
def test_masked_exit_codes_are_caught(command: str, why: str):
    reason = masked_exit(command)
    assert reason is not None and why in reason


def test_check_kind():
    assert check_kind("evnx --version") == "version"
    assert check_kind("pipx install x && x --help") == "version"
    assert check_kind("graphtty graph.json") == "example"
    assert check_kind("curl -s localhost:8080/v1/completions -d '{}'") == "generation"
    assert check_kind("curl -s http://127.0.0.1:11434/api/generate -d @req.json") == "generation"


# ---------------------------------------------------------------- log_verdict


def rec(cid: int, command: str, code: int, out: str = "", err: str = "", tool: str = "run_command",
        timed_out: bool = False) -> CommandRecord:
    return CommandRecord(turn=cid, tool=tool, command=command, exit_code=code, seconds=0.1, stdout=out,
                         stderr=err, timed_out=timed_out, command_id=cid)


def claim(level: str, steps: list[int], tests: list[dict[str, Any]], **extra: Any) -> FinishArgs:
    return FinishArgs.model_validate({
        "level": level, "steps": [{"command_id": s, "purpose": "install"} for s in steps],
        "smoke_tests": [{"setup_ids": [], "expected_signal": "", "expected_exit_code": 0,
                         "observed_excerpt": "", **t} for t in tests], **extra})


LOG = [
    rec(1, "pipx install evnx", 0, "installed package evnx 0.10.18"),
    rec(2, "evnx --version", 0, "evnx 0.10.18"),
    rec(3, "evnx validate", 2, "", "Error: .env.example does not exist."),
    rec(4, "evnx sync", 0, "wrote .env.example"),
    rec(5, "evnx validate", 1, "SECRET_KEY looks like a placeholder"),
]


def test_function_needs_a_readme_example_from_the_log():
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 2, "expected_signal": "0.10.18"},
        {"command_id": 5, "setup_ids": [4], "expected_signal": "SECRET_KEY", "expected_exit_code": 1}]), LOG)
    assert verdict.level == "function" and verdict.agrees
    assert [c.passed for c in verdict.checks] == [True, True]
    assert [c.kind for c in verdict.checks] == ["version", "example"]
    assert verdict.checks[1].observed_excerpt == "SECRET_KEY looks like a placeholder"


def test_claimed_exit_code_is_checked_against_the_log():
    # The model says the failing validate (exit 2) was the passing example.
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 2, "expected_signal": "0.10.18"},
        {"command_id": 3, "expected_signal": "Error", "expected_exit_code": 1}]), LOG)
    assert verdict.level == "install"
    assert "smoke test 3: expected exit 1, log shows 2" in verdict.problems


def test_a_version_check_alone_supports_install():
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "0.10.18"}]), LOG)
    assert verdict.level == "install" and not verdict.agrees and verdict.problems == []


def test_masked_step_or_check_is_not_counted():
    log = [rec(1, "pipx install nothere || true", 0, "No matching distribution"),
           rec(2, "nothere --help | head -5", 0, "usage: nothere")]
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "usage"}]), log)
    assert verdict.level == "unverified" and verdict.unverified_reason == "other"
    assert any("step 1 does not show a success (`||`" in p for p in verdict.problems)
    assert any("exit code masked" in p for p in verdict.problems)


def test_signal_must_be_in_the_output_and_crashes_fail():
    log = [rec(1, "uv tool install x", 0, "Installed 1 executable: x"),
           rec(2, "x demo.txt", 0, "Traceback (most recent call last):\n  ...\nKeyError: 'a'"),
           rec(3, "x --version", 0, "x 1.0")]
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "rendered"},
                                                  {"command_id": 3, "expected_signal": "1.0"}]), log)
    problems = verdict.checks[0].problems
    assert "expected_signal not in the output: 'rendered'" in problems
    assert any("crash" in p for p in problems)
    assert verdict.level == "install"


def test_non_zero_exit_needs_a_signal_and_setup_must_come_first():
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 5, "setup_ids": [4], "expected_exit_code": 1},
        {"command_id": 2, "setup_ids": [5], "expected_signal": "0.10.18"}]), LOG)
    assert "a non-zero expected exit needs an expected_signal" in verdict.checks[0].problems
    assert "setup 5 is not a command that ran before it" in verdict.checks[1].problems
    assert verdict.level == "unverified"


def test_unknown_ids_and_no_checks():
    verdict = log_verdict(claim("install", [9], [{"command_id": 8}]), LOG)
    assert verdict.level == "unverified"
    assert verdict.problems == ["step cites no run_command with id 9", "smoke test cites no command with id 8"]
    verdict = log_verdict(claim("install", [1], []), LOG)
    assert verdict.level == "unverified" and verdict.problems == ["no passing check in the log"]


def test_service_and_inference_need_a_background_server():
    log = [rec(1, "curl -L -o llama.tgz https://example.invalid/llama.tgz && tar xzf llama.tgz", 0, ""),
           rec(2, "./llama-server -m m.gguf --port 8080", 0, "pid 7\nport 8080 open after 2s",
               tool="run_background"),
           rec(3, "curl -s localhost:8080/health", 0, '{"status":"ok"}'),
           rec(4, "curl -s localhost:8080/v1/completions -d '{\"prompt\":\"Hi\"}'", 0,
               '{"choices":[{"text":" there"}],"usage":{"completion_tokens":4}}')]
    tests = [{"command_id": 3, "setup_ids": [2], "expected_signal": '"status":"ok"'},
             {"command_id": 4, "setup_ids": [2], "expected_signal": "completion_tokens"}]
    assert log_verdict(claim("inference", [1], tests), log).level == "inference"
    assert log_verdict(claim("inference", [1], tests[:1]), log).level == "service"
    # Without the server as setup, a curl is only an example.
    alone = [{**t, "setup_ids": []} for t in tests]
    assert log_verdict(claim("inference", [1], alone), log).level == "function"


def test_failed_and_unverified_claims_stand():
    verdict = log_verdict(claim("failed", [], [], blocking_error="no wheel for this platform"), LOG)
    assert verdict.level == "failed" and verdict.agrees
    verdict = log_verdict(claim("unverified", [], [], unverified_reason="needs_gpu"), LOG)
    assert (verdict.level, verdict.unverified_reason) == ("unverified", "needs_gpu")
