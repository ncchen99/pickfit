"""Rule prefilter (architecture B.1): drop what is clearly not usable software, for $0.

Order: hard rejects (fork, archived, disabled, GitHub template, no README,
abuse keywords) -> not software (lists, homework, tutorials, templates,
dotfiles, demos) -> library (several signals and no strong tool signal) ->
tool -> everything else is "uncertain" and goes on to a model.

Ported from the research spike's classifier, keeping only signals from the
GitHub REST API (repo, README, releases, tree, root manifests); the spike's
third-party package index lookups are gone (its terms forbid scripted access
without written consent, plan section 5). That removed the "packaged in a
distro" signal; checking Homebrew and package registries directly is later work.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

RULES_VERSION = "rules.v1"

INSTALL_HEADING = re.compile(
    r"^#{1,4}\s*.*\b(install|installation|getting started|quick ?start|setup|download)\b"
    r"|^#{1,4}.*(安裝|下載)", re.I | re.M)
USAGE_HEADING = re.compile(
    r"^#{1,4}\s*.*\b(usage|how to use|examples?|commands?|features)\b|^#{1,4}.*(使用|用法)",
    re.I | re.M)
INSTALL_COMMAND = re.compile(
    r"\b(brew install|cargo (b)?install|pipx install|uv tool install|pip3? install|npm (i|install) -g|"
    r"npx |go install|winget install|scoop install|apt(-get)? install|yay -S|paru -S|"
    r"nix (profile install|run)|docker (run|compose)|curl [^\n|]*\|\s*(ba|z)?sh|make install|"
    r"cmake --build)", re.I)
LIBRARY_USAGE = re.compile(r"\bgo get (-u )?[\w.]+/|^\s*(from \w+ import|import \w+$)|require\(['\"]",
                           re.M)
LIBRARY_DESCRIPTION = re.compile(
    r"\b(library|sdk|framework|bindings?|api client|client for)\b|函式庫", re.I)
BINARY_ASSET = re.compile(
    r"(darwin|macos|apple|linux|windows|win64|x86_64|amd64|aarch64|arm64|\.dmg$|\.exe$|\.msi$|"
    r"\.deb$|\.rpm$|\.appimage$|\.pkg$|\.apk$)", re.I)
SOURCE_FILE = re.compile(r"\.(go|rs|py|ts|js|mjs|swift|c|cc|cpp|zig|java|kt|rb|sh|lua|cs|dart)$")
LINK_LIST_ITEM = re.compile(r"^\s*[-*] \[.+?\]\(http", re.M)
# Account farms and credential tools seen in discovery research (channels-hosting).
ABUSE = re.compile(
    r"bulk[- ]?(create|creat|register|sign[- ]?up)|account (generator|creator|farm)|"
    r"harvest(ing)? cookies|cookie (stealer|grabber)|token (grabber|stealer)|captcha (bypass|solver)|"
    r"\bstealer\b", re.I)

# (reason, pattern): matched against the repo name and topics (strong) or the description (weak).
NOT_SOFTWARE = (
    ("awesome_list", re.compile(r"^awesome[-_]|\bawesome[- ]list\b|curated list", re.I)),
    ("homework", re.compile(
        r"homework|assignment|coursework|\bcourse\b|exercises?\b|leetcode|bootcamp|作業|\blab\d", re.I)),
    ("tutorial", re.compile(
        r"tutorial|教學|cheat ?sheet|interview[- ]prep|for beginners|\d+[- ]days[- ]of|"
        r"\blearn[- ](to[- ]code|rust|go|python|javascript|react)\b", re.I)),
    ("template", re.compile(r"(^|[\s/_-])(template|starter|boilerplate|skeleton)([\s_-]|$)", re.I)),
    ("dotfiles", re.compile(r"dotfiles|my (neo)?vim config|\.config\b", re.I)),
    ("demo", re.compile(r"\bdemo\b|proof[- ]of[- ]concept|\bpoc\b|\bexamples?\b|sample", re.I)),
)
TOOL_TOPICS = frozenset({
    "cli", "command-line", "command-line-tool", "terminal", "tui", "app", "desktop-app",
    "macos-app", "self-hosted", "local-ai", "local-llm", "developer-tools", "devtools",
})
STRONG_TOOL = ("entry_point", "release_binaries")
LIBRARY_REASONS = ("npm_library_no_bin", "python_library_no_scripts", "cargo_lib_only",
                   "go_no_main", "readme_shows_library_usage", "description_says_library")
LINK_LIST_MIN = 40
# Same owner this many times in one discovery batch: worth a look, not a reject.
OWNER_BURST = 5


@dataclass
class RuleResult:
    label: str  # tool | uncertain | library | non_software | rejected
    passed: bool
    reasons: list[str] = field(default_factory=list)
    positive: int = 0
    not_software: int = 0
    library: int = 0


def _entry_points(files: list[str], manifests: dict[str, str]) -> tuple[list[str], list[tuple[str, int]]]:
    """Executable entry points found in manifests and the tree, plus library-only signals."""
    entry: list[str] = []
    negative: list[tuple[str, int]] = []
    package_json = manifests.get("package.json")
    if package_json:
        try:
            pkg = json.loads(package_json)
        except json.JSONDecodeError:
            pkg = None
        if isinstance(pkg, dict):
            if pkg.get("bin"):
                entry.append("package.json bin")
            elif pkg.get("main") or pkg.get("exports"):
                negative.append(("npm_library_no_bin", 2))
    pyproject = manifests.get("pyproject.toml") or ""
    if re.search(r"^\[project\.(scripts|gui-scripts)\]|^\[tool\.poetry\.scripts\]", pyproject, re.M):
        entry.append("pyproject scripts")
    if "console_scripts" in (manifests.get("setup.cfg") or ""):
        entry.append("setup.cfg console_scripts")
    cargo = manifests.get("Cargo.toml") or ""
    if "src/main.rs" in files or any(f.startswith("src/bin/") for f in files) or "[[bin]]" in cargo:
        entry.append("cargo bin")
    go_main = "main.go" in files or any(re.match(r"cmd/[^/]+/main\.go$", f) for f in files)
    if go_main:
        entry.append("go main")
    if any(f.endswith((".xcodeproj/project.pbxproj", "tauri.conf.json", "Package.swift")) for f in files):
        entry.append("app project")
    if not entry:
        if "[project]" in pyproject:
            negative.append(("python_library_no_scripts", 1))  # weak: many apps run via python -m
        elif cargo and "src/lib.rs" in files:
            negative.append(("cargo_lib_only", 2))
        elif "go.mod" in files and not go_main:
            negative.append(("go_no_main", 2))
    return entry, negative


def _hard_rejects(repo: dict[str, Any], readme: str | None) -> list[str]:
    reasons = [name for name, hit in (
        ("fork", repo.get("fork")),
        ("archived", repo.get("archived")),
        ("disabled", repo.get("disabled")),
        ("github_template", repo.get("is_template")),
    ) if hit]
    if not (readme or "").strip():
        reasons.append("no_readme")
    text = " ".join(filter(None, [repo.get("name"), repo.get("description")]))
    if ABUSE.search(text):
        reasons.append("abuse_keywords")
    return reasons


def classify(candidate: dict[str, Any], owner_counts: dict[str, int] | None = None) -> RuleResult:
    """Label one candidate (a store row: `repo` snapshot plus README, releases, files, manifests)."""
    repo = candidate["repo"]
    readme = candidate.get("readme")
    files: list[str] = candidate.get("files") or []
    manifests: dict[str, str] = candidate.get("manifests") or {}
    releases: list[dict[str, Any]] = candidate.get("releases") or []
    notes: list[str] = []
    if owner_counts and owner_counts.get(repo.get("owner") or "", 0) >= OWNER_BURST:
        notes.append(f"flag:owner_burst({owner_counts[repo['owner']]})")

    hard = _hard_rejects(repo, readme)
    if hard:
        return RuleResult("rejected", False, [f"reject:{r}" for r in hard] + notes)

    readme = readme or ""
    positive: list[tuple[str, int]] = []
    negative: list[tuple[str, int]] = []
    if INSTALL_HEADING.search(readme):
        positive.append(("readme_install_section", 2))
    if USAGE_HEADING.search(readme):
        positive.append(("readme_usage_section", 1))
    has_install_command = bool(INSTALL_COMMAND.search(readme))
    if has_install_command:
        positive.append(("readme_install_command", 2))
    if any(BINARY_ASSET.search(a["name"] or "") for r in releases for a in r.get("assets") or []):
        positive.append(("release_binaries", 3))
    entry, library_signals = _entry_points(files, manifests)
    if entry:
        positive.append(("entry_point:" + ",".join(entry), 3))
    negative += library_signals
    if LIBRARY_USAGE.search(readme) and not has_install_command:
        negative.append(("readme_shows_library_usage", 2))
    topics = set(repo.get("topics") or [])
    if TOOL_TOPICS & topics:
        positive.append(("tool_topic", 1))

    name_and_topics = " ".join([repo.get("name") or "", *sorted(topics)])
    description = repo.get("description") or ""
    for reason, pattern in NOT_SOFTWARE:
        if pattern.search(name_and_topics):
            negative.append((reason, 4 if reason != "demo" else 2))
        elif pattern.search(description):
            negative.append((reason, 2))
    if LIBRARY_DESCRIPTION.search(description):
        negative.append(("description_says_library", 2))
    if files and not candidate.get("files_truncated") and not any(SOURCE_FILE.search(f) for f in files):
        negative.append(("no_source_files", 4))
    links = len(LINK_LIST_ITEM.findall(readme))
    if links > LINK_LIST_MIN:
        negative.append((f"readme_is_link_list({links})", 3))

    def is_library(reason: str) -> bool:
        return reason in LIBRARY_REASONS

    strong = any(name.startswith(STRONG_TOOL) for name, _ in positive)
    p = sum(w for _, w in positive)
    n = sum(w for name, w in negative if not is_library(name))
    lib = sum(w for name, w in negative if is_library(name))
    if n >= 4 and n >= p:
        label = "non_software"
    elif lib >= 4 and not strong:
        label = "library"
    elif n < 4 and lib < 2 and (strong or p >= 4):
        label = "tool"
    else:
        label = "uncertain"
    passed = label in ("tool", "uncertain")
    reasons = ([f"+{name}" for name, _ in positive] + [f"-{name}" for name, _ in negative]
               + ([] if passed else [f"reject:{label}"]) + notes)
    return RuleResult(label, passed, reasons, positive=p, not_software=n, library=lib)
