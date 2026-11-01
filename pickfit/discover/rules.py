"""Rule prefilter (architecture B.1): drop what is clearly not usable software, for $0.

Order: hard rejects (fork, archived, disabled, GitHub template, no README,
abuse keywords, the lure-kit file pattern) -> not software (lists, homework,
tutorials, templates, dotfiles, demos) -> library (several signals and no
strong tool signal) -> tool -> everything else is "uncertain". A tool or
uncertain repo is still rejected when there is nothing to verify: no source
files at all (README-only), release binaries without their source or a
license (binary-only), or no install, usage, entry point or binary signal.
What passes goes on to a model.

A candidate listed by a package store (Flathub, Homebrew Cask; the store row's `listings`)
has a strong tool signal: the store installs it as an app. Its store text stands in for a
missing README.

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

RULES_VERSION = "rules.v3"  # v3: a package-store listing is a strong tool signal; Vala and QML are source

INSTALL_HEADING = re.compile(
    r"^#{1,4}\s*.*\b(install|installation|get(ting)? started|quick ?start|setup|download|build(ing)?)\b"
    r"|^#{1,4}.*(安裝|安装|下載|下载|快速開始|快速开始|インストール|導入|セットアップ|ビルド|설치)",
    re.I | re.M)
USAGE_HEADING = re.compile(
    r"^#{1,4}\s*.*\b(usage|how to use|examples?|commands?|features)\b"
    r"|^#{1,4}.*(使用|用法|使い方|操作|사용법)",
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
SOURCE_FILE = re.compile(
    r"\.(go|rs|py|ts|tsx|js|jsx|mjs|cjs|vue|svelte|swift|m|mm|c|h|cc|cpp|hpp|zig|java|kt|scala|rb|php|"
    r"pl|ex|exs|erl|hs|ml|fs|clj|el|jl|nim|cr|v|pas|sh|bash|zsh|fish|ps1|lua|cs|dart|nix|vala|qml)$")
LINK_LIST_ITEM = re.compile(r"^\s*[-*] \[.+?\]\(http", re.M)
# Account farms and credential tools seen in discovery research (channels-hosting).
ABUSE = re.compile(
    r"bulk[- ]?(create|creat|register|sign[- ]?up)|account (generator|creator|farm)|"
    r"harvest(ing)? cookies|cookie (stealer|grabber)|token (grabber|stealer)|captcha (bypass|solver)|"
    r"\bstealer\b", re.I)

# The lure kit seen in discovery (channels-hosting; P2 hand-over): README + index.html, a
# .github/<random letters> file with no extension and .github/workflows/<random letters>.yml,
# star-farmed, an SEO title. Real files directly under .github/ are named in capitals
# (CODEOWNERS) or have an extension, so a mixed-case extensionless name is the kit's marker.
_GITHUB_MARKER = re.compile(r"^\.github/(?=(?:[a-z]*[A-Z]){2})(?=(?:[A-Z]*[a-z]){2})[A-Za-z]{10,20}$")
_WORKFLOW_STEM = re.compile(r"^\.github/workflows/([A-Za-z]{10,20})\.ya?ml$")
SEO_TITLE = re.compile(
    r"\b20[2-3]\d\b.*\b(best|top|ultimate|free|download|next[- ]gen)\b"
    r"|\b(best|top|ultimate|free|download|next[- ]gen)\b.*\b20[2-3]\d\b", re.I)
NAME_WITH_YEAR = re.compile(r"[-_]20[2-3]\d$")

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
STRONG_TOOL = ("entry_point", "release_binaries", "listed")
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


def _random_token(word: str) -> bool:
    """Letters that are not words: several capitals, and capitals in a row or vowelless chunks.

    Words in camelCase (onPushToMain) have a vowel in every chunk; an acronym (BuildAndTestCI)
    can look random, so this alone is only used together with a missing license.
    """
    capitals = sum(ch.isupper() for ch in word)
    if not 4 <= capitals < len(word):
        return False
    if re.search(r"[A-Z]{2}", word):
        return True
    chunks = re.findall(r"[A-Z]?[a-z]+", word)
    return sum(1 for c in chunks if len(c) >= 2 and not re.search(r"[aeiouy]", c, re.I)) >= 2


def _lure_kit(files: list[str], repo: dict[str, Any]) -> bool:
    """The kit's .github marker file, or a random workflow name in a repo with no license."""
    if any(_GITHUB_MARKER.match(f) for f in files):
        return True
    workflow = any((m := _WORKFLOW_STEM.match(f)) and _random_token(m.group(1)) for f in files)
    return workflow and not repo.get("license")


def _hard_rejects(repo: dict[str, Any], readme: str | None, files: list[str], listed: bool = False) -> list[str]:
    reasons = [name for name, hit in (
        ("fork", repo.get("fork")),
        ("archived", repo.get("archived")),
        ("disabled", repo.get("disabled")),
        ("github_template", repo.get("is_template")),
    ) if hit]
    if not (readme or "").strip() and not listed:
        reasons.append("no_readme")
    text = " ".join(filter(None, [repo.get("name"), repo.get("description")]))
    if ABUSE.search(text):
        reasons.append("abuse_keywords")
    if _lure_kit(files, repo):
        reasons.append("suspected_lure")
    return reasons


def classify(candidate: dict[str, Any], owner_counts: dict[str, int] | None = None) -> RuleResult:
    """Label one candidate (a store row: `repo` snapshot plus README, releases, files, manifests)."""
    repo = candidate["repo"]
    readme = candidate.get("readme")
    files: list[str] = candidate.get("files") or []
    manifests: dict[str, str] = candidate.get("manifests") or {}
    releases: list[dict[str, Any]] = candidate.get("releases") or []
    stores = sorted({x["source"] for x in candidate.get("listings") or []})
    notes: list[str] = []
    if owner_counts and owner_counts.get(repo.get("owner") or "", 0) >= OWNER_BURST:
        notes.append(f"flag:owner_burst({owner_counts[repo['owner']]})")

    hard = _hard_rejects(repo, readme, files, listed=bool(stores))
    if hard:
        return RuleResult("rejected", False, [f"reject:{r}" for r in hard] + notes)

    readme = readme or ""
    positive: list[tuple[str, int]] = []
    negative: list[tuple[str, int]] = []
    if stores:
        positive.append(("listed:" + ",".join(stores), 3))
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
    if SEO_TITLE.search(description) or NAME_WITH_YEAR.search(repo.get("name") or ""):
        negative.append(("seo_title", 3))
    source_files = sum(1 for f in files if SOURCE_FILE.search(f))
    tree_known = bool(files) and not candidate.get("files_truncated")
    if tree_known and source_files == 0:
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
    # Nothing a sandbox could verify: these never reach the model or the sandbox.
    nothing_to_verify = None
    if label in ("tool", "uncertain"):
        has_binaries = any(name == "release_binaries" for name, _ in positive)
        if tree_known and source_files == 0:
            nothing_to_verify = "readme_only"
        elif has_binaries and tree_known and source_files <= 2 and not entry and not repo.get("license"):
            nothing_to_verify = "binary_only"
        elif label == "uncertain" and p <= 1:
            nothing_to_verify = "no_install_or_usage_signal"
    if nothing_to_verify:
        label = "rejected"
    passed = label in ("tool", "uncertain")
    reasons = ([f"+{name}" for name, _ in positive] + [f"-{name}" for name, _ in negative]
               + ([] if passed else [f"reject:{nothing_to_verify or label}"]) + notes)
    return RuleResult(label, passed, reasons, positive=p, not_software=n, library=lib)
