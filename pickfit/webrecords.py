"""Records for hosted web apps (P2.8): kind web_app, written from a selected site and its extraction.

A site pickfit.discover.webapps selected becomes an extraction candidate whose sources are
its home page as fetched and, for an open-source app, the repository's description and
README (extract.web_sources). A Show HN post is listed as a source of kind `hn`, where
pickfit found the app; the address it links is cited to it, nothing else. Its extraction rows are keyed
by the site (`web:<host>[/path]`), never by a GitHub id, so the repository pipeline never
mistakes them for a repository's extraction.

The record follows profiles.build_record: values the model read keep their verbatim quote
in `evidence`; facts an API gave (the repository, its license and topics; the address the
post or the repository linked) are cited to that API. Web-app specifics:

- repo_id is the repository's `gh:<id>` when the site has one, else the site's `web:` id,
  and `repo` is null then; `web.url` is the address to open (https only).
- kind must read as web_app: a site the extraction calls something else is skipped.
- category: as the sources show it (other for most; dev_cli for a developer tool; local_ai
  when the AI runs on the user's device), never mcp_server.
- platforms: all three by rule, since a browser opens the app on each; network is required
  unless a source says otherwise; install stays empty.

Only new files are written: a site whose repository or address already has a record is
skipped, and an existing file is never overwritten.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pickfit.discover.webapps import WebSites, host_of
from pickfit.extract import build_sources
from pickfit.ledger import taipei_now
from pickfit.profiles import (
    _TAG,
    DEFAULT_OUT,
    MAX_TAGS,
    WriteSummary,
    _Evidence,
    _summary,
    open_source_from_license,
    render,
    slugify,
)
from pickfit.schema import ExtractionResult, SoftwareRecord

ALL_OS = ["macos", "linux", "windows"]
_SEGMENT_JUNK = re.compile(r"[^A-Za-z0-9._~-]+")


def site_id(site: dict[str, Any]) -> str:
    """The site's `web:` id in the record schema's alphabet: host (IDNA) and path segments."""
    key = site["site_key"].removeprefix("web:")
    host, _, path = key.partition("/")
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        host = re.sub(r"[^a-z0-9.-]", "-", host.lower())
    segments = [_SEGMENT_JUNK.sub("-", seg).strip("-") for seg in path.split("/")]
    return "web:" + "/".join([host, *[seg for seg in segments if seg]])


def web_url(site: dict[str, Any]) -> str | None:
    """The https address to open: where the home page ended up, else the link itself."""
    for url in ((site.get("checks") or {}).get("home", {}).get("final_url"), site.get("site_url")):
        if url and url.startswith("https://"):
            return url
    return None


def web_candidate(site: dict[str, Any]) -> dict[str, Any]:
    """A selected site as an extraction candidate (extract.run_extract(candidates=...))."""
    repo = site.get("repo") or {}
    return {"repo_id": site_id(site), "full_name": repo.get("full_name") or host_of(site["site_url"]) or site["title"],
            "category": "other", "repo": repo, "site": site, "aliases": [],
            "first_seen_at": site["first_seen_at"], "last_seen_at": site["checked_at"] or site["first_seen_at"]}


def build_web_record(site: dict[str, Any], extraction: dict[str, Any], *, slug: str, now: datetime) -> SoftwareRecord:
    """One web_app record. Raises ValueError to skip."""
    candidate = web_candidate(site)
    result = ExtractionResult.model_validate(extraction["result"])
    repo = site.get("repo")
    checked_at = (site.get("checks") or {}).get("checked_at") or site["checked_at"]
    url = web_url(site)
    if url is None:
        raise ValueError("no_https: the site has no https address")
    sources = build_sources(candidate)
    record_sources: list[dict[str, Any]] = [{"id": "site", "kind": "website", "url": url, "fetched_at": checked_at}]
    source_ids = {"site": "site"}
    hn_id = f"hn:{site['item_id']}" if site["source"] == "show_hn" else None
    if hn_id:  # where pickfit found the app; no field cites the post
        record_sources.append({"id": hn_id, "kind": "hn", "url": site["item_url"],
                               "fetched_at": checked_at})
    if repo:
        source_ids["description"] = "github_api"
        record_sources.append({"id": "github_api", "kind": "github_api",
                               "url": f"https://api.github.com/repos/{repo['full_name']}", "fetched_at": checked_at})
        readme = next((s for s in sources if s.id == "readme"), None)
        if readme:
            source_ids["readme"] = "readme"
            record_sources.append({"id": "readme", "kind": "readme", "url": readme.url, "fetched_at": checked_at})
    ev = _Evidence(sources, source_ids, extraction["model"], extraction["created_at"])
    # The address came from the repository's homepage field, or else from the Show HN post's link.
    link_source = "github_api" if repo and site["site_url"] == repo.get("homepage") else hn_id or "site"

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
    if kind != "web_app":
        raise ValueError(f"not_web_app: kind {kind}")
    category = cited("/category", result.category.value, result.category.quote)
    if category not in ("dev_cli", "local_ai", "other"):  # a web app is not an MCP server
        category = "other"
        ev.items = [e for e in ev.items if e["field"] != "/category"]
        ev.api("/category", "site", checked_at, method="rule")
    summary = cited("/summary", result.summary.value, result.summary.quote)
    if summary:
        summary = _summary(summary)
    elif repo and repo.get("description"):
        summary = _summary(repo["description"])
        ev.api("/summary", "github_api", checked_at)
    else:
        raise ValueError("no_summary")
    name = cited("/name", result.name.value, result.name.quote)
    if not name or len(name) > 100:
        if not repo:
            raise ValueError("no_name")
        name = repo.get("name") or repo["full_name"].split("/")[1]
        ev.api("/name", "github_api", checked_at)

    pre = result.prerequisites
    min_ram = cited("/prerequisites/min_ram_gb", pre.min_ram_gb.value, pre.min_ram_gb.quote)
    network = cited("/prerequisites/network", pre.network.value, pre.network.quote)
    if network is None:
        network = "required"
        ev.api("/prerequisites/network", "site", checked_at, method="rule")
    prerequisites = {
        "runtimes": cited_list("/prerequisites/runtimes", pre.runtimes),
        "system_packages": cited_list("/prerequisites/system_packages", pre.system_packages),
        "gpu": cited("/prerequisites/gpu", pre.gpu.value, pre.gpu.quote),
        "apple_silicon_only": cited("/prerequisites/apple_silicon_only", pre.apple_silicon_only.value,
                                    pre.apple_silicon_only.quote),
        "min_ram_gb": min_ram if min_ram is None or min_ram >= 0 else None,
        "network": network,
        "api_keys": cited_list("/prerequisites/api_keys", pre.api_keys),
    }
    ev.api("/platforms", "site", checked_at, method="rule")
    ev.api("/web", link_source, checked_at)
    ev.api("/homepage", link_source, checked_at)

    license_id = repo.get("license") if repo else None
    tags: list[str] = []
    if repo:
        ev.api("/repo", "github_api", checked_at)
        ev.api("/license", "github_api", checked_at)
        ev.api("/open_source", "github_api", checked_at, method="rule")
        tags = [t for t in repo.get("topics") or [] if _TAG.match(t)][:MAX_TAGS]
        if tags:
            ev.api("/tags", "github_api", checked_at)

    data: dict[str, Any] = {
        "slug": slug,
        "repo_id": f"gh:{repo['id']}" if repo else candidate["repo_id"],
        "name": name,
        "summary": summary,
        "aliases": [],
        "status": "listed",
        "status_reason": None,
        "category": category,
        "kind": "web_app",
        "audience": cited("/audience", result.audience.value, result.audience.quote),
        "maturity": cited("/maturity", result.maturity.value, result.maturity.quote),
        "tags": tags,
        "use_cases": cited_list("/use_cases", result.use_cases),
        "alternatives_to": cited_list("/alternatives_to", result.alternatives_to),
        "features": cited_list("/features", result.features),
        "why_worth_it": None,
        "homepage": url,
        "repo": {"url": repo.get("html_url") or f"https://github.com/{repo['full_name']}",
                 "full_name": repo["full_name"], "created_at": repo.get("created_at"),
                 "archived": bool(repo.get("archived"))} if repo else None,
        "platforms": ALL_OS,
        "prerequisites": prerequisites,
        "install": {},
        "pricing": {"model": cited("/pricing", result.pricing.value, result.pricing.quote), "note": None},
        "open_source": open_source_from_license(license_id) if repo else None,
        "license": license_id,
        "processing": cited("/processing", result.processing.value, result.processing.quote),
        "last_release": None,
        "verification": {"level": "unverified", "unverified_reason": "not_run", "checked_at": None, "runs": []},
        "web": {"url": url},
        "sources": record_sources,
        "evidence": ev.items,
        "first_seen_at": site["first_seen_at"],
        "updated_at": now.isoformat(timespec="seconds"),
    }
    if data["audience"] == "import_only":
        raise ValueError("not_a_tool: import_only")
    return SoftwareRecord.model_validate(data)


def latest_web_extractions(db_path: Path | str, model: str) -> dict[str, dict[str, Any]]:
    from pickfit.discover.store import PipelineDB
    from pickfit.profiles import latest_extractions

    return {k: v for k, v in latest_extractions(PipelineDB(db_path), model).items() if k.startswith("web:")}


def write_web_records(sites: WebSites, *, model: str, out_dir: Path = DEFAULT_OUT, dry_run: bool = False,
                      now: datetime | None = None, log: Callable[[str], None] | None = None) -> WriteSummary:
    """One new record per selected site with a usable extraction by `model`."""
    log = log or (lambda line: None)
    now = now or taipei_now()
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_dir.glob("*.json"))]
    taken_slugs = {d["slug"] for d in existing}
    taken_ids = {d["repo_id"] for d in existing}
    taken_urls = {(d.get("web") or {}).get("url") for d in existing} - {None}
    extractions = latest_web_extractions(sites.path, model)
    summary = WriteSummary()
    for site in sorted(sites.rows(outcome="selected"), key=lambda s: (s["source"], s["item_id"])):
        sid = site_id(site)
        label = site["site_key"]
        extraction = extractions.get(sid)
        if extraction is None:
            summary.skipped[label] = "no_extraction"
            continue
        record_id = f"gh:{site['repo']['id']}" if site.get("repo") else sid
        if record_id in taken_ids or web_url(site) in taken_urls:
            summary.skipped[label] = "has_record"
            continue
        repo = site.get("repo") or {}
        result = extraction["result"] or {}
        name = (result.get("name") or {}).get("value") or repo.get("name") or ""
        slug = slugify(name)
        if not slug or slug in taken_slugs:
            slug = slugify(sid.removeprefix("web:").replace("/", "-"))
        if not slug or slug in taken_slugs:
            summary.skipped[label] = "slug_taken"
            continue
        try:
            record = build_web_record(site, extraction, slug=slug, now=now)
        except (ValueError, ValidationError) as err:
            reason = str(err).splitlines()[0][:200]
            summary.skipped[label] = reason
            log(f"  skip {label}: {reason}")
            continue
        path = out_dir / f"{slug}.json"
        if path.exists():
            summary.skipped[label] = "file_exists"
            continue
        if not dry_run:
            path.write_text(render(record), encoding="utf-8")
        taken_slugs.add(slug)
        taken_ids.add(record.repo_id)
        summary.written.append(slug)
        log(f"  {'would write' if dry_run else 'wrote'} {path.name} [{record.category}/{record.kind}] {record.web.url}")
    return summary
