"""Turn stored extractions into canonical records: data/software/<slug>.json (P2.6).

Facts an API provides come from the GitHub snapshot in runs/pipeline.db, never
from the model: the repository, license, latest release, dates, topics (tags),
homepage and earlier names. The extraction supplies only what the sources say
(summary, kind, category, platforms, prerequisites, use cases, install claims),
and each such value keeps its verbatim quote, the source it was found in and the
model that read it, in `evidence`.

Records start unverified. Install commands are kept as `readme_claim` guides,
which the index never serves; verification (P3) adds runs and replayed guides.
Writing again keeps what verification and scoring added to an existing record
(verification, replayed or human guides, scores, outcomes) and its slug and
first_seen_at, and its features when the extraction lists none (they came from
a features-only extraction).

A candidate found through Show HN also lists each post as a source of kind `hn`:
where pickfit found the tool, not evidence for any field.

Only tools for end users are written (TOOL_KINDS, not import_only), by default
only in the listed categories (dev_cli, local_ai, mcp_server). An MCP server also
gets `mcp`: transports, launch command, client config snippets, environment
variables and tool names, each kept only when its text is in the sources.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pickfit.discover.store import PipelineDB
from pickfit.extract import Source as ExtractSource
from pickfit.extract import build_sources, feature_rows, normalize_for_match
from pickfit.ledger import taipei_now
from pickfit.schema import (
    COMMAND_MAX,
    LISTED_CATEGORIES,
    TOOL_KINDS,
    ExtractedFeatures,
    ExtractionResult,
    InstallClaim,
    SoftwareRecord,
)
from pickfit.score import refresh_scores

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "software"
DEFAULT_CATEGORIES = LISTED_CATEGORIES
DONE = ("ok", "quotes_dropped")
SUMMARY_MAX = 200
MAX_TAGS = 10

_TAG = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,30}$")
_WEB_URL = re.compile(r"^https?://[^\s/?#]+[^\s]*$")
_SLUG_JUNK = re.compile(r"[^a-z0-9]+")

# SPDX ids GitHub reports for common OSI-approved licenses (and public-domain dedications).
OPEN_SOURCE_LICENSES = frozenset({
    "0BSD", "AFL-3.0", "AGPL-3.0", "Apache-2.0", "Artistic-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "BSD-3-Clause-Clear", "BSL-1.0", "CC0-1.0", "ECL-2.0", "EPL-1.0", "EPL-2.0", "EUPL-1.1",
    "EUPL-1.2", "GPL-2.0", "GPL-3.0", "ISC", "LGPL-2.1", "LGPL-3.0", "MIT", "MIT-0", "MPL-2.0",
    "MS-PL", "MS-RL", "MulanPSL-2.0", "NCSA", "OSL-3.0", "PostgreSQL", "UPL-1.0", "Unlicense",
    "Zlib",
})
# Source-available or non-commercial: code is visible, but not open source.
NOT_OPEN_SOURCE_LICENSES = frozenset({
    "BUSL-1.1", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0", "Elastic-2.0", "SSPL-1.0",
    "PolyForm-Noncommercial-1.0.0", "PolyForm-Shield-1.0.0",
})

# Install claims per OS, best first. Only `uv tool install` / `uvx` install a tool;
# `uv add` and `uv pip install` rank with pip.
OS_METHOD_ORDER: dict[str, tuple[str, ...]] = {
    "macos": ("brew", "uv", "pipx", "npm", "cargo", "go", "pip", "binary", "script", "docker",
              "source", "other"),
    "linux": ("uv", "pipx", "npm", "pip", "binary", "script", "cargo", "go", "brew", "docker",
              "source", "other"),
    "windows": ("uv", "pipx", "npm", "pip", "binary", "script", "cargo", "go", "docker", "source",
                "other"),
}
_UV_TOOL = re.compile(r"^\s*(uv\s+tool\s+install|uvx)\b")
# Steps that only work inside a clone of the repo (one step of a longer build, not an install).
_NEEDS_CHECKOUT = re.compile(
    r"^\s*(\./|sh\s+\./|bash\s+\./|make\b|cmake\b|cargo\s+(build|run)\b|go\s+(build|run)\b|npm\s+ci\b"
    r"|npm\s+(i|install)\s*$|pnpm\s+(i|install)\s*$|yarn\s*$|bun\s+install\s*$|git\s+clone\b"
    r"|(npm|pnpm|yarn|bun)\s+(run\s+)?(dev|start|build|test)\b|docker[- ]compose\s+up\b|docker\s+compose\s+up\b)"
    r"|\s-r\s+\S*requirements|\s-e\s+\.(\s|$|\[)|\sinstall\s+\.(\s|$|\[)")
_POSIX_SHELL = re.compile(r"\b(bash|sh|zsh)\b|\bchmod\b|^\s*\./|\|\s*(sudo\s+)?(ba|z)?sh\b")
_POWERSHELL = re.compile(r"\b(irm|iwr|iex|powershell|pwsh|Invoke-WebRequest|Invoke-Expression)\b", re.I)
_BREW_TAP = re.compile(r"^\s*brew\s+tap\s")
# A package-manager command for this tool names it; one that does not installs something else
# (a prerequisite such as llama.cpp, or a test dependency such as pytest).
PACKAGE_METHODS = frozenset({"brew", "npm", "pip", "pipx", "uv", "cargo", "go"})
_NAME_SUFFIX = re.compile(r"(cli|app|mcp|server|tui)$")

# Extraction source ids -> record source ids (release ids carry the tag).
_API_SOURCE = "github_api"


@dataclass
class WriteSummary:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # full_name -> reason

    def to_dict(self) -> dict[str, Any]:
        return {"written": len(self.written), "unchanged": len(self.unchanged),
                "skipped": len(self.skipped),
                "skip_reasons": dict(Counter(r.split(":")[0] for r in self.skipped.values())),
                "slugs": self.written, "skipped_repos": self.skipped}


def slugify(name: str) -> str:
    return _SLUG_JUNK.sub("-", name.lower()).strip("-")[:64].strip("-")


def open_source_from_license(spdx: str | None) -> bool | None:
    if spdx in OPEN_SOURCE_LICENSES:
        return True
    if spdx in NOT_OPEN_SOURCE_LICENSES:
        return False
    return None


def _newest_release(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """GitHub's 'latest release': the newest one that is not a prerelease."""
    return next((r for r in candidate.get("releases") or []
                 if not r.get("prerelease") and r.get("published_at") and r.get("tag")), None)


