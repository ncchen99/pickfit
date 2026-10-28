"""Rule table for common install errors (P3.2, architecture C.2 step 3).

Rules run before the model sees a failed command: a hit adds a short hint
(and sometimes a suggested command) to the tool output. The model still
decides what to run; rules never execute anything. Patterns come from the
spike (llama.cpp, evnx, graphtty) and the design's error table.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# Shared libraries seen missing in slim images -> Debian package.
SYSTEM_LIBRARY_PACKAGES: dict[str, str] = {
    "libgomp.so.1": "libgomp1",
    "libssl.so.3": "libssl3",
    "libcurl.so.4": "libcurl4",
    "libstdc++.so.6": "libstdc++6",
    "libasound.so.2": "libasound2",
    "libGL.so.1": "libgl1",
    "libfuse.so.2": "libfuse2",
    "libgtk-3.so.0": "libgtk-3-0",
}
TOOLCHAINS = ("cargo", "rustc", "go", "gcc", "g++", "cc", "make", "cmake", "brew", "docker", "sudo")
BOX_TOOLS = "python3, uv, pipx, node/npm, git, curl"


@dataclass(frozen=True)
class RuleHit:
    rule: str
    hint: str
    suggested_command: str | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    hint: Callable[[re.Match[str], str], str]
    suggest: Callable[[re.Match[str], str], str | None] = lambda m, command: None
    only_exit: int | None = None


def _pip_package(command: str) -> str:
    m = re.search(r"pip3?\s+install\s+(?:-\S+\s+)*([A-Za-z0-9][\w.\-\[\],]*)", command)
    return m.group(1) if m else "<package>"


def _library_hint(m: re.Match[str], command: str) -> str:
    lib = m.group(1)
    pkg = SYSTEM_LIBRARY_PACKAGES.get(lib)
    named = f" (Debian package {pkg})" if pkg else ""
    return (f"The program needs the system library {lib}{named}. The box user is not root and cannot "
            "apt-get. Prefer a statically linked build (release assets named musl or static) or another "
            "install method; otherwise finish with blocking_error naming the package.")


def _toolchain_hint(m: re.Match[str], command: str) -> str:
    tool = m.group(1)
    if tool == "sudo":
        return "There is no sudo in the box. Use a user-level install into ~/.local instead."
    if tool == "brew":
        return "Homebrew is not available in the Linux box; pick a non-brew candidate."
    return (f"{tool} is not installed in the box (it has {BOX_TOOLS}). Switch to another install "
            "candidate, such as a release binary or a package manager, instead of installing a toolchain.")


def _missing_command(m: re.Match[str], command: str) -> str:
    return (f"`{m.group(1)}` is not on PATH. User-level installs land in ~/.local/bin (uv tool, pipx, "
            "pip --user, npm with this box's prefix), ~/.cargo/bin or ~/go/bin. Check with "
            "`ls ~/.local/bin` and call the binary by its real name.")


_TOOLCHAIN_ALT = "|".join(re.escape(t) for t in TOOLCHAINS)

RULES: tuple[Rule, ...] = (
    Rule("missing_shared_library",
         re.compile(r"error while loading shared libraries: (lib[\w.+-]+?\.so[\w.]*)"),
         _library_hint),
    Rule("externally_managed_python",
         re.compile(r"externally-managed-environment"),
         lambda m, c: ("pip refuses to install into this Python (PEP 668). Install the CLI in its own "
                       "environment with `uv tool install` or `pipx install`."),
         lambda m, c: f"uv tool install {_pip_package(c)}"),
    Rule("missing_toolchain",
         re.compile(rf"(?:^|[\s:'\"])({_TOOLCHAIN_ALT})(?::|'|\")? (?:command )?not found", re.M),
         _toolchain_hint),
    Rule("not_on_path",
         re.compile(r"(?:^|\s)([\w.+-]+): (?:command )?not found", re.M),
         _missing_command, only_exit=127),
    Rule("python_version",
         re.compile(r"Requires-Python|requires a different Python|No matching distribution found for"
                    r"|Could not find a version that satisfies"),
         lambda m, c: ("No release fits this Python (3.12), or the package name is wrong. Check the name "
                       "in the README; `uv tool install --python 3.11 <pkg>` (or 3.13) lets uv fetch "
                       "another Python.")),
    Rule("flag_unsupported",
         re.compile(r"unrecognized arguments?: (?:-V|--version|-v)\b|unexpected argument '(?:--version|-V)'"
                    r"|[Uu]nknown (?:option|flag|argument)[: ]+'?(?:--version|-V)\b|No such option: (?:--version|-V)"
                    r"|invalid option -- '?V"),
         lambda m, c: ("The tool does not support that flag; this is not an install failure. Try `--help`, "
                       "`-h`, `version` or `help`.")),
    Rule("error_names_fix",
         re.compile(r"(?:[Cc]reate it with|[Pp]lease run|[Ff]irst run|[Tt]ry running|[Rr]un|[Uu]se)\s+"
                    r"[`'\"]([^`'\"\n]{2,120})[`'\"]"),
         lambda m, c: f"The error message names a fix: `{m.group(1)}`. Consider running it, then retry the step.",
         lambda m, c: m.group(1)),
    Rule("needs_root",
         re.compile(r"Permission denied|EACCES|Operation not permitted|must be run as root|[Aa]re you root"
                    r"|Read-only file system"),
         lambda m, c: ("The box runs as a non-root user and only $HOME and /tmp are writable. Use a "
                       "user-level install: an install-dir or prefix option pointing at ~/.local, "
                       "`pip install --user`, or unpack binaries into ~/.local/bin.")),
)
assert 6 <= len(RULES) <= 8


def match_rules(command: str, exit_code: int, stdout: str, stderr: str) -> list[RuleHit]:
    """Hints for a failed command, at most one per rule; empty when it succeeded."""
    if exit_code == 0:
        return []
    text = f"{stderr}\n{stdout}"
    hits: list[RuleHit] = []
    claimed_tools: set[str] = set()
    for rule in RULES:
        if rule.only_exit is not None and exit_code != rule.only_exit:
            continue
        m = rule.pattern.search(text)
        if not m:
            continue
        if rule.id == "missing_toolchain":
            claimed_tools.add(m.group(1))
        if rule.id == "not_on_path" and m.group(1) in claimed_tools:
            continue
        hits.append(RuleHit(rule.id, rule.hint(m, command), rule.suggest(m, command)))
    return hits


_NOISE = re.compile(r"0x[0-9a-fA-F]+|\d+(?:\.\d+)*|/[^\s:'\"]+")


def error_signature(exit_code: int, stdout: str, stderr: str) -> str | None:
    """A short key for "the same error again"; None for a success.

    Numbers, hex and paths are blanked so the same failure with a different
    timing or temp path still matches.
    """
    if exit_code == 0:
        return None
    lines = [line.strip() for line in (stderr or stdout).splitlines() if line.strip()]
    last = _NOISE.sub("#", lines[-1])[:200] if lines else ""
    return f"exit {exit_code}: {last}"
