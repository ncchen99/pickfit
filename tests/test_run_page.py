"""scripts/run_page.py: one verification run -> one self-contained HTML page; no network."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from scripts.run_page import main, tail

RUN = "verify-tinyq-20261029-010000-abcd"


def write_run(runs: Path, *, judge: bool = True) -> Path:
    run_dir = runs / "verify" / RUN
    run_dir.mkdir(parents=True)
    report = {
        "run_id": RUN, "slug": "tinyq", "repo_url": "https://github.com/someone/tinyq", "model": "muse-spark-1.3",
        "started_at": "2026-10-29T01:00:00+08:00", "seconds": 20.0,
        "box": {"runner": "modal-gvisor", "image": "pickfit-sbx:x", "os": "linux", "arch": "x86_64"},
        "plan": {"candidates": [{"rank": 1, "method": "cargo", "command": "cargo install tinyq", "origin": "readme"}]},
        "turns": [
            {"turn": 1, "model": "muse-spark-1.3", "latency_s": 1.5, "cost_usd": 0.004,
             "usage": {"input_tokens": 4000, "cached_tokens": 0, "output_tokens": 90, "reasoning_tokens": 20},
             "reasoning_summary": "Trying the README's install.", "text": None,
             "tool_calls": [{"name": "run_command", "arguments": "{}"}]},
            {"turn": 2, "model": "muse-spark-1.3", "latency_s": 2.0, "cost_usd": 0.003, "usage": {},
             "text": "Done.", "tool_calls": [{"name": "finish", "arguments": json.dumps({
                 "level": "function", "install_method": "cargo", "steps": [{"command_id": 1}],
                 "smoke_tests": [{"command_id": 2}],
                 "pitfalls": [{"readme_said": "tinyq -v", "actually_needed": "tinyq --version"}]})}]},
        ],
        "commands": [
            {"turn": 1, "tool": "run_command", "command": "tinyq -v", "exit_code": 2, "seconds": 0.4,
             "stdout": "", "stderr": "error: <script>alert(1)</script> unknown flag",
             "hints": [{"rule": "flag_unsupported", "hint": "Try --help.", "suggested_command": None}],
             "purpose": "check version", "command_id": 1},
            {"turn": 1, "tool": "run_command", "command": "tinyq --version", "exit_code": 0, "seconds": 0.3,
             "stdout": "tinyq 0.1.0\n", "stderr": "", "hints": [], "purpose": None, "command_id": 2},
        ],
        "verdict": {"claimed_level": "function", "level": "function", "checks": [
            {"command": "tinyq --version", "kind": "version", "exit_code": 0, "expected_exit_code": 0,
             "expected_signal": "0.1.0", "passed": True, "problems": []}]},
    }
    (run_dir / "report.json").write_text(json.dumps(report))
    (run_dir / "outcome.json").write_text(json.dumps({
        "level": "function", "replayed": True, "judge": "working", "seconds": 30.0, "cost_usd": 0.009,
        "box_usd": 0.002, "offline": True, "written": True,
        "phases": {"agent_box_start": 3, "agent": 15, "replay_box_start": 3, "replay": 5, "judge": 4}}))
    (run_dir / "replay.json").write_text(json.dumps({"result": {
        "passed": True, "level": "function", "offline": True,
        "steps": [{"command": "cargo install tinyq", "exit_code": 0, "seconds": 9.0, "network": True}],
        "checks": [{"command": "tinyq --version", "expected_exit_code": 0, "passed": True, "offline": True,
                    "run": {"command": "tinyq --version", "exit_code": 0, "seconds": 0.2}}]}}))
    (run_dir / "verification_run.json").write_text(json.dumps({
        "level": "function", "install_method": "cargo", "tool_version": "0.1.0", "runner": "modal-gvisor",
        "os": "linux", "arch": "x86_64", "steps": [{"command": "cargo install tinyq"}],
        "smoke_tests": [{"command": "tinyq --version", "expected_signal": "0.1.0", "passed": True, "offline": True}],
        "pitfalls": [{"readme_said": "tinyq -v", "actually_needed": "tinyq --version"}]}))
    if judge:
        Image.new("RGB", (40, 30), "black").save(run_dir / "check-1-cmd2.png")
        (run_dir / "judge.json").write_text(json.dumps({
            "verdict": "working", "observed": "Version printed.", "model": "muse-spark-1.3", "cost_usd": 0.002,
            "latency_s": 3.0, "screenshots": ["/elsewhere/runs/verify/x/check-1-cmd2.png"],
            "regions": [{"image": 1, "label": "version line", "box": [30, 100, 530, 300], "text": "tinyq 0.1.0"}],
            "problems": []}))
    traces = runs / "traces"
    traces.mkdir()
    lines = [{"ts": "2026-10-29T01:00:01+08:00", "run_id": RUN, "stage": "verify", "model": "muse-spark-1.3",
              "status": "ok", "latency_s": 1.5, "cost_usd": 0.004,
              "usage": {"input_tokens": 4000, "cached_tokens": 3000, "output_tokens": 90, "reasoning_tokens": 20}},
             {"ts": "2026-10-29T01:00:09+08:00", "run_id": RUN, "stage": "verify-judge", "model": "muse-spark-1.3",
              "status": "ok", "latency_s": 3.0, "cost_usd": 0.002,
              "usage": {"input_tokens": 1000, "cached_tokens": 0, "output_tokens": 200, "reasoning_tokens": 100}},
             {"ts": "2026-10-29T01:00:10+08:00", "run_id": "verify-other", "stage": "verify", "cost_usd": 9.0}]
    (traces / "2026-10-29.jsonl").write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return run_dir


def test_page_walks_through_agent_replay_judge_and_calls(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_run(runs)
    assert main([RUN, "--runs", str(runs)]) == 0
    page = (runs / "pages" / f"{RUN}.html").read_text()
    assert "Fails: Check version" in page and "exit 2" in page and "rule · flag_unsupported" in page
    assert "&lt;script&gt;alert(1)" in page and "<script>alert(1)" not in page
    assert "Trying the README&#x27;s install." in page and "claimed level" in page
    assert "{table}" not in page and "<td>tinyq -v</td><td>tinyq --version</td>" in page
    assert "Replay in a fresh box, network off" in page and "works offline" in page
    assert 'class="ebox" style="left:3.0%;top:10.0%;width:50.0%;height:20.0%"' in page
    assert "data:image/png;base64," in page  # the screenshot is inlined from the run directory
    assert "$0.0060" in page and "prompt cache hit 60%" in page  # only this run's two traced calls
    assert "tinyq -v" in page and "tinyq --version" in page and "<title>pickfit run · tinyq</title>" in page


def test_page_without_judge_or_traces_still_renders(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    run_dir = write_run(runs, judge=False)
    (runs / "traces" / "2026-10-29.jsonl").unlink()
    out = tmp_path / "page.html"
    assert main([RUN, "--runs", str(runs), "--out", str(out)]) == 0
    page = out.read_text()
    assert "A second model judges" not in page and "Every Meta model call" not in page
    assert "$0.0090" in page  # falls back to outcome.json's cost
    assert run_dir.exists()


def test_tail_keeps_the_end_and_strips_ansi() -> None:
    text = "\n".join(f"\x1b[31mline {i}\x1b[0m" for i in range(100))
    out = tail(text, lines=3)
    assert out.startswith("…\n") and out.endswith("line 99") and "\x1b" not in out
