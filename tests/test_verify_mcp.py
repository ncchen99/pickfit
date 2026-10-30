"""MCP servers in verification: probe helpers, the verdict's MCP rules, the replay and the run record."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import TAIPEI
from pickfit.schema import SoftwareRecord, VerificationRun
from pickfit.verify.agent import CommandRecord, FinishArgs, VerifyReport
from pickfit.verify.judge import JudgeResult
from pickfit.verify.mcp import (
    MARKER,
    PROBE_COMMAND,
    credentials,
    handshake,
    is_mcp,
    launch_argv,
    pitfalls,
    probe_kind,
)
from pickfit.verify.replay import CheckResult, RanCommand, ReplayResult
from pickfit.verify.result import build_run, install_guide
from pickfit.verify.task import VerifyTask
from pickfit.verify.verdict import check_kind, log_verdict, supported_level

PROBE = f"{PROBE_COMMAND} -- notes-mcp --root ~/work"
CALL = f"{PROBE_COMMAND} --call search_notes --args '{{\"q\": \"x\"}}' -- notes-mcp --root ~/work"


def summary(ok: bool = True, **extra: Any) -> str:
    data = {"probe": 1, "ok": ok, "launch": ["notes-mcp", "--root", "/home/sbx/work"], "protocol": "2025-06-18",
            "server": "notes", "version": "0.3.1", "tools": ["search_notes", "read_note"], "count": 2,
            "flags": {}, "noise": 0, **extra}
    lines = ["initialize: ok protocol=2025-06-18 server=notes version=0.3.1", "tools/list: ok count=2",
             "tool: search_notes args=q*", "tool: read_note args=path*"]
    if extra.get("called"):
        lines.append("tools/call: ok tool=search_notes content=text text_chars=12")
    if ok:
        lines.append("handshake: ok" + (", tool call ok" if extra.get("called") else ""))
    return "\n".join([*lines, MARKER + json.dumps(data)]) + "\n"


def rec(cid: int, command: str, code: int, out: str = "") -> CommandRecord:
    return CommandRecord(turn=cid, tool="run_command", command=command, exit_code=code, seconds=0.5, stdout=out,
                         command_id=cid)


def claim(level: str, steps: list[int], tests: list[dict[str, Any]], **extra: Any) -> FinishArgs:
    return FinishArgs.model_validate({
        "level": level, "steps": [{"command_id": s, "purpose": "install"} for s in steps],
        "smoke_tests": [{"setup_ids": [], "expected_exit_code": 0, "observed_excerpt": "", **t} for t in tests],
        **extra})


LOG = [
    rec(1, "npm install -g notes-mcp", 0, "added 12 packages"),
    rec(2, "notes-mcp --help", 0, "Usage: notes-mcp --root DIR"),
    rec(3, PROBE, 0, summary()),
    rec(4, CALL, 0, summary(called="search_notes")),
]


# ---------------------------------------------------------------- helpers


def test_probe_commands_and_launch_argv() -> None:
    assert probe_kind(PROBE) == "mcp" and probe_kind(CALL) == "mcp_call"
    assert probe_kind("cd repo && python3 /home/sbx/.pickfit/mcp_probe.py -- node dist/index.js") == "mcp"
    assert probe_kind("cat mcp_probe.py") is None and probe_kind("notes-mcp --help") is None
    assert check_kind(f"cd repo && {PROBE}") == "mcp" and check_kind(CALL) == "mcp_call"
    assert launch_argv(PROBE) == ["notes-mcp", "--root", "~/work"]
    assert launch_argv(CALL) == ["notes-mcp", "--root", "~/work"]
    assert launch_argv(f"{PROBE_COMMAND} --timeout 5") is None


@pytest.mark.parametrize(("command", "names"), [
    ("GITHUB_TOKEN=dummy " + PROBE, ["GITHUB_TOKEN"]),
    ("export OPENAI_API_KEY=sk-x && notes-mcp", ["OPENAI_API_KEY"]),
    ("echo NOTION_SECRET=abc > .env", ["NOTION_SECRET"]),
    ("MAX_TOKENS=16 notes-mcp", []),
    ("NOTES_ROOT=~/work " + PROBE, []),
    ("GITHUB_TOKEN= notes-mcp", []),
    (PROBE_COMMAND + " -- notes-mcp --api-key sk-test", ["--api-key"]),
    (PROBE_COMMAND + " -- notes-mcp --token=abc", ["--token"]),
    ("notes-mcp --max-tokens 16 --tokenizer x", []),
])
def test_credentials(command: str, names: list[str]) -> None:
    assert credentials(command) == names


def test_handshake_and_notes_from_the_probe_output() -> None:
    seen = handshake(summary(called="search_notes"), CALL, offline=True)
    assert seen is not None and seen.tools == ["search_notes", "read_note"] and seen.tool_count == 2
    assert seen.launch == ["notes-mcp", "--root", "~/work"] and seen.called_tool == "search_notes"
    assert seen.server_name == "notes" and seen.protocol_version == "2025-06-18" and seen.offline is True
    assert handshake(summary(ok=False), PROBE, offline=None) is None
    assert handshake("handshake: ok\n", PROBE, offline=None) is None  # no summary line: not the probe's output
    notes = pitfalls(summary(flags={"add": ["instruction_tag", "sensitive_files"]}, noise=2))
    assert [p.kind for p in notes] == ["note", "note"]
    assert "Tool add's description has instruction-like text" in notes[0].actually_needed
    assert "<IMPORTANT>-style tag" in notes[0].actually_needed and "2 other line(s)" in notes[1].actually_needed
    server = pitfalls(summary(flags={"(server instructions)": ["override"]}))
    assert server[0].actually_needed.startswith("The server's instructions have instruction-like text")


def test_is_mcp_prefers_the_record_category() -> None:
    task = VerifyTask(slug="x", repo_url="https://github.com/a/x", readme="", extraction=None, category="mcp_server")
    assert is_mcp(task)
    assert not is_mcp(VerifyTask(slug="x", repo_url="https://github.com/a/x", readme="", extraction=None))


# ---------------------------------------------------------------- verdict


def test_mcp_levels_come_from_the_probe_only() -> None:
    handshake_only = claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}])
    assert log_verdict(handshake_only, LOG, mcp=True).level == "function"
    with_call = claim("service", [1], [{"command_id": 3, "expected_signal": "handshake: ok"},
                                       {"command_id": 4, "expected_signal": "tools/call: ok"}])
    assert log_verdict(with_call, LOG, mcp=True).level == "service"
    # --help alone does not pass an MCP server, though it would pass a CLI tool at install.
    help_only = claim("install", [1], [{"command_id": 2, "expected_signal": "Usage"}])
    assert log_verdict(help_only, LOG).level == "install"
    verdict = log_verdict(help_only, LOG, mcp=True)
    assert verdict.level == "unverified" and verdict.unverified_reason == "other"
    assert any("probe completes the handshake" in p for p in verdict.problems)
    # A claim above what the probe shows is lowered.
    assert log_verdict(claim("service", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}]), LOG,
                       mcp=True).level == "function"


def test_a_probe_check_needs_the_probes_own_summary() -> None:
    faked = [*LOG[:2], rec(3, PROBE, 0, "handshake: ok\n")]  # the signal, but no summary line
    verdict = log_verdict(claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}]), faked,
                          mcp=True)
    assert verdict.level == "unverified" and not verdict.checks[0].passed
    broken = [*LOG[:2], rec(3, PROBE, 0, summary(ok=False, error="tools/list returned no tools"))]
    verdict = log_verdict(claim("function", [1], [{"command_id": 3, "expected_signal": "initialize: ok"}]), broken,
                          mcp=True)
    assert verdict.level == "unverified" and "did not complete" in " ".join(verdict.checks[0].problems)


def test_placeholder_credentials_never_count() -> None:
    log = [*LOG[:2], rec(3, "GITHUB_TOKEN=dummy " + PROBE, 0, summary())]
    verdict = log_verdict(claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}]), log,
                          mcp=True)
    assert verdict.level == "unverified"
    assert "placeholder credentials" in " ".join(verdict.checks[0].problems)
    log = [*LOG[:3], rec(5, "echo API_KEY=x > ~/work/.env", 0)]
    verdict = log_verdict(claim("function", [1, 5], [{"command_id": 3, "expected_signal": "handshake: ok"}]), log,
                          mcp=True)
    assert verdict.level == "unverified" and any("step 5 sets API_KEY" in p for p in verdict.problems)
    # Only an MCP server's verification checks for them.
    assert log_verdict(claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}]),
                       [*LOG[:2], rec(3, "GITHUB_TOKEN=dummy " + PROBE, 0, summary())]).level == "function"


def test_unverified_needs_account_stands() -> None:
    log = [LOG[0], rec(2, PROBE, 2, MARKER + json.dumps({"probe": 1, "ok": False, "error": "closed stdout"}))]
    verdict = log_verdict(claim("unverified", [1], [], unverified_reason="needs_account"), log, mcp=True)
    assert verdict.level == "unverified" and verdict.unverified_reason == "needs_account"


def test_supported_level_for_mcp() -> None:
    from pickfit.verify.verdict import ResolvedCheck

    def check(kind: str, passed: bool = True) -> ResolvedCheck:
        return ResolvedCheck(command_id=1, command="x", tool="run_command", setup_ids=[], expected_signal="",
                             expected_exit_code=0, exit_code=0, passed=passed, kind=kind)

    assert supported_level(True, [check("mcp")], False, mcp=True) == "function"
    assert supported_level(True, [check("mcp"), check("mcp_call")], True, mcp=True) == "service"
    assert supported_level(True, [check("example")], True, mcp=True) is None
    assert supported_level(True, [check("mcp_call", passed=False), check("mcp")], False, mcp=True) == "function"


# ---------------------------------------------------------------- run record


def report(finish: FinishArgs, verdict_mcp: bool = True) -> VerifyReport:
    verdict = log_verdict(finish, LOG, mcp=verdict_mcp)
    return VerifyReport(run_id="verify-notes-mcp-20261031-010000-abcd", slug="notes-mcp",
                        repo_url="https://github.com/a/notes-mcp", model="muse-spark-1.3", mode="replay",
                        started_at="2026-10-31T01:00:00+08:00", box={"runner": "modal-gvisor", "image": "im",
                                                                     "os": "linux", "arch": "x86_64"},
                        commands=list(LOG), finish=finish.model_dump(), verdict=verdict.to_dict(),
                        stop_reason="finished", cost_usd=0.05)


def ran(cid: int, command: str, out: str, network: bool) -> RanCommand:
    return RanCommand(cid, command, 0, 0.4, False, out, "", network)


def replay(*checks: CheckResult) -> ReplayResult:
    return ReplayResult(passed=True, level="service" if any(c.kind == "mcp_call" for c in checks) else "function",
                        offline=all(c.offline for c in checks),
                        steps=[ran(1, "npm install -g notes-mcp", "added 12 packages", True)], checks=list(checks))


def judge() -> JudgeResult:
    return JudgeResult(verdict="working", observed="handshake ok, two tools", error_text=None,
                       matches_expected_signal=True, model="muse-spark-1.3")


def test_a_passed_mcp_run_carries_the_replays_handshake(tmp_path: Path) -> None:
    finish = claim("service", [1], [{"command_id": 3, "expected_signal": "handshake: ok"},
                                    {"command_id": 4, "expected_signal": "tools/call: ok"}])
    checks = (CheckResult(3, PROBE, "mcp", 0, "handshake: ok", passed=True, offline=True,
                          run=ran(3, PROBE, summary(flags={"read_note": ["override"]}), False)),
              CheckResult(4, CALL, "mcp_call", 0, "tools/call: ok", passed=True, offline=False,
                          run=ran(4, CALL, summary(called="search_notes"), True)))
    run, notes = build_run(report(finish), replay(*checks), judge(), evidence_dir=tmp_path, mcp=True,
                           checked_at=datetime(2026, 10, 31, 1, 5, tzinfo=TAIPEI))
    assert run.level == "service" and run.replayed
    assert run.mcp is not None and run.mcp.called_tool == "search_notes" and run.mcp.offline is True
    assert run.mcp.tools == ["search_notes", "read_note"]
    assert [p.kind for p in run.pitfalls] == []  # flags come from the probe check that decided the handshake
    # Users have no probe: the guide's check and first task are never probe commands.
    guide = install_guide(run)
    assert guide.check is None and guide.first_task is None and guide.steps[0].command == "npm install -g notes-mcp"


def test_the_handshake_check_also_brings_its_notes(tmp_path: Path) -> None:
    finish = claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}])
    check = CheckResult(3, PROBE, "mcp", 0, "handshake: ok", passed=True, offline=True,
                        run=ran(3, PROBE, summary(flags={"read_note": ["override"]}, noise=1), False))
    run, _ = build_run(report(finish), replay(check), judge(), evidence_dir=tmp_path, mcp=True)
    assert run.level == "function" and run.mcp.called_tool is None
    assert [p.kind for p in run.pitfalls] == ["note", "note"]
    assert "Tool read_note's description" in run.pitfalls[0].actually_needed


def test_no_handshake_in_the_replay_is_unverified(tmp_path: Path) -> None:
    finish = claim("function", [1], [{"command_id": 3, "expected_signal": "handshake: ok"}])
    check = CheckResult(3, PROBE, "mcp", 0, "handshake: ok", passed=True, offline=True,
                        run=ran(3, PROBE, "handshake: ok\n", False))
    run, notes = build_run(report(finish), replay(check), judge(), evidence_dir=tmp_path, mcp=True)
    assert run.level == "unverified" and run.unverified_reason == "other" and run.mcp is None
    assert "no completed MCP handshake in the replay" in notes


def test_records_check_the_handshake() -> None:
    base = json.loads((Path(__file__).parent / "fixtures" / "record_mcp.json").read_text(encoding="utf-8"))
    record = SoftwareRecord.model_validate(base)
    assert record.mcp is not None and record.verification.runs[0].mcp is not None
    run = base["verification"]["runs"][0]
    without = {**base, "verification": {**base["verification"], "runs": [{k: v for k, v in run.items() if k != "mcp"}]}}
    with pytest.raises(ValueError, match="needs its handshake"):
        SoftwareRecord.model_validate(without)
    with pytest.raises(ValueError, match="category mcp_server only"):
        SoftwareRecord.model_validate({**without, "category": "dev_cli",
                                       "verification": {**base["verification"], "runs": [], "level": "unverified",
                                                        "unverified_reason": "not_run", "checked_at": None},
                                       "install": {}})
    service = {**run, "level": "service", "mcp": {**run["mcp"], "called_tool": None}}
    with pytest.raises(ValueError, match="needs a tool call"):
        VerificationRun.model_validate(service)


# ---------------------------------------------------------------- agent


def test_the_agent_gets_the_probe_the_guide_and_its_level_from_the_probe(tmp_path: Path, monkeypatch) -> None:
    import pickfit.env
    from pickfit import meta
    from pickfit.ledger import Caps, Ledger
    from pickfit.schema import ExtractionResult
    from pickfit.verify.agent import VerifyAgent
    from tests.test_profiles import MCP_README, mcp_extraction
    from verify_fakes import FakeBox, FakeServer, finish, response, run_cmd

    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)
    ex = ExtractionResult.model_validate(mcp_extraction())
    task = VerifyTask(slug="notes-mcp", repo_url="https://github.com/someone/notes-mcp", readme=MCP_README,
                      extraction=ex)
    server = FakeServer(
        response("r1", run_cmd("npm install -g notes-mcp")),
        response("r2", run_cmd(PROBE)),
        response("r3", finish(level="function", steps=[1], install_method="npm",
                              smoke=[{"command_id": 2, "setup_ids": [], "expected_signal": "handshake: ok",
                                      "expected_exit_code": 0, "observed_excerpt": "handshake: ok"}])),
    )
    box = FakeBox({"npm install": (0, "added 12 packages", ""), "mcp_probe.py": (0, summary(), "")})
    ledger = Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    agent = VerifyAgent(task, box, client=server.client(), ledger=ledger, runs_dir=tmp_path / "runs",
                        log=lambda line: None, run_id="verify-notes-mcp-test")
    report = agent.run()
    assert report.verdict["level"] == "function" and report.verdict["agrees"]
    assert box.files["/home/sbx/.pickfit/mcp_probe.py"].startswith(b"#!/usr/bin/env python3")
    first = server.requests[0]["input"][0]["content"]
    assert "This is an MCP (Model Context Protocol) server." in first
    assert "Launch command the README gives: notes-mcp --root ~/notes" in first
    assert "Environment variables the README names: NOTES_ROOT" in first
    assert "Tiny models for the inference check" not in first


def test_http_only_mcp_servers_are_set_aside() -> None:
    from pickfit.schema import ExtractionResult
    from pickfit.verify.batch import not_in_box
    from tests.test_profiles import mcp_extraction

    http = ExtractionResult.model_validate(mcp_extraction(transports={"value": ["streamable_http"],
                                                                      "quote": "Transport: stdio."}))
    assert not_in_box(http) == "MCP over HTTP only (the probe speaks stdio)"
    assert not_in_box(ExtractionResult.model_validate(mcp_extraction())) is None
