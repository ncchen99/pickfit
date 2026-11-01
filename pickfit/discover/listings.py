"""Package stores as discovery sources (P2.7, brief 2.1): Flathub and Homebrew Cask.

A store's catalog says what an app is, under which license, where its source lives and
how to install it; pickfit lists software it has tested itself, so a store app becomes a
candidate like any other and goes through rules, extraction and verification. The
catalogs and what may be read from them: docs/source-terms.md.

One set of neutral rules for both stores, applied in this order; the first that fails is
the app's outcome (`listings.outcome`):

1. software: Flathub desktop applications; casks that install an app, a binary, a pkg or
   an installer (fonts and keyboard layouts are not software), not a `@variant` of another.
2. open source where the source says so: Flathub's AppStream project_license (not
   LicenseRef or proprietary, not non-commercial or source-available); a cask has no
   license field, so GitHub's license for the repository the cask downloads from.
3. maintained: a release (Flathub) or a push to the repository (cask) in the last
   MAINTAINED_DAYS; the repository is not archived; the cask is not deprecated or disabled.
4. usable without an account: the store's text does not say an account, login or
   subscription is required (only stated requirements; extraction and the sandbox look again).
5. used but not famous: between the BAND percentiles of the store's popularity measure
   among the apps that pass 1-4. Flathub's install stats are not licensed for reuse, so
   for Flathub the measure is the upstream repository's GitHub stars, and an app whose
   source is not on GitHub has none (`no_popularity_signal`). For a cask it is the
   365-day install count, with at least one install in the last 30 days.

Topic plays no part. The batch is a hash-ordered sample of the apps that pass (pick).

An app whose repository is on GitHub becomes the candidate `gh:<id>`: one already in the
pool, under its current or an earlier name, is the same candidate, and the store is added
to how it was found (query id `<source>:<item id>`).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pickfit.discover.github import GitHub, GitHubError
from pickfit.discover.showhn import _repos_in
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.ledger import taipei_now

SOURCES = ("flathub", "homebrew_cask")
FILTERS_VERSION = "listings.v1"
MAINTAINED_DAYS = 365
BAND = (0.25, 0.75)  # percentiles: the middle half; the least-used and the best-known quarters are out
SOFTWARE_KINDS = ("gui", "cli", "installer")
# GitHub accounts that host packaging, not the app (Flathub's manifests, Homebrew's taps).
PACKAGING_OWNERS = frozenset({"flathub", "flathub-infra", "homebrew"})

# License expressions that are not open source: proprietary, non-commercial, no-derivatives,
# source-available.
_NOT_OPEN = re.compile(r"LicenseRef|proprietary|(^|-)NC(-|$)|(^|-)ND(-|$)|BUSL|SSPL|Elastic|PolyForm|"
                       r"Commons-Clause|freeware|shareware|unknown", re.I)
_OR = re.compile(r"\s+OR\s+", re.I)
# Stated requirements only: "requires a Foo account", "login required", "subscription needed".
_NEEDS_ACCOUNT = re.compile(
    r"\b(requires?|needs?|must have)\s+(an?\s+)?([\w.+-]+\s+){0,3}(account|subscription|login)\b"
    r"|\b(account|subscription|login|sign[- ]?in)\s+(is\s+)?(required|needed|mandatory)\b", re.I)
# "No account required", "you don't need a YouTube account": a negation just before the match.
_NEGATION = re.compile(r"\b(no|not|without|never)\W*$|n't\W+(\w+\W+)?$", re.I)


@dataclass
class Listing:
    """What a store says about one app. Text fields are the store's own words."""

    source: str
    item_id: str
    name: str
    url: str  # the app's public page in the store
    kind: str  # gui | cli | installer | other
    summary: str | None = None
    description: str | None = None
    license: str | None = None  # the store's license field (Flathub); casks have none
    homepage: str | None = None
    upstream: str | None = None  # the source repository URL the store names, on any host
    github: str | None = None  # owner/name when that repository is on GitHub
    released_at: str | None = None  # newest release the store lists (UTC ISO)
    version: str | None = None
    install_command: str | None = None  # the command the store shows
    run_command: str | None = None
    installs: dict[str, int] | None = None  # cask install events per 30d/90d/365d
    deprecated: bool = False
    facts: dict[str, Any] = field(default_factory=dict)  # developer, categories, release notes, ...


