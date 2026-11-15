"""PreToolUse hook for a loop session: what the ingest loop may not do on its own (docs/loop.md).

A loop session runs in auto mode and is told to work around problems instead of asking. Three kinds of
action stay with a person, and this hook refuses them whatever the permission mode:

- going outside: git push, pickfit publish, wrangler deploy, merging a pull request;
- changing what decides a verdict: the judges, the fault rules, the box's limit checks, the scores, the
  schema, this guard and its settings (PROTECTED). A loop that fixes the harness could otherwise turn a red
  result green by loosening the check. It writes loop/proposals/<issue>.patch instead and carries on;
- records by hand: data/software changes only through the pipeline's own write-back, never an edit; tests
  are added or changed, never deleted; eval/ and .env are not read.

A hook reads one command at a time and a shell has many ways to write a file, so the Bash rules are a net,
not a wall: scripts/loop.sh checks the branch's diff against the same lists after every batch and stops the
loop when a protected file changed.

Installed only where a loop runs (scripts/loop_setup.sh writes loop/settings.json into the loop worktree's
.claude/settings.local.json; scripts/loop.sh passes it with --settings), so no other session is affected.
Reads the hook input on stdin; prints a deny decision or nothing. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A worktree lives at <main>/.claude/worktrees/<name>; the main checkout's files are protected too.
_MAIN = str(ROOT).split("/.claude/worktrees/")[0]
ROOTS = tuple(dict.fromkeys((str(ROOT), _MAIN)))

# What decides a verdict, a score or a record's shape, and the guard itself. A trailing slash is a directory.
PROTECTED = (
    "pickfit/verify/verdict.py",
    "pickfit/verify/judge.py",
    "pickfit/verify/feature_judge.py",
    "pickfit/verify/failure.py",
    "pickfit/verify/limits.py",
    "pickfit/verify/web_guard.py",
    "pickfit/score.py",
    "pickfit/schema.py",
    "schema/",
    "scripts/guarded_write_back.py",
    "scripts/loop_guard.py",
    "scripts/loop_budget.py",
    "scripts/loop.sh",
    "loop/settings.json",
    "loop/budget.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)
PIPELINE_ONLY = ("data/software/",)  # written by `pickfit ... --write-back`, never by an edit
OFF_LIMITS = ("eval/", ".env")  # not read at all

_OUTWARD = [
    (re.compile(r"\bgit\s+(?:-[cC]\s+\S+\s+|--?[\w-]+(?:=\S+)?\s+)*push\b"), "git push"),
    (re.compile(r"\bpickfit\s+publish\b"), "pickfit publish"),
    (re.compile(r"\bpickfit\s+watch\b[^|;&]*--publish\b"), "pickfit watch --publish"),
    (re.compile(r"\bwrangler\s+(?:deploy|publish)\b"), "wrangler deploy"),
    (re.compile(r"\bgh\s+pr\s+merge\b"), "gh pr merge"),
]
# Ways a shell command changes a file it names. `>` is handled apart, by its target.
_WRITES = re.compile(
    r"\bsed\s+(?:-\S+\s+)*-\w*i|\bperl\s+(?:-\S+\s+)*-\w*i|\btee\b|\brm\b|\bmv\b|\btruncate\b|\bdd\b"
    r"|(?:^|\s)patch\s|\bgit\s+(?:checkout|restore|rm|mv|apply|stash)\b|\bopen\(|\.write_text\(|\.write_bytes\(|\.write\(")
_FD_REDIRECT = re.compile(r"\d*>&\d+|\d*>\s*/dev/null")
_REDIRECT_TARGET = re.compile(r">>?\s*([^\s;|&)]+)")
# The pipeline commands that call a model or start a sandbox. --dry-run and --status spend nothing.
_PAID = re.compile(r"\bpickfit\s+(?:verify|extract|prescreen|score|usability|visual|reverify|watch|webapps|"
                   r"translate|usage-guide|ping)\b")
_FREE = re.compile(r"--dry-run\b|--status\b")
_DELETES = re.compile(r"\b(?:git\s+)?rm\b")
_PARTS = re.compile(r"&&|\|\||[;|\n]")
_COPY = re.compile(r"\b(?:cp|install|rsync)\b.*\s(\S+)\s*$")  # group 1: the destination, the last word


def _relative(path: str, cwd: str) -> str | None:
    """The path inside a checkout (this one, the main one or another worktree); None when it is outside.

    Symlinks are followed first, so a worktree's .env, a link to the main checkout's, is still .env.
    """
    full = Path(path) if Path(path).is_absolute() else Path(cwd or ROOT) / path
    text = str(full.resolve())
    for root in sorted(ROOTS, key=len, reverse=True):
        if text == root or text.startswith(root + "/"):
            return re.sub(r"^\.claude/worktrees/[^/]+/", "", text[len(root):].lstrip("/"))
    return None


def _under(relative: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if prefix.endswith("/"):
            if relative.startswith(prefix) or relative == prefix.rstrip("/"):
                return prefix
        elif relative == prefix or (prefix == ".env" and re.fullmatch(r"\.env(\..+)?", relative)):
            return prefix
    return None


def _mentions(command: str, prefixes: tuple[str, ...]) -> str | None:
    """A listed path named in a shell command: as typed, relative or absolute."""
    for prefix in prefixes:
        if prefix == ".env":
            if re.search(r"(?:^|[\s'\"=/])\.env(?:\.[\w.-]+)?(?=$|[\s'\";|&<>)])", command):
                return prefix
        elif re.search(r"(?:^|[\s'\"=/(])" + re.escape(prefix), command):
            return prefix
    return None


def check_file(tool: str, path: str, cwd: str) -> str | None:
    relative = _relative(path, cwd)
    if relative is None:
        return None
    if _under(relative, OFF_LIMITS):
        return f"{relative} is off limits to a loop session (eval/ and .env are never read)"
    if tool == "Read":
        return None
    hit = _under(relative, PROTECTED)
    if hit:
        return (f"{relative} decides verdicts, scores or the loop's own limits. Do not change it here: write the "
                f"change as loop/proposals/<issue>.patch, set the issue to review, park what waits on it, go on")
    if _under(relative, PIPELINE_ONLY):
        return f"{relative} is written only by the pipeline's write-back (pickfit verify --write-back), never edited"
    return None


def over_budget() -> str | None:
    """Why no more may be spent: a cap in loop/budget.json is reached, or the budget cannot be read."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import loop_budget
        reached = loop_budget.report(ROOT / "loop")["reached"]
    except Exception as error:  # a budget that cannot be read stops spending rather than letting it through
        return f"the loop's budget cannot be read ({type(error).__name__}: {error})"
    finally:
        sys.path.pop(0)
    return ", ".join(reached) if reached else None


