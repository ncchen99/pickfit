"""Install commands as a user runs them: pickfit's sandbox home written as $HOME.

A verified install guide keeps the commands its run executed, word for word (SoftwareRecord checks them against
the run). Those commands may name the sandbox user's home, /Users/sbx on the macOS box or /home/sbx on Linux,
which no user's machine has. The index publishes both: the verified commands, unchanged, and a user's copy made
here by one rule, with no model involved:

- unquoted, the home becomes "$HOME" (quoted, since a home folder may hold spaces): /Users/sbx/Applications/X.app
  -> "$HOME"/Applications/X.app;
- inside double quotes it becomes $HOME, which the shell expands there;
- inside single quotes nothing expands, so the command is kept as it ran and marked not portable: the user has
  to put their own home folder there.

Only the home at a path boundary counts (/home/sbxfoo is not it). The box's work folder (~/work) existed in the
sandbox before any step ran; a guide that names it says so (`needs_workdir`), since a user's machine has no
such folder until they make it. Windows commands are not rewritten: a Windows guide naming the box's home is
marked not portable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The sandbox user's home on each box (pickfit/verify/box.py BOX_HOME, tart_box.py MAC_HOME, vbox_box.py WIN_HOME;
# tests/test_userpaths.py keeps them equal).
SANDBOX_HOMES = {"linux": "/home/sbx", "macos": "/Users/sbx", "windows": "C:\\Users\\sbx"}
WORKDIR = "work"  # the box's work folder under its home (BOX_WORKDIR, MAC_WORKDIR)

_PATH_END = re.compile(r"[A-Za-z0-9_.-]")  # a character that would make the home a longer name (/home/sbxfoo)


@dataclass(frozen=True)
class UserCommand:
    command: str  # the command a user runs (the verified one when nothing changed or it cannot be rewritten)
    changed: bool  # the sandbox home was written as $HOME
    portable: bool  # False: the sandbox home is still in it (inside single quotes, or a Windows command)


def _at_boundary(text: str, i: int, home: str) -> bool:
    """The home starts a path here (not /tmp/home/sbx) and ends at a path boundary (not /home/sbxfoo)."""
    end = i + len(home)
    return (text.startswith(home, i) and (i == 0 or not (_PATH_END.match(text[i - 1]) or text[i - 1] == "/"))
            and (end == len(text) or not _PATH_END.match(text[end])))


def for_user(command: str, os_name: str | None) -> UserCommand:
    """The command with the sandbox home of `os_name`'s box written as $HOME, quote by quote."""
    home = SANDBOX_HOMES.get(os_name or "")
    if not home or home not in command:
        return UserCommand(command, changed=False, portable=True)
    if os_name == "windows":
        return UserCommand(command, changed=False, portable=False)
    out: list[str] = []
    quote: str | None = None  # None, "'" or '"'
    portable = True
    i = 0
    while i < len(command):
        c = command[i]
        if quote is None and c == "\\" and i + 1 < len(command):
            out.append(command[i:i + 2])
            i += 2
            continue
        if quote == '"' and c == "\\" and i + 1 < len(command):
            out.append(command[i:i + 2])
            i += 2
            continue
        if _at_boundary(command, i, home):
            if quote is None:
                out.append('"$HOME"')
            elif quote == '"':
                out.append("$HOME")
            else:  # single quotes: $HOME would stay literal
                out.append(home)
                portable = False
            i += len(home)
            continue
        if quote is None and c in "'\"":
            quote = c
        elif quote == c:
            quote = None
        out.append(c)
        i += 1
    if not portable:
        return UserCommand(command, changed=False, portable=False)
    rewritten = "".join(out)
    return UserCommand(rewritten, changed=rewritten != command, portable=True)


def expected_for_user(text: str, os_name: str | None) -> str:
    """Expected output naming the sandbox home (`which tool` -> /home/sbx/.local/bin/tool): the part after the
    home, which any user's output still contains."""
    home = SANDBOX_HOMES.get(os_name or "")
    if not home or home not in text or os_name == "windows":
        return text
    return re.sub(re.escape(home) + r"(?![A-Za-z0-9_.-])", "", text)


def names_workdir(command: str, os_name: str | None) -> bool:
    """The verified command names the box's work folder (which existed before any step ran)."""
    home = SANDBOX_HOMES.get(os_name or "")
    return bool(home) and re.search(re.escape(f"{home}/{WORKDIR}") + r"(?![A-Za-z0-9_.-])", command) is not None