class _Evidence:
    """Collects FieldEvidence entries and finds which source holds a quote."""

    def __init__(self, sources: list[ExtractSource], source_ids: dict[str, str], model: str,
                 extracted_at: str) -> None:
        self._hay = [(source_ids[s.id], normalize_for_match(s.text)) for s in sources
                     if s.id in source_ids]
        self.model = model
        self.extracted_at = extracted_at
        self.items: list[dict[str, Any]] = []

    def where(self, quote: str) -> str | None:
        needle = normalize_for_match(quote)
        return next((sid for sid, hay in self._hay if needle and needle in hay), None)

    def model_value(self, pointer: str, quote: str) -> bool:
        """Record a model value's evidence; False when its quote is in no source (drop the value)."""
        source_id = self.where(quote)
        if source_id is None:
            return False
        self.items.append({"field": pointer, "source_id": source_id, "quote": quote[:300],
                           "method": "model", "model": self.model, "checked_at": self.extracted_at})
        return True

    def api(self, pointer: str, source_id: str, checked_at: str, method: str = "api") -> None:
        self.items.append({"field": pointer, "source_id": source_id, "quote": None,
                           "method": method, "model": None, "checked_at": checked_at})


def _claim_rank(os_name: str, claim: InstallClaim) -> int:
    method = claim.method
    if method == "uv" and not _UV_TOOL.match(claim.command):
        method = "pip"
    order = OS_METHOD_ORDER[os_name]
    return order.index(method) if method in order else len(order)


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _names_tool(command: str, names: list[str]) -> bool:
    squashed = _squash(command)
    for name in names:
        token = _squash(name)
        for variant in (token, _NAME_SUFFIX.sub("", token)):
            if len(variant) >= 3 and variant in squashed:
                return True
    return False


def _fits_os(claim: InstallClaim, os_name: str, platforms: list[str]) -> bool:
    """The README gives this command for os_name, or names no OS and the tool claims os_name."""
    if os_name in claim.platforms:
        return True
    if claim.platforms or os_name not in platforms:
        return False
    if os_name == "windows":
        return not _POSIX_SHELL.search(claim.command) and claim.method != "brew"
    return not _POWERSHELL.search(claim.command)