def check_bash(command: str) -> str | None:
    for pattern, name in _OUTWARD:
        if pattern.search(command):
            return f"{name} stays with a person: note it in loop/journal.md and go on with the next item"
    if any(_PAID.search(part) and not _FREE.search(part) for part in _PARTS.split(command)):
        reached = over_budget()
        if reached:
            return (f"the loop's spending cap is reached: {reached}. Start nothing that costs money: write "
                    f"'需要你' with this line in loop/journal.md, leave the item as it is (the next session "
                    f"takes it up again) and end the session")
    off = _mentions(command, OFF_LIMITS)
    if off:
        return f"the command names {off}, which a loop session never reads"
    plain = _FD_REDIRECT.sub(" ", command)
    for target in _REDIRECT_TARGET.findall(plain):
        if _mentions(target.strip("'\""), PROTECTED + PIPELINE_ONLY):
            return f"the command writes {target}, a protected file; propose the change in loop/proposals/ instead"
    for part in _PARTS.split(plain):  # each command of a pipeline or a list is judged by the paths it names itself
        copy = _COPY.search(part)
        if copy:  # copying a protected file out, to draft a proposal, is fine; copying over one is not
            hit = _mentions(copy.group(1).strip("'\""), PROTECTED + PIPELINE_ONLY)
            if hit:
                return f"the command copies over {hit}, which a loop session does not edit"
        if _WRITES.search(part):
            hit = _mentions(part, PROTECTED + PIPELINE_ONLY)
            if hit:
                return (f"the command may change {hit}, which a loop session does not edit; propose the change "
                        f"in loop/proposals/ (records: only the pipeline's write-back)")
        if _DELETES.search(part) and _mentions(part, ("tests/",)):
            return "tests are added or changed, never deleted, in a loop session"
    return None


def decide(event: dict) -> str | None:
    """The reason to refuse this tool call, or None to let the permission mode decide."""
    tool = event.get("tool_name") or ""
    args = event.get("tool_input") or {}
    cwd = event.get("cwd") or str(ROOT)
    if tool == "Bash":
        return check_bash(str(args.get("command") or ""))
    if tool in ("Edit", "Write", "NotebookEdit", "Read"):
        path = args.get("file_path") or args.get("notebook_path")
        return check_file(tool, str(path), cwd) if path else None
    if tool in ("Grep", "Glob"):
        path = args.get("path")
        if path:
            relative = _relative(str(path), cwd)
            if relative is not None and _under(relative, OFF_LIMITS):
                return f"{relative} is off limits to a loop session"
    return None


def main() -> int:
    if sys.argv[1:] == ["--list-protected"]:  # for scripts/loop.sh, so the list lives in one place
        print("\n".join(PROTECTED))
        return 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    reason = decide(event)
    if reason:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": reason}}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
