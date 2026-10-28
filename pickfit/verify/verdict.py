"""The verdict comes from the command log, not from what the model says (P3.3 gap).

`finish` cites commands by their command_id; the program looks each one up in
the log and decides from what actually ran:

- a step counts only if it exited 0 and its exit code was not masked
  (`|| true`, `; echo $?`, a trailing `| head`, a background `&`);
- a smoke test passes only if its recorded exit code is the expected one, the
  exit code was not masked, the expected signal appears in its output, and the
  output shows no crash; a non-zero expected exit (a linter that found
  problems) needs the signal;
- the level is the weaker of the claim and what the passing checks support:
  install needs a passing check, function a README example (not only
  --version/--help), service a background server, inference a generation
  request against it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.schema import COMMAND_MAX, PASSED_LEVELS, is_passed

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord, FinishArgs

EXCERPT_CHARS = 300

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")

# Last command of a `;` list whose exit code says nothing about the command before it.
_TRIVIAL = {"echo", "printf", "true", ":", "exit", "ls", "cat", "pwd", "sleep", "wait", "date",
            "which", "type", "command", "hash", "set", "test", "["}
# Last command of a pipeline that hides the exit code of what feeds it (no pipefail).
_FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "rg", "cat", "less", "more", "sed", "awk", "tee",
            "wc", "sort", "uniq", "cut", "tr", "column", "jq", "xargs", "true", "nl", "fold", "fmt"}
# Compound commands: their exit code is whatever branch ran last.
_CONTROL = {"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "case", "esac"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Output that means the program crashed, whatever the exit code says.
_CRASH = re.compile(r"Traceback \(most recent call last\)|panicked at|Segmentation fault|"
                    r": command not found|No module named |Error: Cannot find module")
_VERSION_HELP = re.compile(r"(?:^|\s)(?:--version|-V|-v|--help|-h|version|help)\s*$")
_GENERATION = re.compile(r"/v1/(?:chat/)?completions|/api/(?:generate|chat)|/completion\b|/v1/responses")


# ---------------------------------------------------------------- exit-code masking


def _top_level(command: str) -> list[tuple[str, str]]:
    """Split a bash command at top-level operators: [(operator before, text), ...].

    Quotes, $(...), backticks, (...) subshells, comments and heredoc bodies are
    skipped, so only operators that bash itself sees at the top split the text.
    """
    parts: list[tuple[str, str]] = []
    op, start, depth, i, n = "", 0, 0, 0, len(command)
    heredocs: list[tuple[str, bool]] = []
    while i < n:
        ch = command[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = command.find("'", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == '"':
            i += 1
            while i < n and command[i] != '"':
                i += 2 if command[i] == "\\" else 1
            i += 1
            continue
        if ch == "`":
            end = command.find("`", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == "#" and (i == 0 or command[i - 1] in " \t\n;|&("):
            end = command.find("\n", i)
            i = n if end < 0 else end
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            m = re.match(r"<<(-?)\s*(['\"]?)([A-Za-z0-9_.-]+)\2", command[i:])
            if m:
                heredocs.append((m.group(3), m.group(1) == "-"))
                i += m.end()
                continue
        if ch in "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            two = command[i:i + 2]
            found = None
            if two in ("||", "&&"):
                found = two
            elif ch == "|":
                found = "|"
            elif ch == ";":
                found = ";"
            elif ch == "&" and not (i and command[i - 1] in "<>") and command[i + 1:i + 2] != ">":
                found = "&"
            elif ch == "\n":
                found = "\n"
            if found:
                parts.append((op, command[start:i]))
                op = found
                i += len(found)
                if found == "\n" and heredocs:
                    i = _skip_heredocs(command, i, heredocs)
                    heredocs = []
                start = i
                continue
        i += 1
    parts.append((op, command[start:]))
    return [(o, t) for o, t in parts if t.strip() or o]


def _skip_heredocs(command: str, i: int, heredocs: list[tuple[str, bool]]) -> int:
    for delimiter, strip_tabs in heredocs:
        while i < len(command):
            end = command.find("\n", i)
            line = command[i:] if end < 0 else command[i:end]
            i = len(command) if end < 0 else end + 1
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
    return i


def _first_word(text: str) -> str:
    words = text.strip().lstrip("({").split()
    while words and (_ASSIGNMENT.match(words[0]) or words[0] in ("time", "env", "exec", "nohup")):
        words = words[1:]
    return words[0].rsplit("/", 1)[-1] if words else ""


def masked_exit(command: str) -> str | None:
    """Why the recorded exit code of `command` may not be its real result, or None."""
    parts = _top_level(command)
    if parts and parts[-1][0] == "&" and not parts[-1][1].strip():
        return "a trailing `&` sends it to the background"
    parts = [p for p in parts if p[1].strip()]
    if any(op == "||" for op, _ in parts):
        return "`||` runs another command when the first fails"
    for _, text in parts:
        words = text.split()
        if words[:1] == ["exit"] and (len(words) == 1 or words[1] == "0"):
            return "`exit` sets the exit code itself"
        if words[:2] == ["set", "+e"]:
            return "`set +e` ignores failures"
        if text.strip().startswith("!"):
            return "`!` inverts the exit code"
        if _first_word(text) in _CONTROL:
            return f"`{_first_word(text)}` decides the exit code itself"
    if not parts:
        return None
    # The exit code is the last list's: everything after the last `;`, `&` or newline.
    cut = max((k for k, (op, _) in enumerate(parts) if op in (";", "&", "\n")), default=0)
    tail = parts[cut:]
    if cut and _first_word(tail[0][1]) in _TRIVIAL:
        return f"the last command is `{_first_word(tail[0][1])}`, so it hides the exit code before it"
    # Within that list, the exit code is the last pipeline's last command.
    start = max(k for k, (op, _) in enumerate(tail) if op != "|")
    pipeline = tail[start:]
    if len(pipeline) > 1 and _first_word(pipeline[-1][1]) in _FILTERS:
        return f"piping into `{_first_word(pipeline[-1][1])}` hides the exit code of the command before it"
    return None


def last_command(command: str) -> str:
    parts = [text for _, text in _top_level(command) if text.strip()]
    return parts[-1] if parts else command


# ---------------------------------------------------------------- verdict


def _plain(text: str) -> str:
    return " ".join(_ANSI.sub("", text).split()).lower()


def _excerpt(record: CommandRecord, signal: str) -> str:
    """The output line that carries the signal, else the last non-empty line."""
    lines = [ln for ln in _ANSI.sub("", f"{record.stdout}\n{record.stderr}").splitlines() if ln.strip()]
    if signal:
        key = _plain(signal)
        for line in lines:
            if key and key in _plain(line):
                return line.strip()[:EXCERPT_CHARS]
    return lines[-1].strip()[:EXCERPT_CHARS] if lines else ""


def check_kind(command: str) -> str:
    """version (--version/--help only), generation (asks a model for text), or example."""
    if _GENERATION.search(command):
        return "generation"
    if _VERSION_HELP.search(last_command(command)):
        return "version"
    return "example"


@dataclass
class ResolvedCheck:
    """One claimed smoke test, read back from the log."""

    command_id: int
    command: str
    tool: str
    setup_ids: list[int]
    expected_signal: str
    expected_exit_code: int
    exit_code: int | None
    passed: bool
    kind: str
    observed_excerpt: str = ""
    problems: list[str] = field(default_factory=list)


@dataclass
class LogVerdict:
    claimed_level: str
    level: str
    unverified_reason: str | None
    step_ids: list[int]
    checks: list[ResolvedCheck]
    problems: list[str]

    @property
    def agrees(self) -> bool:
        return self.level == self.claimed_level and not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "agrees": self.agrees}


def evaluate_check(record: CommandRecord, expected_exit_code: int, expected_signal: str
                   ) -> tuple[bool, list[str]]:
    """Whether one recorded command shows a passing check; the reasons when not."""
    problems: list[str] = []
    masked = masked_exit(record.command)
    if masked:
        problems.append(f"exit code masked ({masked})")
    if record.timed_out:
        problems.append("timed out")
    if record.exit_code != expected_exit_code:
        problems.append(f"expected exit {expected_exit_code}, log shows {record.exit_code}")
    output = _plain(f"{record.stdout}\n{record.stderr}")
    if not output:
        problems.append("no output to show it worked")
    signal = _plain(expected_signal)
    if expected_exit_code != 0 and not signal:
        problems.append("a non-zero expected exit needs an expected_signal")
    if signal and signal not in output:
        problems.append(f"expected_signal not in the output: {expected_signal[:80]!r}")
    crash = _CRASH.search(_ANSI.sub("", f"{record.stdout}\n{record.stderr}"))
    if crash:
        problems.append(f"output shows a crash: {crash.group(0)!r}")
    return not problems, problems


def supported_level(steps_ok: bool, checks: list[ResolvedCheck], has_service: bool) -> str | None:
    """The strongest passed level the passing checks support, or None."""
    passing = [c for c in checks if c.passed]
    if not steps_ok or not passing:
        return None
    if any(c.kind == "generation" for c in passing) and has_service:
        return "inference"
    if has_service and any(c.kind != "version" for c in passing):
        return "service"
    if any(c.kind != "version" for c in passing):
        return "function"
    return "install"


def weaker(a: str, b: str) -> str:
    return a if PASSED_LEVELS.index(a) > PASSED_LEVELS.index(b) else b


def log_verdict(finish: FinishArgs, commands: list[CommandRecord]) -> LogVerdict:
    """Decide the level from the command log; the claim is only an upper bound."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    problems: list[str] = []

    steps_ok = bool(finish.steps)
    step_ids: list[int] = []
    for step in finish.steps:
        record = by_id.get(step.command_id)
        if record is None or record.tool != "run_command":
            steps_ok = False
            problems.append(f"step cites no run_command with id {step.command_id}")
            continue
        step_ids.append(step.command_id)
        masked = masked_exit(record.command)
        if record.exit_code != 0 or record.timed_out or masked:
            steps_ok = False
            why = masked or ("timed out" if record.timed_out else f"exit {record.exit_code}")
            problems.append(f"step {step.command_id} does not show a success ({why}): "
                            f"{_one_line(record.command)}")
        elif len(record.command) > COMMAND_MAX:
            steps_ok = False
            problems.append(f"step {step.command_id} is {len(record.command)} characters; an install step "
                            f"must fit in {COMMAND_MAX} (split it into shorter commands)")

    checks: list[ResolvedCheck] = []
    has_service = False
    for test in finish.smoke_tests:
        record = by_id.get(test.command_id)
        if record is None:
            problems.append(f"smoke test cites no command with id {test.command_id}")
            continue
        check = ResolvedCheck(
            command_id=test.command_id, command=record.command, tool=record.tool,
            setup_ids=list(test.setup_ids), expected_signal=test.expected_signal.strip(),
            expected_exit_code=test.expected_exit_code, exit_code=record.exit_code, passed=False,
            kind=check_kind(record.command))
        setup_ok = True
        for setup_id in test.setup_ids:
            if setup_id in step_ids:  # an install step: the replay runs every step first anyway
                continue
            setup = by_id.get(setup_id)
            if setup is None or setup_id >= test.command_id:
                setup_ok = False
                check.problems.append(f"setup {setup_id} is not a command that ran before it")
            elif setup.exit_code != 0 or setup.timed_out:
                setup_ok = False
                check.problems.append(f"setup {setup_id} exited {setup.exit_code}")
        ok, why = evaluate_check(record, check.expected_exit_code, check.expected_signal)
        check.problems += why
        check.passed = ok and setup_ok
        check.observed_excerpt = _excerpt(record, check.expected_signal)
        serves = record.tool == "run_background" or any(
            by_id[s].tool == "run_background" for s in test.setup_ids if s in by_id)
        if check.passed and serves:
            has_service = True
        problems += [f"smoke test {test.command_id}: {p}" for p in check.problems]
        checks.append(check)

    level, reason = finish.level, finish.unverified_reason
    if is_passed(level):
        supported = supported_level(steps_ok, checks, has_service)
        if supported is None:
            level, reason = "unverified", "other"
            if not problems:
                problems.append("no passing check in the log")
        else:
            level = weaker(level, supported)
    return LogVerdict(claimed_level=finish.level, level=level, unverified_reason=reason,
                      step_ids=step_ids, checks=checks, problems=problems)


def _one_line(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
