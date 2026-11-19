"""Help text as a capability source (pickfit/verify/help_text.py, capabilities step 4)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pickfit.verify.help_text import (
    HelpText,
    capture_help,
    gather,
    help_from_report,
    is_help_command,
    looks_like_help,
    subcommands,
    tool_command,
    write_store,
)

CLAP = """All-in-one LLM CLI Tool

Usage: aichat [OPTIONS] [TEXT]...

Options:
  -m, --model <MODEL>   Select a LLM model
  -h, --help            Print help
"""
COBRA = """Work seamlessly with GitHub from the command line.

USAGE
  gh <command> <subcommand> [flags]

CORE COMMANDS
  auth:        Authenticate gh and git with GitHub
  browse:      Open repositories in the browser

Available Commands:
  completion  Generate the autocompletion script
  release     Manage releases
  help        Help about any command

Flags:
  --help   Show help for command
"""
CLICK = """Usage: frob [OPTIONS] COMMAND [ARGS]...

  Frob files.

Options:
  --help  Show this message and exit.

Commands:
  convert  Convert a file to another format.
  watch    Watch a folder.
"""


@pytest.mark.parametrize("command", [
    "aichat --help", "aichat -h", "~/.local/bin/aichat --help 2>&1", "frob help convert", "frob convert --help",
    "npx some-cli --help", "man pandoc", "aichat --help | head -50",
])
def test_help_commands_are_recognized(command):
    assert is_help_command(command)


@pytest.mark.parametrize("command", [
    "aichat --version", "aichat --help && aichat --version", "pip install aichat", "npx --help",
    "aichat --help > out.txt", "cat README.md", "man", "frob convert in.csv",
])
def test_other_commands_are_not_help(command):
    assert not is_help_command(command)


def test_help_text_is_told_from_errors():
    assert looks_like_help(CLAP) and looks_like_help(CLICK)
    assert not looks_like_help("error: unexpected argument '--help'")
    assert not looks_like_help("")


def test_subcommands_are_read_from_the_commands_section():
    assert subcommands(CLICK) == ["convert", "watch"]
    assert subcommands(COBRA) == ["completion", "release"]  # `help` is skipped
    assert subcommands(CLAP) == []


def check(command: str, kind: str = "version", passed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(command=command, kind=kind, passed=passed)


def test_the_tool_command_comes_from_a_passing_version_check():
    assert tool_command([check("frob in.csv", "example"), check("cd x && ~/.local/bin/frob --version")]) \
        == "~/.local/bin/frob"
    assert tool_command([check("npx some-cli --version")]) == "npx some-cli"
    assert tool_command([check("frob --version", passed=False)]) is None
    assert tool_command([check("python -m frob --version")]) is None  # not unwrapped
    assert tool_command([]) is None


class Clock:
    def __init__(self, step: float = 1.0) -> None:
        self.now, self.step = 0.0, step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def fake_exec(answers: dict[str, tuple[int, str, str]], ran: list[str], timeouts: list[int] | None = None,
              hangs: set[str] = frozenset()):
    def exec_(command: str, timeout_s: int):
        ran.append(command)
        if timeouts is not None:
            timeouts.append(timeout_s)
        code, out, err = answers.get(command, (127, "", f"{command}: not found"))
        return SimpleNamespace(exit_code=code, stdout=out, stderr=err, timed_out=command in hangs, truncated=False)
    return exec_


def test_capture_runs_the_help_then_each_subcommand():
    ran: list[str] = []
    answers = {"frob --help": (0, CLICK, ""),
               "frob convert --help": (0, "Usage: frob convert [OPTIONS] SRC DST\n\nOptions:\n  --to TEXT", ""),
               "frob watch --help": (0, "", "Watch: not documented")}
    texts = capture_help(fake_exec(answers, ran), "frob", clock=Clock(), run_id="verify-frob-1")
    assert ran == ["frob --help", "frob convert --help", "frob watch --help"]
    assert [t.command for t in texts] == ["frob --help", "frob convert --help"]
    assert {t.by for t in texts} == {"pickfit"} and texts[0].run_id == "verify-frob-1"


def test_capture_falls_back_to_dash_h_and_stops_on_time():
    ran: list[str] = []
    texts = capture_help(fake_exec({"frob -h": (2, "", CLICK)}, ran), "frob", clock=Clock())
    assert ran[:2] == ["frob --help", "frob -h"] and texts[0].text.startswith("Usage: frob")  # usage on stderr
    ran = []
    assert capture_help(fake_exec({"frob --help": (0, CLICK, "")}, ran), "frob", clock=Clock(step=100)) == []
    assert ran == []


def report(run_id: str, started: str, commands: list[dict], help: list[dict] | None = None) -> dict:
    return {"run_id": run_id, "slug": "frob", "started_at": started, "commands": commands, "help": help or []}


def cmd(command: str, stdout: str, command_id: int = 1, tool: str = "run_command") -> dict:
    return {"command": command, "stdout": stdout, "stderr": "", "exit_code": 0, "timed_out": False,
            "tool": tool, "command_id": command_id}


def test_saved_runs_give_their_help_commands_once():
    r = report("verify-frob-2", "2026-11-04T10:00:00+08:00",
               [cmd("frob --version", "frob 1.0", 1), cmd("frob --help", CLICK, 2), cmd("frob --help 2>&1", CLICK, 3),
                cmd("frob -h", "error: no", 4)])
    texts = help_from_report(r)
    assert [(t.command, t.command_id, t.by) for t in texts] == [("frob --help", 2, "agent")]


def test_gather_prefers_newer_runs_and_pickfits_capture(tmp_path: Path):
    old = report("verify-frob-1", "2026-11-01T10:00:00+08:00", [cmd("frob --help", "Usage: frob OLD\n" + CLICK)])
    new = report("verify-frob-2", "2026-11-10T10:00:00+08:00", [cmd("frob convert --help", "Usage: frob convert SRC DST\n\nOptions:\n  --to TEXT")],
                 help=[{"command": "frob --help", "exit_code": 0, "text": CLICK, "by": "pickfit",
                        "run_id": "verify-frob-2"}])
    for r in (old, new):
        d = tmp_path / "verify" / r["run_id"]
        d.mkdir(parents=True)
        (d / "report.json").write_text(json.dumps(r))
    by_slug = gather(tmp_path)
    assert [(t.command, t.run_id, t.by) for t in by_slug["frob"]] == [
        ("frob --help", "verify-frob-2", "pickfit"), ("frob convert --help", "verify-frob-2", "agent")]
    assert gather(tmp_path, {"other"}) == {}
    out = tmp_path / "store"
    assert write_store(by_slug, out) == 1
    saved = json.loads((out / "frob.json").read_text())
    assert saved["slug"] == "frob" and [HelpText(**h) for h in saved["help"]] == by_slug["frob"]


def test_long_help_keeps_its_start():
    texts = help_from_report(report("r", "", [cmd("frob --help", CLICK + "x" * 30_000)]))
    assert texts[0].truncated and texts[0].text.startswith("Usage: frob") and len(texts[0].text) == 20_000


def test_each_help_command_gets_five_seconds_and_all_of_them_thirty():
    ran: list[str] = []
    timeouts: list[int] = []
    answers = {"frob --help": (0, CLICK, ""), "frob convert --help": (0, CLICK, ""), "frob watch --help": (0, CLICK, "")}
    capture_help(fake_exec(answers, ran, timeouts), "frob", clock=Clock(step=12))
    # started at 12; --help at 24 (18 s left: 5), convert at 36 (6 s left: 5), watch at 48 (none left)
    assert ran == ["frob --help", "frob convert --help"] and timeouts == [5, 5]
    ran, timeouts = [], []
    capture_help(fake_exec(answers, ran, timeouts), "frob", clock=Clock(step=13))
    assert timeouts == [5, 4]  # started at 13; convert at 39 has 30 - 26 = 4 s left: never more than that


def test_a_help_command_that_hangs_ends_the_capture():
    ran: list[str] = []
    assert capture_help(fake_exec({}, ran, hangs={"frob --help"}), "frob", clock=Clock()) == []
    assert ran == ["frob --help"]  # -h and help are not tried
    ran = []
    texts = capture_help(fake_exec({"frob --help": (0, CLICK, "")}, ran, hangs={"frob convert --help"}),
                         "frob", clock=Clock())
    assert ran == ["frob --help", "frob convert --help"] and [t.command for t in texts] == ["frob --help"]
