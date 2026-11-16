"""`pickfit discover`: find candidates (GitHub search, Show HN or a package store), store them, fetch
details, apply rules. `--repo owner/name` skips the search and stores the repositories it names."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pickfit.discover import cask, flathub
from pickfit.discover.github import (PUSHED_DAYS, RATE_LIMIT_MAX_WAIT_S, STARS, GitHub, GitHubError, Query,
                                     build_queries, normalize_repo, runs_dir)
from pickfit.discover.listings import pick, search_store
from pickfit.discover.rules import RULES_VERSION, classify
from pickfit.discover.showhn import DEFAULT_DAYS, HN, search_show_hn
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.env import get_env
from pickfit.ledger import taipei_now

CHANNELS = ("github", "show_hn", "flathub", "homebrew_cask")
STORES = ("flathub", "homebrew_cask")
DEFAULT_SEED = "p2.7"
DEFAULT_PER_QUERY = 100
DETAIL_WORKERS = 4  # REST calls in flight; GitHub asks clients not to hammer it concurrently
# owner/name, or a github.com URL of the repository (a trailing slash or .git is fine).
_NAMED_REPO = re.compile(r"(?:(?:https?://)?(?:www\.)?github\.com/)?([A-Za-z0-9][A-Za-z0-9-]{0,38})/"
                         r"([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?", re.I)


def pipeline_db_path() -> Path:
    return runs_dir() / "pipeline.db"


def prescreen_status() -> dict[str, Any]:
    """Why the P2.4 prescreen has no rows yet; the funnel shows its rows once it has run."""
    if get_env("ANTHROPIC_API_KEY"):
        return {"status": "not_run", "model": None, "cost_usd": 0.0,
                "note": "run `pickfit prescreen --limit N`"}
    return {"status": "skipped", "model": None, "cost_usd": 0.0,
            "note": "ANTHROPIC_API_KEY not set; rule-passed candidates go straight to extraction"}


def search(gh: GitHub, db: PipelineDB, *, today: date, per_query: int, pushed_days: int,
           categories: list[str] | None, run_id: str, log: Callable[[str], None],
           stars: str = STARS, cap: int | None = None, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Run the topic searches. Without `cap`, store every result. With `cap`, store only the first
    `cap` new repos taken round-robin by rank across the queries (each query's first result in
    query order, then each one's second, ...), skipping `exclude` (repo ids that already have a
    record) and repeats; return them in that order with the query and rank each came from."""
    queries = build_queries(today, pushed_days=pushed_days, categories=categories, stars=stars)
    if cap is None:
        for query in queries:
            ran_at = taipei_now().isoformat(timespec="seconds")
            returned = new = 0
            total = None
            for _, item, total in gh.search_all(query, per_query):
                returned += 1
                new += db.upsert_repo(normalize_repo(item), category=query.category, query_id=query.id)
            db.log_query(run_id=run_id, query_id=query.id, category=query.category, q=query.q,
                         ran_at=ran_at, total_count=total, returned=returned, new=new)
            log(f"search {query.id}: {total if total is not None else 0} matches, "
                f"took {returned}, new {new}  [{query.q}]")
        return []
    results: list[tuple[Query, str, int | None, list[dict[str, Any]]]] = []
    for query in queries:
        ran_at = taipei_now().isoformat(timespec="seconds")
        total = None
        items = []
        for _, item, total in gh.search_all(query, per_query):
            items.append(item)
        results.append((query, ran_at, total, items))
        log(f"search {query.id}: {total if total is not None else 0} matches, took {len(items)}  [{query.q}]")
    seen = set(exclude or ())
    picked: list[dict[str, Any]] = []
    taken: Counter[str] = Counter()
    for rank in range(max((len(r[3]) for r in results), default=0)):
        for query, _, _, items in results:
            if len(picked) >= cap:
                break
            if rank >= len(items):
                continue
            repo = normalize_repo(items[rank])
            key = repo_key(repo["id"])
            if key in seen:
                continue
            seen.add(key)
            db.upsert_repo(repo, category=query.category, query_id=query.id)
            taken[query.id] += 1
            picked.append({"order": len(picked) + 1, "repo_id": key, "full_name": repo["full_name"],
                           "stars": repo.get("stargazers_count"), "query_id": query.id, "rank": rank + 1})
    for query, ran_at, total, items in results:
        db.log_query(run_id=run_id, query_id=query.id, category=query.category, q=query.q,
                     ran_at=ran_at, total_count=total, returned=len(items), new=taken[query.id])
    skipped = sum(1 for _, _, _, items in results for item in items
                  if repo_key(normalize_repo(item)["id"]) in (exclude or set()))
    log(f"cap {cap}: picked {len(picked)} round-robin by rank; {skipped} results already have a record")
    return picked


