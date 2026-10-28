"""Which rule-passed candidates to extract first when the budget covers only some ($0).

Extraction costs about $0.014 a candidate on muse-spark-1.3, and in the first
local_ai batch 11 of 16 profiles turned out to be GUI apps or other tools a
Linux sandbox cannot verify. This ranks the candidates not yet extracted by
signals in the GitHub snapshot alone (no model): an executable entry point, a
package-manager install command, Linux release binaries, a local server or
model runner in the README, and a name or description about local models
count for; a desktop, mobile or browser-extension project, a GPU or Apple
Silicon requirement, and a coding-agent description (those are usually
dev_cli) count against. It only orders the
queue: nothing is rejected, and the model still decides kind and category.

    uv run python -m pickfit.discover.shortlist --category local_ai --limit 40

prints one `gh:<id>  score  owner/name  signals` line per candidate, best
first; the ids go to `pickfit extract --repo`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pickfit.discover.rules import _entry_points
from pickfit.discover.store import PipelineDB

DONE = ("ok", "quotes_dropped")

TOOL_INSTALL = re.compile(
    r"\b(pipx install|uv tool install|uvx |pip3? install (?!-r\b|-e\b|\.)|npm (i|install) -g|npx |"
    r"cargo (b)?install|go install|brew install)", re.I)
LINUX_ASSET = re.compile(r"linux|x86_64-unknown|\.deb$|\.rpm$", re.I)
GUI_ASSET = re.compile(r"\.(dmg|exe|msi|apk|ipa|appimage|pkg)$", re.I)
LOCAL_SERVER = re.compile(r"/v1/(models|chat|completions)|openai[- ]compatible|localhost:\d{2,5}", re.I)
LOCAL_RUNNER = re.compile(r"\bollama\b|llama\.cpp|llama-server|\bgguf\b|whisper|\bonnx|local models?\b"
                          r"|offline", re.I)
# What the repo says it is (name and description): a local runner or offline AI tool is local_ai;
# a coding agent that can also use a local model usually ends up dev_cli.
LOCAL_FOCUS = re.compile(r"\b(local|offline|on-device|private)\b.{0,40}\b(llms?|models?|inference|ai|speech|voice|"
                         r"transcri\w*|tts|stt)\b|\bgguf\b|llama\.?cpp|\bollama\b|\bwhisper|inference "
                         r"(engine|server|runtime)|speech[- ]to[- ]text|text[- ]to[- ]speech|\bquantiz", re.I)
CODING_AGENT = re.compile(r"coding[- ]agent|claude code|\bcodex\b|\bcursor\b|copilot|pair[- ]program|"
                          r"agent (harness|runtime|platform|swarm)|multi-agent|agentic", re.I)
GUI_FILE = re.compile(r"(^|/)(src-tauri/|tauri\.conf\.json$|[^/]+\.xcodeproj/|Package\.swift$|"
                      r"AndroidManifest\.xml$|pubspec\.yaml$|electron-builder\.(json|ya?ml)$)")
# A GUI project at the top of the tree is the product; one in a subdirectory is often a companion app.
TOP_GUI_FILE = re.compile(r"^(src-tauri/|tauri\.conf\.json$|[^/]+\.xcodeproj/|Package\.swift$|pubspec\.yaml$|"
                          r"electron-builder\.(json|ya?ml)$|app/src/main/AndroidManifest\.xml$)")
# Entry points one level down (workspaces, monorepos), outside GUI project directories.
NESTED_ENTRY = re.compile(r"(^|/)src/(main\.rs|bin/)|(^|/)cmd/[^/]+/main\.go$|(^|/)__main__\.py$")
GUI_DIR = re.compile(r"(^|/)(src-tauri|desktop|mobile|android|ios|macos)/", re.I)
# A self-hosted web app (compose file plus a web front end) is usually category "other".
COMPOSE_FILE = re.compile(r"^(docker-)?compose\.ya?ml$")
WEB_FRONTEND = re.compile(r"(^|/)next\.config\.\w+$|^(frontend|web|client|ui|apps/web)/package\.json$")
GUI_README = re.compile(r"desktop app|menu ?bar app|\bmenubar\b|system tray|tray icon|"
                        r"(vs ?code|chrome|firefox|browser) extension|obsidian plugin|android app|ios app",
                        re.I)
GPU_REQUIRED = re.compile(r"(requires?|needs?|must have)\s+(an?\s+)?(nvidia|cuda|gpu)\b|"
                          r"\b(cuda|nvidia gpu|gpu) (is )?required", re.I)
APPLE_ONLY = re.compile(r"apple silicon (only|required)|requires? (an? )?apple silicon|macos only|"
                        r"only (runs|works) on (macos|apple silicon)", re.I)


@dataclass
class Ranked:
    repo_id: str
    full_name: str
    score: int
    signals: list[str]
    pushed_at: str


def box_fit(candidate: dict[str, Any]) -> tuple[int, list[str]]:
    """(score, signals): how likely the candidate is a tool a Linux sandbox can run."""
    readme = candidate.get("readme") or ""
    files: list[str] = candidate.get("files") or []
    manifests: dict[str, str] = candidate.get("manifests") or {}
    assets = [a.get("name") or "" for r in candidate.get("releases") or [] for a in r.get("assets") or []]
    signals: list[tuple[str, int]] = []
    entry, _ = _entry_points(files, manifests)
    entry = [e for e in entry if e != "app project"]
    if entry:
        signals.append(("entry_point", 3))
    elif any(NESTED_ENTRY.search(f) and not GUI_DIR.search(f) for f in files):
        entry = ["nested"]
        signals.append(("nested_entry_point", 2))
    if TOOL_INSTALL.search(readme):
        signals.append(("tool_install_command", 2))
    if any(LINUX_ASSET.search(a) and not GUI_ASSET.search(a) for a in assets):
        signals.append(("linux_binaries", 2))
    if LOCAL_SERVER.search(readme):
        signals.append(("local_server", 1))
    if LOCAL_RUNNER.search(readme):
        signals.append(("local_runner", 1))
    about = " ".join(filter(None, [candidate["repo"].get("name"), candidate["repo"].get("description")]))
    if LOCAL_FOCUS.search(about):
        signals.append(("local_focus", 2))
    if CODING_AGENT.search(about):
        signals.append(("coding_agent", -2))
    if candidate.get("rule_label") == "uncertain":
        signals.append(("rules_uncertain", -1))
    package_json = manifests.get("package.json") or ""
    if any(TOP_GUI_FILE.search(f) for f in files) or re.search(r'"electron"\s*:', package_json):
        signals.append(("gui_project", -4))
    elif any(GUI_FILE.search(f) for f in files):
        signals.append(("gui_subproject", -1))
    elif GUI_README.search(readme[:6000]):
        signals.append(("gui_readme", -3))
    elif assets and all(GUI_ASSET.search(a) for a in assets) and not entry:
        signals.append(("gui_assets_only", -2))
    if any(COMPOSE_FILE.search(f) for f in files) and any(WEB_FRONTEND.search(f) for f in files):
        signals.append(("web_app", -2))
    if any(f.endswith("manifest.json") for f in files) and '"manifest_version"' in readme:
        signals.append(("browser_extension", -3))
    if GPU_REQUIRED.search(readme):
        signals.append(("gpu_required", -3))
    if APPLE_ONLY.search(readme):
        signals.append(("apple_only", -3))
    return sum(w for _, w in signals), [f"{'+' if w > 0 else ''}{w}:{name}" for name, w in signals]


def shortlist(db: PipelineDB, *, category: str, model: str = "muse-spark-1.3",
              skip_repo_ids: set[str] | None = None) -> list[Ranked]:
    """Rule-passed candidates of `category` with no finished extraction by `model`, best first."""
    skip = set(skip_repo_ids or ())
    done = {e["repo_id"] for e in db.extractions() if e["model"] == model and e["status"] in DONE}
    ranked = []
    for c in db.candidates("WHERE rule_passed = 1 AND category = ?", (category,)):
        if c["repo_id"] in done or c["repo_id"] in skip or not (c.get("readme") or "").strip():
            continue
        score, signals = box_fit(c)
        ranked.append(Ranked(c["repo_id"], c["full_name"], score, signals, c["repo"].get("pushed_at") or ""))
    ranked.sort(key=lambda r: r.pushed_at, reverse=True)
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def record_repo_ids(data_dir: Path) -> set[str]:
    ids = set()
    for path in data_dir.glob("*.json"):
        try:
            ids.add(json.loads(path.read_text(encoding="utf-8"))["repo_id"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return ids


def main(argv: list[str] | None = None) -> int:
    from pickfit.discover.run import pipeline_db_path
    from pickfit.profiles import DEFAULT_OUT

    parser = argparse.ArgumentParser(prog="python -m pickfit.discover.shortlist", description=__doc__.split("\n")[0])
    parser.add_argument("--category", required=True, choices=["dev_cli", "local_ai"])
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--min-score", type=int, default=None, help="leave out candidates below this score")
    parser.add_argument("--db", type=Path, default=None, help="pipeline database (default runs/pipeline.db)")
    parser.add_argument("--ids-only", action="store_true", help="print only the repo ids")
    args = parser.parse_args(argv)
    db = PipelineDB(args.db or pipeline_db_path())
    ranked = shortlist(db, category=args.category, skip_repo_ids=record_repo_ids(DEFAULT_OUT))
    if args.min_score is not None:
        ranked = [r for r in ranked if r.score >= args.min_score]
    for r in ranked[:args.limit]:
        print(r.repo_id if args.ids_only else f"{r.repo_id}\t{r.score:+d}\t{r.full_name}\t{' '.join(r.signals)}")
    print(f"{len(ranked)} candidates ranked, {min(len(ranked), args.limit)} shown", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
