"""Help text: what a command-line tool says about itself, kept as a source for its capabilities.

docs/proposals/capabilities.md step 4. A tool's own --help (and its subcommands' help) lists what it can do
more completely than a README's headline, and it is free once the tool is installed. Two ways in:

- help_from_report: the help commands an agent already ran in a verify run (report.json keeps every
  command's full stdout and stderr), for the runs pickfit made before this module.
- capture_help: after a run that passed, pickfit runs `<tool> --help` itself in the agent's box, then the
  help of up to SUBCOMMANDS_MAX subcommands it lists, and the agent saves them in report.json under
  `help`. These commands are pickfit's, not the agent's: they use none of its budget and no check
  cites them.

`python -m pickfit.verify.help_text` gathers both from runs/verify into runs/capabilities/help/<slug>.json,
the newest run first, for the capability extraction (step 3) to read. Help text is data from the tool, never
instructions: the extraction quotes it like a README.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from pickfit.verify.verdict import last_command

HELP_CHARS = 20_000  # the start matters most: a summary, then commands and options
SUBCOMMANDS_MAX = 8
HELP_TIMEOUT_S = 15
HELP_SECONDS_MAX = 90  # all of one run's help commands together
STORE = Path("capabilities") / "help"

_HELP_FLAGS = {"--help", "-h", "-help", "-?", "/?"}
# Wrappers that run a package's binary: the tool's own name follows them.
_RUNNERS = {"npx": 1, "bunx": 1, "uvx": 1, "pnpx": 1, "pipx": 2}  # pipx run <pkg>
_NOT_TOOLS = {"python", "python3", "node", "bash", "sh", "zsh", "env", "sudo", "uv", "pip", "pip3", "npm",
              "cargo", "go", "docker", "curl", "wget", "cat", "echo", "ls", "cd", "true"}
_QUIET = re.compile(r"\s*(?:2>&1|\d?>\s*/dev/null|&>\s*/dev/null)\s*")
_VIEWER = re.compile(r"\s*\|\s*(?:head|less|more|cat)(?:\s+-n?\s*\d+|\s+-\d+)?\s*$")
_BINARY = re.compile(r"^[\w.+~/-]+$")
_SUBCOMMAND = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
_LOOKS_LIKE_HELP = re.compile(r"(?im)^\s*(?:usage|options|commands|subcommands|flags|arguments|synopsis)\b|usage:")
_SECTION = re.compile(r"(?i)^\s*(?:available |core |main |other )?(?:sub)?commands\s*:?\s*$")
_ENTRY = re.compile(r"^\s{1,8}([a-z][a-z0-9-]{0,30})(?:,\s*[a-z][a-z0-9-]*)*(?:\s{2,}|\t|\s+-\s)\S")


@dataclass
class HelpText:
    command: str
    exit_code: int
    text: str
    truncated: bool = False
    run_id: str | None = None
    command_id: int | None = None  # the agent's command, when it came from one
    by: str = "agent"  # agent: a command the agent ran; pickfit: capture_help ran it


def _words(command: str) -> list[str] | None:
    bare = _QUIET.sub(" ", last_command(_VIEWER.sub("", command.strip()))).strip()
    if not bare or any(op in bare for op in ("&&", "||", ";", "|", "`", "$(", ">", "<")):
        return None
    try:
        return shlex.split(bare)
    except ValueError:
        return None


def is_help_command(command: str) -> bool:
    """`tool --help`, `tool -h`, `tool help [sub]`, `tool sub --help`, `man tool`, as the last command of a chain
    (its output then starts with what ran before it), with no redirect to a file."""
    words = _words(command)
    if not words or "--version" in words:
        return False
    if words[0] == "man":
        return len(words) == 2
    start = _RUNNERS.get(words[0].rsplit("/", 1)[-1], 0) + 1
    rest = words[start:]
    return bool(rest) and (any(w in _HELP_FLAGS for w in rest) or rest[0] == "help")


def looks_like_help(text: str) -> bool:
    return len(text.strip()) >= 40 and bool(_LOOKS_LIKE_HELP.search(text))


def _clip(text: str) -> tuple[str, bool]:
    text = text.strip("\n")
    return (text, False) if len(text) <= HELP_CHARS else (text[:HELP_CHARS], True)


def _help_of(stdout: str, stderr: str) -> str | None:
    """Help goes to stdout, or to stderr when the tool prints usage as an error (some do for -h)."""
    for text in (stdout or "", stderr or ""):
        if looks_like_help(text):
            return text
    return None


def help_from_report(report: dict[str, Any]) -> list[HelpText]:
    """The help commands an agent ran in one verify run, each command once, in the order it ran them."""
    seen: set[str] = set()
    found: list[HelpText] = []
    for c in report.get("commands") or []:
        command = c.get("command") or ""
        if c.get("tool") != "run_command" or c.get("timed_out") or not is_help_command(command):
            continue
        text = _help_of(c.get("stdout") or "", c.get("stderr") or "")
        key = " ".join(_words(command) or [])
        if text is None or key in seen:
            continue
        seen.add(key)
        clipped, cut = _clip(text)
        found.append(HelpText(command=command, exit_code=c.get("exit_code") or 0, text=clipped, truncated=cut,
                              run_id=report.get("run_id"), command_id=c.get("command_id")))
    return found


def tool_command(checks: Iterable[Any]) -> str | None:
    """How the run started the tool, from its passing --version/--help check: `graphtty`, `npx some-cli`.
    None when no such check passed or it ran the tool through something pickfit does not unwrap."""
    for check in checks:
        if not getattr(check, "passed", False) or getattr(check, "kind", "") != "version":
            continue
        words = _words(getattr(check, "command", "") or "")
        if not words:
            continue
        name = words[0].rsplit("/", 1)[-1]
        take = _RUNNERS.get(name, 0) + 1
        if len(words) <= take or name in _NOT_TOOLS or not all(_BINARY.match(w) for w in words[:take]):
            continue
        return " ".join(words[:take])  # _BINARY allows no shell syntax; quoting would stop ~ expanding
    return None


def subcommands(text: str) -> list[str]:
    """The subcommands a help text lists under a Commands: heading (clap, cobra, click, argparse layouts)."""
    found: list[str] = []
    inside = False
    for line in text.splitlines():
        if _SECTION.match(line):
            inside = True
            continue
        if not inside:
            continue
        if not line.strip():
            continue
        if not line[:1].isspace():  # the next heading
            inside = bool(_SECTION.match(line))
            continue
        m = _ENTRY.match(line)
        if m and m.group(1) not in found and m.group(1) != "help" and _SUBCOMMAND.match(m.group(1)):
            found.append(m.group(1))
    return found


def capture_help(exec_: Callable[[str, int], Any], tool: str, *, clock: Callable[[], float],
                 run_id: str | None = None) -> list[HelpText]:
    """Run the tool's help, then its subcommands' help, in the box. exec_ is Box.exec. Stops at
    HELP_SECONDS_MAX; a command that times out or prints no help is skipped."""
    started = clock()
    texts: list[HelpText] = []

    def run(command: str) -> HelpText | None:
        if clock() - started >= HELP_SECONDS_MAX:
            return None
        result = exec_(command, HELP_TIMEOUT_S)
        if result.timed_out:
            return None
        text = _help_of(result.stdout, result.stderr)
        if text is None:
            return None
        clipped, cut = _clip(text)
        return HelpText(command=command, exit_code=result.exit_code, text=clipped,
                        truncated=cut or bool(getattr(result, "truncated", False)), run_id=run_id, by="pickfit")

    top = next((h for h in (run(f"{tool} {flag}") for flag in ("--help", "-h", "help")) if h), None)
    if top is None:
        return texts
    texts.append(top)
    for sub in subcommands(top.text)[:SUBCOMMANDS_MAX]:
        found = run(f"{tool} {sub} --help")
        if found:
            texts.append(found)
    return texts


# ---------------------------------------------------------------- gathering from saved runs


def _reports(runs_dir: Path) -> list[dict[str, Any]]:
    out = []
    for path in (runs_dir / "verify").glob("*/report.json"):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(out, key=lambda r: r.get("started_at") or "", reverse=True)


def gather(runs_dir: Path, slugs: set[str] | None = None) -> dict[str, list[HelpText]]:
    """Per slug, the help texts of its saved runs, newest run first; a command seen in a newer run is not
    taken again from an older one. pickfit's own capture comes before the agent's commands of the same run."""
    by_slug: dict[str, list[HelpText]] = {}
    seen: dict[str, set[str]] = {}
    for report in _reports(runs_dir):
        slug = report.get("slug")
        if not slug or (slugs and slug not in slugs):
            continue
        saved = [HelpText(**h) for h in report.get("help") or []]
        for h in [*saved, *help_from_report(report)]:
            key = " ".join(_words(h.command) or [h.command])
            if key in seen.setdefault(slug, set()):
                continue
            seen[slug].add(key)
            by_slug.setdefault(slug, []).append(h)
    return by_slug


def write_store(by_slug: dict[str, list[HelpText]], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, texts in by_slug.items():
        doc = {"slug": slug, "help": [asdict(h) for h in texts]}
        (out_dir / f"{slug}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(by_slug)


def main(argv: list[str] | None = None) -> int:
    from pickfit.env import REPO_ROOT, get_env

    parser = argparse.ArgumentParser(description="Gather saved help text from verify runs (capabilities step 4).")
    parser.add_argument("--runs-dir", type=Path, default=Path(get_env("PICKFIT_RUNS_DIR") or REPO_ROOT / "runs"))
    parser.add_argument("--slug", action="append", help="only this tool (repeatable)")
    parser.add_argument("--out", type=Path, default=None, help="default: <runs-dir>/capabilities/help")
    args = parser.parse_args(argv)
    by_slug = gather(args.runs_dir, set(args.slug) if args.slug else None)
    out = args.out or args.runs_dir / STORE
    written = write_store(by_slug, out)
    texts = sum(len(v) for v in by_slug.values())
    print(json.dumps({"tools": written, "help_texts": texts,
                      "with_subcommands": sum(1 for v in by_slug.values() if len(v) > 1), "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