def _readme_guides(result: ExtractionResult, platforms: list[str], names: list[str],
                   ev: _Evidence) -> dict[str, Any]:
    """One readme_claim guide per OS the README gives a standalone install command for.

    Commands that only work inside a clone (npm ci, pip install -e ., ./install.sh) are one
    step of a source build, so they are left to verification rather than shown as an install.
    """
    smoke = result.smoke_test_candidates
    check = next(({"command": s.command, "expected_signal": s.expected_output}
                  for s in smoke if s.expected_output and s.expected_output.strip()), None)
    first_task = smoke[0].command if smoke and len(smoke[0].command) <= 300 else None
    manual = [m.value for m in result.manual_steps if m.value]
    guides: dict[str, Any] = {}
    for os_name in OS_METHOD_ORDER:
        claims = [c for c in result.install_methods if _fits_os(c, os_name, platforms)
                  and not _NEEDS_CHECKOUT.search(c.command)
                  and (c.method not in PACKAGE_METHODS or _BREW_TAP.match(c.command)
                       or _names_tool(c.command, names))
                  and _claim_rank(os_name, c) < len(OS_METHOD_ORDER[os_name])]
        if not claims:
            continue
        best = min(claims, key=lambda c: _claim_rank(os_name, c))
        steps = [best]
        if _BREW_TAP.match(best.command):  # a tap is followed by its brew install
            after = claims[claims.index(best) + 1:]
            follow = next((c for c in after if c.method == "brew" and not _BREW_TAP.match(c.command)), None)
            if follow is None:
                continue
            steps.append(follow)
        if not all(ev.model_value(f"/install/{os_name}/steps/{i}", c.command)
                   for i, c in enumerate(steps)):
            continue
        guides[os_name] = {"basis": "readme_claim", "run_id": None, "method": best.method,
                           "steps": [{"command": c.command, "purpose": None} for c in steps],
                           "manual_steps": manual, "check": check, "first_task": first_task}
    return guides


def _mcp_section(result: ExtractionResult, ev: _Evidence) -> dict[str, Any]:
    """The record's mcp facts: only what a quote (or the verbatim snippet itself) shows in the sources."""
    mcp = result.mcp
    transports = mcp.transports.value or []
    if transports and not ev.model_value("/mcp/transports", mcp.transports.quote or ""):
        transports = []
    launch = mcp.launch_command.value
    if launch and (len(launch) > COMMAND_MAX or not ev.model_value("/mcp/launch_command", mcp.launch_command.quote or "")):
        launch = None
    configs = []
    for claim in mcp.client_configs[:3]:
        if ev.model_value(f"/mcp/client_configs/{len(configs)}", claim.snippet):
            configs.append({"client": claim.client, "snippet": claim.snippet})
    env_vars: list[dict[str, Any]] = []
    for claim in mcp.env_vars:
        if len(env_vars) < 10 and claim.name not in {e["name"] for e in env_vars} \
                and ev.model_value(f"/mcp/env_vars/{len(env_vars)}", claim.name):
            purpose = " ".join((claim.purpose or "").split())[:120] or None
            env_vars.append({"name": claim.name, "required": claim.required, "purpose": purpose})
    tools: list[str] = []
    for item in mcp.tools:
        name = (item.value or "").strip()
        if name and len(tools) < 30 and len(name) <= 80 and name not in tools \
                and ev.model_value(f"/mcp/tools/{len(tools)}", item.quote or ""):
            tools.append(name)
    return {"transports": sorted(set(transports)), "launch_command": launch, "client_configs": configs,
            "env_vars": env_vars, "tools": tools}