def fetch_details(gh: GitHub, db: PipelineDB, *, workers: int, log: Callable[[str], None],
                  only: set[str] | None = None) -> None:
    """README, releases and files for every candidate that needs them, or only for `only` (repo ids)."""
    todo = [r for r in db.needs_details() if only is None or r["repo_id"] in only]
    log(f"details: {len(todo)} repos to fetch")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(gh.details, repo): repo for repo in todo}
        for future in as_completed(futures):
            repo = futures[future]
            try:
                db.save_details(repo["repo_id"], future.result(), pushed_at=repo["pushed_at"])
            except GitHubError as err:
                db.save_details(repo["repo_id"], None, pushed_at=repo["pushed_at"], error=str(err))
            done += 1
            if done % 50 == 0 or done == len(todo):
                log(f"details: {done}/{len(todo)}")


def apply_rules(db: PipelineDB, only: set[str] | None = None) -> Counter[str]:
    """Label every candidate that has details, or only those in `only` (repo ids); return the label
    counts. The owner counts behind the owner-burst flag are always over every detailed candidate."""
    candidates = [c for c in db.candidates() if c["details_at"] and not c["details_error"]]
    owners = Counter(c["repo"].get("owner") for c in candidates)
    if only is not None:
        candidates = [c for c in candidates if c["repo_id"] in only]
    labels: Counter[str] = Counter()
    for c in candidates:
        result = classify(c, owners)
        db.save_rules(c["repo_id"], label=result.label, passed=result.passed,
                      reasons=result.reasons, version=RULES_VERSION)
        labels[result.label] += 1
    return labels


