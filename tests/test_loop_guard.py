"""scripts/loop_guard.py: what a loop session is refused, and what it must still be able to do."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "loop_guard", Path(__file__).resolve().parent.parent / "scripts" / "loop_guard.py")
loop_guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(loop_guard)

ROOT = str(loop_guard.ROOT)


def bash(command: str) -> str | None:
    return loop_guard.decide({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ROOT})


def file(tool: str, path: str) -> str | None:
    return loop_guard.decide({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": ROOT})


@pytest.mark.parametrize("command", [
    "git push origin loop/20261116",
    "git -C . push",
    "uv run pickfit publish",
    "uv run pickfit watch --once --publish",
    "cd worker && npx wrangler deploy",
    "gh pr merge 12 --squash",
])
def test_going_outside_is_refused(command):
    assert bash(command)


@pytest.mark.parametrize("command", [
    "sed -i '' 's/0.8/0.5/' pickfit/verify/judge.py",
    "echo 'x = 1' >> pickfit/verify/verdict.py",
    "git checkout main -- pickfit/verify/failure.py",
    "python3 -c \"open('pickfit/score.py', 'w').write('')\"",
    "cp /tmp/record.json data/software/ferro.json",
    "cp runs/loop/draft/judge.py pickfit/verify/judge.py",
    "jq '.verification.level = \"function\"' x.json > data/software/ferro.json",
    "rm tests/test_verdict.py",
    "git rm -q tests/test_limits.py",
    "cat .env",
    "cat .env.example 2>/dev/null || true",
    "grep -r needle eval/",
    "set -a; . ./.env; set +a; uv run pickfit ping",
])
def test_loosening_the_checks_or_reading_what_is_off_limits_is_refused(command):
    assert bash(command)


@pytest.mark.parametrize("command", [
    "uv run pytest -q tests/test_verdict.py 2>&1 | tail -5",
    "uv run pickfit verify --batch 1 --records --repo owner/name --runner modal --write-back",
    "uv run python scripts/guarded_write_back.py runs/verify/ferro-20261116-010203",
    "uv run pickfit verify --limits-test --runner modal",
    "grep -n 'def judge' pickfit/verify/judge.py",
    "git add data/software/ferro.json loop/ && git commit -m 'ferro: function'",
    "git diff --stat main -- pickfit/verify/limits.py",
    "uv run python scripts/loop_state.py finish reverify:ferro --result verified",
    "sed -i '' 's/a/b/' pickfit/verify/gui_operate.py",
    "rm -rf runs/verify/tmp-box && ls tests/",
    "echo done > loop/proposals/H-003.patch",
    "cp runs/verify/a/report.json /tmp/report.json && grep -c judge pickfit/verify/judge.py",
    "mkdir -p runs/loop/draft && cp pickfit/verify/judge.py runs/loop/draft/judge.py",
    "diff -u pickfit/verify/judge.py runs/loop/draft/judge.py > loop/proposals/H-007.patch",
    "git commit -m 'gui: push the scroll through the guest agent'",
])
def test_the_loop_s_own_work_is_let_through(command):
    assert bash(command) is None


def test_edits_to_what_decides_a_verdict_are_refused_and_reads_are_not():
    assert file("Edit", f"{ROOT}/pickfit/verify/verdict.py")
    assert file("Write", "pickfit/schema.py")
    assert file("Write", f"{ROOT}/schema/software.v1.json")
    assert file("Edit", f"{ROOT}/scripts/loop_guard.py")
    assert file("Edit", f"{ROOT}/.claude/settings.local.json")
    assert file("Read", f"{ROOT}/pickfit/verify/verdict.py") is None


def test_records_are_never_edited_by_hand():
    assert "write-back" in file("Edit", f"{ROOT}/data/software/ferro.json")
    assert file("Read", f"{ROOT}/data/software/ferro.json") is None


def test_eval_and_env_are_not_read():
    assert file("Read", f"{ROOT}/eval/questions.yaml")
    assert file("Read", f"{ROOT}/.env")
    assert loop_guard.decide({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": "eval"}, "cwd": ROOT})


def test_the_harness_itself_and_new_tests_stay_editable():
    assert file("Edit", f"{ROOT}/pickfit/verify/gui_operate.py") is None
    assert file("Edit", f"{ROOT}/pickfit/verify/modal_box.py") is None
    assert file("Write", f"{ROOT}/tests/test_new_regression.py") is None
    assert file("Edit", f"{ROOT}/loop/issues.md") is None
    assert file("Write", f"{ROOT}/loop/proposals/H-003.patch") is None
    assert file("Write", "/tmp/somewhere/else.py") is None


def test_the_main_checkout_s_copies_are_protected_from_a_worktree(monkeypatch):
    monkeypatch.setattr(loop_guard, "ROOTS", ("/repo/.claude/worktrees/loop", "/repo"))
    assert loop_guard.check_file("Edit", "/repo/pickfit/verify/judge.py", "/repo/.claude/worktrees/loop")
    assert loop_guard.check_file("Edit", "/repo/.claude/worktrees/other/pickfit/score.py", "/repo")
    assert loop_guard.check_file("Edit", "/repo/.claude/worktrees/loop/pickfit/verify/box.py", "/repo") is None


def test_main_prints_a_deny_decision_only_when_it_refuses(monkeypatch, capsys):
    event = {"tool_name": "Bash", "tool_input": {"command": "git push"}, "cwd": ROOT}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert loop_guard.main() == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "deny"

    event["tool_input"]["command"] = "uv run pytest -q"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert loop_guard.main() == 0
    assert capsys.readouterr().out == ""

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert loop_guard.main() == 0