def _summary(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SUMMARY_MAX:
        return text
    cut = text[:SUMMARY_MAX - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def build_record(candidate: dict[str, Any], extraction: dict[str, Any], *, slug: str,
                 now: datetime, existing: dict[str, Any] | None = None,
                 found_in: list[dict[str, Any]] | None = None) -> SoftwareRecord:
    """One record from a candidate row and its extraction row. Raises ValueError to skip.

    found_in: the candidate's Show HN posts (channel_hits rows), listed as `hn` sources.
    """
    result = ExtractionResult.model_validate(extraction["result"])
    repo = candidate["repo"]
    full_name = repo.get("full_name") or candidate["full_name"]
    model = extraction["model"]
    seen_at = candidate["last_seen_at"]
    details_at = candidate["details_at"]

    sources = build_sources(candidate)  # the exact text the model read
    release = _newest_release(candidate)
    source_ids = {"description": _API_SOURCE, "readme": "readme"}
    record_sources = [{"id": _API_SOURCE, "kind": "github_api",
                       "url": f"https://api.github.com/repos/{full_name}", "fetched_at": seen_at}]
    readme = next((s for s in sources if s.id == "readme"), None)
    if readme:
        record_sources.append({"id": "readme", "kind": "readme", "url": readme.url,
                               "fetched_at": details_at})
    shown = next((s for s in sources if s.id == "release"), None)
    if shown or release:
        rel = release or next(r for r in candidate["releases"] if r.get("url") == shown.url)
        rid = f"release:{rel['tag']}"
        source_ids["release"] = rid
        record_sources.append({"id": rid, "kind": "release", "url": rel.get("url"),
                               "fetched_at": details_at})
    ev = _Evidence(sources, source_ids, model, extraction["created_at"])

    def cited(name: str, value: Any, quote: str | None) -> Any:
        if value is None or value == [] or quote is None:
            return None
        return value if ev.model_value(name, quote) else None

    def cited_list(name: str, items: list[Any]) -> list[str]:
        kept: list[str] = []
        for item in items:
            if item.value and item.value not in kept and ev.model_value(f"{name}/{len(kept)}", item.quote):
                kept.append(item.value)
        return kept

    kind = cited("/kind", result.kind.value, result.kind.quote)
    if kind not in TOOL_KINDS:
        raise ValueError(f"not_a_tool: kind {kind}")
    audience = cited("/audience", result.audience.value, result.audience.quote)
    if audience == "import_only":
        raise ValueError("not_a_tool: import_only")
    category = cited("/category", result.category.value, result.category.quote)
    if category is None:  # the model could not tell: fall back to the discovery query's category
        category = candidate["category"]
        ev.api("/category", _API_SOURCE, seen_at, method="rule")

    summary = cited("/summary", result.summary.value, result.summary.quote)
    if summary:
        summary = _summary(summary)
    elif repo.get("description"):
        summary = _summary(repo["description"])
        ev.api("/summary", _API_SOURCE, seen_at)
    else:
        raise ValueError("no_summary")
    name = cited("/name", result.name.value, result.name.quote)
    if not name or len(name) > 100:
        name = repo.get("name") or full_name.split("/")[1]
        ev.api("/name", _API_SOURCE, seen_at)

    platforms = cited("/platforms", result.platforms.value, result.platforms.quote) or []
    pre = result.prerequisites
    min_ram = cited("/prerequisites/min_ram_gb", pre.min_ram_gb.value, pre.min_ram_gb.quote)
    prerequisites = {
        "runtimes": cited_list("/prerequisites/runtimes", pre.runtimes),
        "system_packages": cited_list("/prerequisites/system_packages", pre.system_packages),
        "gpu": cited("/prerequisites/gpu", pre.gpu.value, pre.gpu.quote),
        "apple_silicon_only": cited("/prerequisites/apple_silicon_only", pre.apple_silicon_only.value,
                                    pre.apple_silicon_only.quote),
        "min_ram_gb": min_ram if min_ram is None or min_ram >= 0 else None,
        "network": cited("/prerequisites/network", pre.network.value, pre.network.quote),
        "api_keys": cited_list("/prerequisites/api_keys", pre.api_keys),
    }

    # API facts.
    license_id = repo.get("license")
    ev.api("/repo", _API_SOURCE, seen_at)
    ev.api("/license", _API_SOURCE, seen_at)
    ev.api("/open_source", _API_SOURCE, seen_at, method="rule")
    homepage = repo.get("homepage") if _WEB_URL.match(repo.get("homepage") or "") else None
    if homepage:
        ev.api("/homepage", _API_SOURCE, seen_at)
    tags = [t for t in repo.get("topics") or [] if _TAG.match(t)][:MAX_TAGS]
    if tags:
        ev.api("/tags", _API_SOURCE, seen_at)
    last_release = None
    if release:
        last_release = {"tag": release["tag"][:100], "published_at": release["published_at"],
                        "url": release.get("url")}
        ev.api("/last_release", f"release:{release['tag']}", details_at)
    aliases = list(candidate.get("aliases") or [])
    if aliases:
        ev.api("/aliases", _API_SOURCE, seen_at)

    data: dict[str, Any] = {
        "slug": slug,
        "repo_id": candidate["repo_id"],
        "name": name,
        "summary": summary,
        "aliases": aliases,
        "status": "listed",
        "status_reason": None,
        "category": category,
        "kind": kind,
        "audience": audience,
        "maturity": cited("/maturity", result.maturity.value, result.maturity.quote),
        "tags": tags,
        "use_cases": cited_list("/use_cases", result.use_cases),
        "alternatives_to": cited_list("/alternatives_to", result.alternatives_to),
        "features": cited_list("/features", result.features),
        "why_worth_it": None,
        "homepage": homepage,
        "repo": {"url": repo.get("html_url") or f"https://github.com/{full_name}",
                 "full_name": full_name, "created_at": repo.get("created_at"),
                 "archived": bool(repo.get("archived"))},
        "platforms": platforms,
        "prerequisites": prerequisites,
        "install": _readme_guides(result, platforms, [repo.get("name") or "", name], ev),
        "pricing": {"model": cited("/pricing", result.pricing.value, result.pricing.quote),
                    "note": None},
        "open_source": open_source_from_license(license_id),
        "license": license_id,
        "processing": cited("/processing", result.processing.value, result.processing.quote),
        "last_release": last_release,
        "verification": {"level": "unverified", "unverified_reason": "not_run", "checked_at": None,
                         "runs": []},
        "mcp": _mcp_section(result, ev) if category == "mcp_server" else None,
        "sources": record_sources,
        "evidence": ev.items,
        "first_seen_at": candidate["first_seen_at"],
        "updated_at": now.isoformat(timespec="seconds"),
    }
    if existing:
        _keep_verified_work(data, existing)
        # A newer snapshot can change what the cap depends on (archived): refresh, no model call.
        refresh_scores(data, now)
    listed = {s["id"] for s in data["sources"]}
    for hit in found_in or []:  # last, so the index's first few source URLs stay the project's own
        if f"hn:{hit['item_id']}" not in listed:
            data["sources"].append({"id": f"hn:{hit['item_id']}", "kind": "hn", "url": hit["item_url"],
                                    "fetched_at": hit["last_seen_at"]})
            listed.add(f"hn:{hit['item_id']}")
    return SoftwareRecord.model_validate(data)


def _keep_verified_work(data: dict[str, Any], existing: dict[str, Any]) -> None:
    """Carry over what verification and scoring wrote; extraction does not own those fields."""
    data["first_seen_at"] = existing.get("first_seen_at") or data["first_seen_at"]
    for key in ("verification", "scores", "outcomes", "why_worth_it", "status", "status_reason"):
        if existing.get(key) is not None:
            data[key] = existing[key]
    for os_name, guide in (existing.get("install") or {}).items():
        if guide and guide.get("basis") != "readme_claim":
            data["install"][os_name] = guide
    kept_runs = {s["id"] for s in existing.get("sources") or []} - {s["id"] for s in data["sources"]}
    data["sources"] += [s for s in existing.get("sources") or [] if s["id"] in kept_runs]
    run_evidence = [e for e in existing.get("evidence") or [] if e.get("method") in ("sandbox", "human")]
    data["evidence"] += run_evidence
    if not data.get("features") and existing.get("features"):  # set from a features-only extraction
        data["features"] = existing["features"]
        sources = {s["id"] for s in data["sources"]}
        data["evidence"] += [e for e in existing.get("evidence") or []
                             if e["field"].startswith("/features/") and e["source_id"] in sources]


def feature_update(candidate: dict[str, Any], extraction: dict[str, Any], existing: dict[str, Any]
                   ) -> dict[str, Any] | None:
    """The existing record with only its features (and their evidence) taken from `extraction`.

    None when the extraction lists no feature a source the record cites still holds. Everything
    else in the record stays as it is, so verification and scores are untouched.
    """
    result = ExtractedFeatures.model_validate({"features": (extraction["result"] or {}).get("features") or []})
    cited_ids = {s["id"] for s in existing.get("sources") or []}
    source_ids = {"description": _API_SOURCE, "readme": "readme"}
    release = next((s for s in build_sources(candidate) if s.id == "release"), None)
    if release is not None:
        source_ids["release"] = next((sid for sid in cited_ids if sid.startswith("release:")), "release")
    source_ids = {k: v for k, v in source_ids.items() if v in cited_ids}
    ev = _Evidence(build_sources(candidate), source_ids, extraction["model"], extraction["created_at"])
    features: list[str] = []
    for item in result.features:
        if item.value and item.value not in features and ev.model_value(f"/features/{len(features)}", item.quote):
            features.append(item.value)
    if not features:
        return None
    data = json.loads(json.dumps(existing))
    data["features"] = features
    data["evidence"] = [e for e in data["evidence"] if not e["field"].startswith("/features/")] + ev.items
    return data


def write_features(db: PipelineDB, *, model: str, out_dir: Path = DEFAULT_OUT, slugs: list[str] | None = None,
                   dry_run: bool = False, now: datetime | None = None,
                   log: Callable[[str], None] | None = None) -> WriteSummary:
    """Set `features` on existing records from the newest extraction by `model` that lists them (a
    features-only one, or a full one); nothing else changes."""
    log = log or (lambda line: None)
    now = now or taipei_now()
    summary = WriteSummary()
    for repo_id, data in _existing_records(out_dir).items():
        if slugs and data["slug"] not in slugs:
            continue
        extraction = feature_rows(db, repo_id, model)
        if extraction is None:
            summary.skipped[data["slug"]] = f"no extraction with features by {model}"
            continue
        updated = feature_update(db.candidate(repo_id), extraction, data)
        if updated is None:
            summary.skipped[data["slug"]] = "no quoted feature"
            continue
        if updated["features"] == data.get("features"):
            summary.unchanged.append(data["slug"])
            continue
        updated["updated_at"] = now.isoformat(timespec="seconds")
        record = SoftwareRecord.model_validate(updated)
        if not dry_run:
            (out_dir / f"{record.slug}.json").write_text(render(record), encoding="utf-8")
        summary.written.append(record.slug)
        log(f"  {'would set' if dry_run else 'set'} {len(record.features)} features on {record.slug}")
    return summary


def latest_extractions(db: PipelineDB, model: str) -> dict[str, dict[str, Any]]:
    """The newest usable extraction per repo by `model`."""
    latest: dict[str, dict[str, Any]] = {}
    for e in db.extractions():
        if e["model"] == model and e["status"] in DONE and e["result"]:
            latest[e["repo_id"]] = e
    return latest


def _existing_records(out_dir: Path) -> dict[str, dict[str, Any]]:
    """repo_id -> existing record JSON."""
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(out_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        found[data["repo_id"]] = data
    return found


def render(record: SoftwareRecord) -> str:
    return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def write_profiles(db: PipelineDB, *, model: str, out_dir: Path = DEFAULT_OUT,
                   categories: tuple[str, ...] = DEFAULT_CATEGORIES, dry_run: bool = False,
                   now: datetime | None = None,
                   log: Callable[[str], None] | None = None) -> WriteSummary:
    """Write one record per usable extraction by `model`; returns what was written and skipped."""
    log = log or (lambda line: None)
    now = now or taipei_now()
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = _existing_records(out_dir)
    taken = {data["slug"]: repo_id for repo_id, data in existing.items()}
    summary = WriteSummary()
    extractions = latest_extractions(db, model)
    found_in: dict[str, list[dict[str, Any]]] = {}
    for hit in db.channel_hits("show_hn"):
        if hit["outcome"] == "candidate":
            found_in.setdefault(hit["repo_id"], []).append(hit)
    candidates = sorted((db.candidate(repo_id) for repo_id in extractions),
                        key=lambda c: (c["first_seen_at"], c["repo_id"]))
    for c in candidates:
        old = existing.get(c["repo_id"])
        slug = old["slug"] if old else slugify(c["repo"].get("name") or c["full_name"].split("/")[1])
        if not old and (not slug or taken.get(slug, c["repo_id"]) != c["repo_id"]):
            slug = slugify(c["full_name"].replace("/", "-"))
        try:
            record = build_record(c, extractions[c["repo_id"]], slug=slug, now=now, existing=old,
                                  found_in=found_in.get(c["repo_id"]))
        except (ValueError, ValidationError) as err:
            reason = str(err).splitlines()[0][:200]
            summary.skipped[c["full_name"]] = reason
            log(f"  skip {c['full_name']}: {reason}")
            continue
        if record.category not in categories:
            summary.skipped[c["full_name"]] = f"category: {record.category}"
            log(f"  skip {c['full_name']}: category {record.category}")
            continue
        taken[slug] = c["repo_id"]
        path = out_dir / f"{slug}.json"
        text = render(record)
        if old and path.exists() and _same_but_time(path.read_text(encoding="utf-8"), text):
            summary.unchanged.append(slug)
            continue
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        summary.written.append(slug)
        log(f"  {'would write' if dry_run else 'wrote'} {path.name} [{record.category}/{record.kind}]")
    return summary


def _same_but_time(old: str, new: str) -> bool:
    """True when two renders differ only in updated_at (no need to touch the file)."""
    strip = lambda text: {k: v for k, v in json.loads(text).items() if k != "updated_at"}  # noqa: E731
    return strip(old) == strip(new)
