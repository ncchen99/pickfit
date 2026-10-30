"""Rank the install methods a README states, before the agent picks one (P3.2).

The program lists candidates deterministically and the model only chooses
among them, so it does not install from memory. Order (sandbox-verify-design
1.2): package managers -> release binaries -> install scripts -> build from
source. Within package managers, isolated user-level installs come first;
in the macOS box Homebrew comes before them (pickfit.profiles ranks macOS
guides the same way). Methods a box cannot run (brew on Linux, docker,
commands for another OS) are kept aside with the reason, not dropped silently.
"""

from __future__ import annotations

import re
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
    "windows": {"brew": "Homebrew is not in the Windows box; kept as the macOS guide",
                "docker": "there is no Docker daemon inside the box"},
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
    "windows": {"npm": r"npm -g installs into %APPDATA%\npm, which is on the box user's PATH; no admin needed",
                "script": "download the script first and read it; do not pipe it into iex unread",
                "binary": r"unpack it under %USERPROFILE% (e.g. ~\.local\bin, on PATH); no admin needed"},
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


def _normalize(command: str) -> str:
    return " ".join(command.split())


def rank_install_methods(claims: list[InstallClaim], os: str = "linux") -> InstallPlan:
    """Order the README's install commands for a box running `os`."""
    pool: list[tuple[int, int, str, str, Origin, str | None]] = []
    skipped: list[Skipped] = []
    seen: set[str] = set()
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
    return rank_install_methods(extraction.install_methods, os)