def _records(data_dir: Path | None) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """repo_id -> {slug, category} of the records under data_dir, and their lowercased owner/name -> repo_id."""
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.json")) if data_dir else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            by_id[data["repo_id"]] = {"slug": data["slug"], "category": data["category"]}
            if data.get("repo"):
                by_name[data["repo"]["full_name"].lower()] = data["repo_id"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return by_id, by_name


def add_repos(gh: Any, db: PipelineDB, names: list[str], *, data_dir: Path | None = None,
              log: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    """Store named repositories (owner/name or a github.com URL) as candidates: GitHub's facts, the README,
    releases and files, and the rule label. No search and no model call.

    This is how a record written on another machine, whose candidate and extraction are in that machine's
    database, becomes something `pickfit extract --repo` and `pickfit verify --batch --repo` can select here.
    A repository that has a record under data_dir takes the record's category, as the batch does; any other
    is "other" until the prescreen or the extraction says more.

    One row per name, in order. outcome: added, refreshed (it was a candidate already), not_a_repository,
    not_found (gone, or not visible to the token), private, details_failed, or another_repository: a record
    has this name but GitHub now answers with a different repository id (the original was deleted and the name
    taken), so nothing is stored.
    """
    log = log or (lambda line: None)
    by_id, by_name = _records(data_dir)
    rows: list[dict[str, Any]] = []
    stored: dict[str, dict[str, Any]] = {}
    for name in names:
        row: dict[str, Any] = {"name": name, "outcome": "not_a_repository"}
        rows.append(row)
        match = _NAMED_REPO.fullmatch(name.strip())
        if not match:
            continue
        asked = f"{match.group(1)}/{match.group(2)}"
        item = gh.repo(asked)
        if item is None:
            row["outcome"] = "not_found"
            continue
        if item.get("private"):
            row["outcome"] = "private"
            continue
        repo = normalize_repo(item)
        key = repo_key(item["id"])
        row.update(repo_id=key, full_name=repo["full_name"])
        owner = by_name.get(asked.lower())  # the record that was written under this name
        if owner and owner != key:
            row.update(outcome="another_repository", record=by_id[owner]["slug"])
            continue
        record = by_id.get(key)
        category = record["category"] if record else "other"
        new = db.upsert_repo(repo, category=category, query_id=f"named:{repo['full_name']}")
        row.update(outcome="added" if new else "refreshed", record=record["slug"] if record else None,
                   category=category)
        try:
            db.save_details(key, gh.details(repo), pushed_at=repo.get("pushed_at"))
        except GitHubError as err:
            db.save_details(key, None, pushed_at=repo.get("pushed_at"), error=str(err))
            row.update(outcome="details_failed", error=str(err))
            continue
        stored[key] = row
    if stored:
        apply_rules(db, only=set(stored))
    for key, row in stored.items():
        candidate = db.candidate(key) or {}
        row.update(rule_label=candidate.get("rule_label"), rule_passed=candidate.get("rule_passed"))
    for row in rows:
        log(f"  {row['name']}: {row['outcome']}"
            + (f" · {row['repo_id']} {row['full_name']}" if "repo_id" in row else "")
            + (f" · record {row['record']}" if row.get("record") else "")
            + (f" · rules {row['rule_label']}" if row.get("rule_label") else ""))
    return rows


def run_discover(*, token: str, db_path: Path | None = None, channel: str = "github",
                 per_query: int = DEFAULT_PER_QUERY, pushed_days: int = PUSHED_DAYS, days: int = DEFAULT_DAYS,
                 categories: list[str] | None = None, skip_details: bool = False,
                 today: date | None = None, now: datetime | None = None, gh: GitHub | None = None,
                 hn: HN | None = None, max_rate_wait_s: float = RATE_LIMIT_MAX_WAIT_S,
                 pick_n: int = 0, seed: str = DEFAULT_SEED, store_http: Any = None,
                 stars: str = STARS, cap: int | None = None, exclude: set[str] | None = None,
                 log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the free part of the funnel and return the funnel counts.

    channel "github" runs the topic searches; "show_hn" reads the last `days` of Show HN
    posts (pickfit.discover.showhn) and adds `show_hn` to the funnel. "flathub" and
    "homebrew_cask" read the store's catalog (pickfit.discover.listings); details are then
    fetched only for the batch of `pick_n` (pick), which the funnel lists under `pick`.
    For "github", `stars` is the star band and `cap` keeps only the first `cap` new repos (see
    search); details and rules then cover only those, and the funnel lists them under `capped`.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; expected one of {CHANNELS}")
    log = log or (lambda line: print(line, file=sys.stderr))
    db = PipelineDB(db_path or pipeline_db_path())
    own_client = gh is None
    gh = gh or GitHub(token, rate_limit_max_wait_s=max_rate_wait_s)
    own_hn = hn is None and channel == "show_hn"
    run_id = f"discover-{'' if channel == 'github' else channel + '-'}" + taipei_now().strftime("%Y%m%d-%H%M%S")
    show_hn = store = picked = passed_over = None
    capped: list[dict[str, Any]] | None = None
    try:
        if channel in STORES:
            now = now or datetime.now(UTC)
            if channel == "flathub":
                listings, catalog = flathub.parse_catalog(flathub.fetch_catalog(store_http)), flathub.CATALOG
            else:
                listings, catalog = cask.parse(*cask.fetch(store_http)), cask.CATALOG
            store = search_store(channel, listings, gh, db, catalog=catalog, now=now, run_id=run_id, log=log)
            if pick_n > 0:
                picked, passed_over = pick_batch(gh, db, channel, pick_n, seed, log=log)
        elif channel == "show_hn":
            hn = hn or HN()
            show_hn = search_show_hn(gh, db, hn, now=now or datetime.now(UTC), days=days,
                                     categories=categories, run_id=run_id, log=log)
        else:
            # GitHub reads created:/pushed: dates in UTC.
            capped = search(gh, db, today=today or datetime.now(UTC).date(), per_query=per_query,
                            pushed_days=pushed_days, categories=categories, run_id=run_id, log=log,
                            stars=stars, cap=cap, exclude=exclude) if cap is not None else None
            if cap is None:
                search(gh, db, today=today or datetime.now(UTC).date(), per_query=per_query,
                       pushed_days=pushed_days, categories=categories, run_id=run_id, log=log, stars=stars)
        only = {x["repo_id"] for x in capped} if capped is not None else None
        if not skip_details and channel not in STORES:
            fetch_details(gh, db, workers=DETAIL_WORKERS, log=log, only=only)
        # A store run labels only the candidates its pick looked at; a capped run only its repos.
        if channel in STORES:
            only = {x["repo_id"] for x in (picked or []) + (passed_over or [])}
        labels = apply_rules(db, only=only)
        log(f"rules: {dict(labels)}")
    finally:
        log(f"github requests: {dict(gh.requests)}")
        if own_client:
            gh.close()
        if hn is not None:
            log(f"hn requests: {dict(hn.requests)}")
            if own_hn:
                hn.close()
    funnel = db.funnel(prescreen_status())
    if show_hn is not None:
        funnel["show_hn"] = {"run_id": run_id, "days": days, **show_hn.to_dict()}
    if capped is not None:
        funnel["capped"] = {"run_id": run_id, "stars": stars, "cap": cap, "per_query": per_query,
                            "excluded": len(exclude or ()), "repos": capped}
    if store is not None:
        funnel[channel] = {"run_id": run_id, **store.to_dict()}
        funnel["pick"] = [_picked(db, x) for x in picked or []]
        funnel["pick_passed_over"] = [_picked(db, x) for x in passed_over or []]
    return funnel


def pick_batch(gh: GitHub, db: PipelineDB, source: str, n: int, seed: str, *,
               log: Callable[[str], None]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The first `n` of the store's candidates in the seed's order that pass the rules, and those
    passed over on the way (rejected by the rules). Details are fetched only for the ones looked at."""
    order = pick(db, source, len(db.listings(source)), seed)
    picked: list[dict[str, Any]] = []
    passed_over: list[dict[str, Any]] = []
    i = 0
    while len(picked) < n and i < len(order):
        chunk = order[i:i + n - len(picked)]
        i += len(chunk)
        fetch_details(gh, db, workers=DETAIL_WORKERS, log=log, only={x["repo_id"] for x in chunk})
        apply_rules(db, only={x["repo_id"] for x in chunk})
        for x in chunk:
            if len(picked) == n:
                break
            (picked if (db.candidate(x["repo_id"]) or {}).get("rule_passed") else passed_over).append(x)
    log(f"pick {source}: {len(picked)} picked, {len(passed_over)} passed over by the rules")
    return picked, passed_over


def _picked(db: PipelineDB, listing: dict[str, Any]) -> dict[str, Any]:
    c = db.candidate(listing["repo_id"]) or {}
    return {"item_id": listing["item_id"], "name": listing["name"], "kind": listing["facts"].get("kind"),
            "repo_id": listing["repo_id"], "repo": listing["linked_repo"], "known_before": listing["known_before"],
            "popularity": listing["facts"].get("popularity"), "rule_label": c.get("rule_label"),
            "rule_passed": c.get("rule_passed")}
