"""Rank the install methods a README states, before the agent picks one (P3.2).

The program lists candidates deterministically and the model only chooses
among them, so it does not install from memory. Order (sandbox-verify-design
1.2): package managers -> release binaries -> install scripts -> build from
source. Within package managers, isolated user-level installs come first;
in the macOS box Homebrew comes before them (pickfit.profiles ranks macOS
guides the same way). Methods a box cannot run (brew on Linux, docker,
commands for another OS) are kept aside with the reason, not dropped silently.
An MCP server's README often gives only the command a client runs (`npx -y pkg`,
`uvx pkg`, `pipx run pkg`); the package it names becomes a derived install.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pickfit.schema import ExtractionResult, InstallClaim

Origin = Literal["readme", "derived"]

# Lower sorts first. cargo and go compile from source and the box has no Rust or Go
# toolchain, so they sit after release binaries and install scripts.
METHOD_ORDER: dict[str, int] = {
    "brew": 9,  # only reaches the ranking on macOS
    "uv": 10, "pipx": 11, "npm": 12, "pip": 13,
    "binary": 20,
    "script": 30,
    "cargo": 40, "go": 41,
    "source": 50, "other": 51,
}
# Never run in the box for that OS; kept as guides or reasons.
NOT_IN_BOX: dict[str, dict[str, str]] = {
    "linux": {"brew": "Homebrew is not in the Linux box; kept as the macOS guide",
              "docker": "there is no Docker daemon inside the box"},
    "macos": {"docker": "there is no Docker daemon inside the box"},
}
NEEDS: dict[str, str] = {
    "cargo": "needs a Rust toolchain, which the box does not have",
    "go": "needs a Go toolchain, which the box does not have",
    "source": "build from source: slowest path, last resort",
    "script": "download the script first and read it; do not pipe it straight into a shell",
    "npm": "the box sets the npm prefix to ~/.local, so -g works without root",
}
NEEDS_BY_OS: dict[str, dict[str, str]] = {
    "macos": {"npm": "npm is Homebrew's; -g installs under /opt/homebrew, which the box user owns",
              "brew": "the box user owns /opt/homebrew, so brew works without sudo"},
}

# `pip install <one package>`, optionally `python -m` and `--user`/`-U`.
_PIP_ONE = re.compile(
    r"^\s*(?:python3?\s+-m\s+)?pip3?\s+install\s+(?:(?:--user|-U|--upgrade)\s+)*"
    r"(?P<pkg>[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9,._-]+\])?(?:[=<>~!]=?[A-Za-z0-9.*+!-]+)?)\s*$"
)


@dataclass(frozen=True)
class Candidate:
    rank: int
    method: str
    command: str
    origin: Origin  # readme: copied from the README; derived: rewritten by a rule here
    note: str | None = None


@dataclass(frozen=True)
class Skipped:
    method: str
    command: str
    reason: str


@dataclass(frozen=True)
class InstallPlan:
    candidates: list[Candidate]
    skipped: list[Skipped]

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": [asdict(c) for c in self.candidates],
                "skipped": [asdict(s) for s in self.skipped]}


def _derived_from_pip(command: str) -> list[tuple[str, str, str]]:
    """`pip install X` -> isolated `uv tool install X` and `pipx install X`."""
    m = _PIP_ONE.match(command)
    if not m:
        return []
    pkg = m.group("pkg")
    note = f"isolated install of the README's `pip install {pkg}`; avoids PEP 668 and the read-only system"
    return [("uv", f"uv tool install {pkg}", note), ("pipx", f"pipx install {pkg}", note)]


# What an MCP client runs, and the install of the package it fetches each time.
_MCP_LAUNCHERS = (
    ("npm", re.compile(r"^\s*(?:npx|bunx|pnpm\s+dlx)\s+(?:(?:-y|--yes|-q|--quiet)\s+)*(?P<pkg>[@A-Za-z0-9][@A-Za-z0-9/._~^-]*)"),
     "npm install -g {pkg}"),
    ("uv", re.compile(r"^\s*uvx\s+(?:--from\s+(?P<from>[A-Za-z0-9][^\s'\"]*)\s+)?"
                      r"(?P<pkg>[A-Za-z0-9][A-Za-z0-9._\[\],=<>~!-]*)"), "uv tool install {pkg}"),
    ("pipx", re.compile(r"^\s*pipx\s+run\s+(?:--spec\s+(?P<from>\S+)\s+)?(?P<pkg>[A-Za-z0-9][A-Za-z0-9._-]*)"),
     "pipx install {pkg}"),
)


def _derived_from_mcp_launch(launch: str | None) -> list[tuple[str, str, str]]:
    """An MCP launch command that fetches a package at start -> installing that package once."""
    for method, pattern, template in _MCP_LAUNCHERS:
        m = pattern.match(launch or "")
        if m:
            pkg = m.groupdict().get("from") or m.group("pkg")
            note = (f"installs the package the README's MCP launch command `{_normalize(launch or '')[:80]}` "
                    "fetches; then start it by its own command")
            return [(method, template.format(pkg=pkg), note)]
    return []


def mcp_launches(extraction: ExtractionResult) -> list[str]:
    """Launch commands the README gives for an MCP server: its launch command, then each client config's
    (a JSON entry's command and args, or what follows `--` in a `claude mcp add` line)."""
    mcp = extraction.mcp
    found = [mcp.launch_command.value] if mcp.launch_command.value else []
    for config in mcp.client_configs:
        text = config.snippet.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                continue
            stack = [data]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if isinstance(node.get("command"), str) and isinstance(node.get("args", []), list):
                        found.append(" ".join([node["command"], *map(str, node.get("args", []))]))
                    stack += list(node.values())
        elif " -- " in text:
            found.append(text.split(" -- ", 1)[1])
    return found


def _normalize(command: str) -> str:
    return " ".join(command.split())


def rank_install_methods(claims: list[InstallClaim], os: str = "linux",
                         derived: list[tuple[str, str, str]] | None = None) -> InstallPlan:
    """Order the README's install commands for a box running `os`, with `derived` (method, command, note)."""
    pool: list[tuple[int, int, str, str, Origin, str | None]] = []
    skipped: list[Skipped] = []
    seen: set[str] = set()
    for method, cmd, note in derived or []:
        seen.add(_normalize(cmd))
        pool.append((METHOD_ORDER.get(method, 60), len(claims), method, cmd, "derived", note))
    for index, claim in enumerate(claims):
        command = claim.command.strip()
        if claim.platforms and os not in claim.platforms:
            where = "/".join(claim.platforms)
            skipped.append(Skipped(claim.method, command, f"the README gives it for {where} only"))
            continue
        not_here = NOT_IN_BOX.get(os, NOT_IN_BOX["linux"])
        if claim.method in not_here:
            skipped.append(Skipped(claim.method, command, not_here[claim.method]))
            continue
        needs = {**NEEDS, **NEEDS_BY_OS.get(os, {})}
        entries: list[tuple[str, str, Origin, str | None]] = [
            (claim.method, command, "readme", needs.get(claim.method))]
        if claim.method == "pip":
            entries += [(method, cmd, "derived", note) for method, cmd, note in _derived_from_pip(command)]
        for method, cmd, origin, note in entries:
            key = _normalize(cmd)
            if key in seen:
                continue
            seen.add(key)
            pool.append((METHOD_ORDER.get(method, 60), index, method, cmd, origin, note))
    pool.sort(key=lambda entry: (entry[0], entry[1]))
    candidates = [Candidate(rank=i + 1, method=method, command=cmd, origin=origin, note=note)
                  for i, (_, _, method, cmd, origin, note) in enumerate(pool)]
    return InstallPlan(candidates, skipped)


def plan_for(extraction: ExtractionResult, os: str = "linux") -> InstallPlan:
    readme = {_normalize(c.command) for c in extraction.install_methods}
    derived: list[tuple[str, str, str]] = []
    for launch in mcp_launches(extraction):
        for entry in _derived_from_mcp_launch(launch):
            if _normalize(entry[1]) not in readme and all(entry[1] != d[1] for d in derived):
                derived.append(entry)
    return rank_install_methods(extraction.install_methods, os, derived)