def open_license(expression: str | None) -> bool:
    """True when the license expression allows open-source use (one choice of an OR is enough)."""
    if not expression or not expression.strip():
        return False
    return any(part.strip() and not _NOT_OPEN.search(part) for part in _OR.split(expression.strip("() ")))


def needs_account(text: str) -> bool:
    text = text or ""
    return any(not _NEGATION.search(text[max(0, m.start() - 20):m.start()])
               for m in _NEEDS_ACCOUNT.finditer(text))


def github_repo(*urls: str | None) -> str | None:
    """owner/name of the first GitHub repository among the URLs, skipping packaging accounts."""
    for url in urls:
        for full in _repos_in(url or ""):
            if full.split("/")[0].lower() not in PACKAGING_OWNERS:
                return full
    return None


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def pick_key(seed: str, item_id: str) -> str:
    return hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest()


def _cheap_outcome(x: Listing, now: datetime) -> str | None:
    if x.kind not in SOFTWARE_KINDS:
        return "not_software"
    if x.source == "homebrew_cask" and "@" in x.item_id:
        return "variant"
    if x.deprecated:
        return "deprecated"
    if x.source == "flathub":
        if not open_license(x.license):
            return "not_open_source"
        if not x.released_at or _age_days(x.released_at, now) > MAINTAINED_DAYS:
            return "unmaintained"
    if needs_account(" ".join(filter(None, [x.name, x.summary, x.description]))):
        return "needs_account"
    if not x.github:
        return "no_popularity_signal" if x.source == "flathub" else "license_unknown"
    return None


def _age_days(iso: str, now: datetime) -> float:
    when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (now - when) / timedelta(days=1)


def _repo_outcome(x: Listing, repo: dict[str, Any] | None, now: datetime) -> str | None:
    if repo is None or not repo.get("id"):
        return "repo_missing"
    if repo.get("archived") or repo.get("disabled"):
        return "unmaintained"
    if x.source == "homebrew_cask":
        if not open_license(repo.get("license")):
            return "not_open_source"
        if not repo.get("pushed_at") or _age_days(repo["pushed_at"], now) > MAINTAINED_DAYS:
            return "unmaintained"
        if not (x.installs or {}).get("30d"):
            return "unused"
    return None


def popularity(x: Listing, repo: dict[str, Any]) -> int:
    """Flathub: the upstream's GitHub stars; cask: 365-day install events."""
    if x.source == "flathub":
        return int(repo.get("stargazers_count") or 0)
    return int((x.installs or {}).get("365d") or 0)


@dataclass
class StoreStats:
    source: str
    apps: int = 0
    by_outcome: Counter[str] = field(default_factory=Counter)
    band: tuple[int, int] | None = None
    eligible: int = 0
    repos_new: int = 0
    repos_known: int = 0
    by_kind: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "apps": self.apps, "by_outcome": dict(self.by_outcome.most_common()),
                "eligible_before_band": self.eligible, "band": list(self.band) if self.band else None,
                "candidates": self.by_outcome["candidate"], "candidates_by_kind": dict(self.by_kind),
                "repos_new": self.repos_new, "repos_known": self.repos_known}


def describe_query(source: str, catalog: str, band: tuple[int, int] | None) -> str:
    measure = "GitHub stars of the upstream" if source == "flathub" else "365-day cask installs"
    span = f"{band[0]}..{band[1]}" if band else "none"
    return (f"{catalog}; open source, maintained {MAINTAINED_DAYS} days, no stated account, {measure} "
            f"between P{int(BAND[0] * 100)} and P{int(BAND[1] * 100)} = {span} ({FILTERS_VERSION})")


def search_store(source: str, listings: list[Listing], gh: GitHub, db: PipelineDB, *, catalog: str,
                 now: datetime, run_id: str, log: Callable[[str], None]) -> StoreStats:
    """Apply the rules to a store's apps, add those that pass to the pool, record every app."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")
    ran_at = taipei_now().isoformat(timespec="seconds")
    stats = StoreStats(source, apps=len(listings))
    outcome: dict[str, str] = {}
    for x in listings:
        o = _cheap_outcome(x, now)
        if o:
            outcome[x.item_id] = o
    to_resolve = [x for x in listings if x.item_id not in outcome]
    log(f"{source}: {len(listings)} apps, {len(to_resolve)} pass the store-only rules; "
        f"looking up {len({x.github.lower() for x in to_resolve})} GitHub repositories")
    try:
        repos = gh.repos([x.github for x in to_resolve]) if to_resolve else {}
    except GitHubError as err:
        raise GitHubError(f"{source}: {err}") from None
    eligible: list[tuple[Listing, dict[str, Any]]] = []
    for x in to_resolve:
        repo = repos.get(x.github.lower())
        o = _repo_outcome(x, repo, now)
        if o:
            outcome[x.item_id] = o
        else:
            eligible.append((x, repo))
    stats.eligible = len(eligible)
    if eligible:
        values = [popularity(x, repo) for x, repo in eligible]
        stats.band = (int(percentile(values, BAND[0])), int(percentile(values, BAND[1])))
        for x, repo in eligible:
            value = popularity(x, repo)
            outcome[x.item_id] = ("below_band" if value < stats.band[0] else
                                  "above_band" if value > stats.band[1] else "candidate")
    log(f"{source}: {stats.eligible} eligible, popularity band {stats.band}")

    names = db.names_index()
    known: dict[str, bool] = {}
    new = 0
    for x in listings:
        o = outcome[x.item_id]
        stats.by_outcome[o] += 1
        repo = repos.get(x.github.lower()) if x.github else None
        key = repo_key(repo["id"]) if repo and repo.get("id") else None
        known_before = None
        if o == "candidate":
            if key not in known:
                known[key] = (names.get(x.github.lower()) is not None or names.get(repo["full_name"].lower())
                              is not None or db.candidate(key) is not None)
                stats.repos_known += known[key]
                stats.repos_new += not known[key]
            known_before = known[key]
            new += db.upsert_repo(repo, category="other", query_id=f"{source}:{x.item_id}")
            names[repo["full_name"].lower()] = key
            stats.by_kind[x.kind] += 1
        facts = asdict(x)
        if repo:
            facts["popularity"] = popularity(x, repo)
        db.save_listing(source=source, item_id=x.item_id, item_url=x.url, name=x.name, facts=facts,
                        linked_repo=repo["full_name"] if repo else x.github, repo_id=key, outcome=o,
                        known_before=known_before, run_id=run_id)
    db.log_query(run_id=run_id, query_id=source, category="other", q=describe_query(source, catalog, stats.band),
                 ran_at=ran_at, total_count=len(listings), returned=stats.by_outcome["candidate"], new=new)
    log(f"{source}: {stats.to_dict()}")
    return stats


def pick(db: PipelineDB, source: str, n: int, seed: str) -> list[dict[str, Any]]:
    """The batch: `n` of the store's candidates in the order of sha256(seed:item id), one per repository."""
    rows = sorted((x for x in db.listings(source) if x["outcome"] == "candidate" and x["repo_id"]),
                  key=lambda x: pick_key(seed, x["item_id"]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for x in rows:
        if x["repo_id"] not in seen and len(out) < n:
            seen.add(x["repo_id"])
            out.append(x)
    return out
