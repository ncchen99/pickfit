"""Reference records for well-known tools, chosen by a rule instead of by hand.

pickfit's discovery takes only repos with at most 300 stars, so a well-known
free tool that honestly fits someone better can never be a pick. A reference
record fixes that for a few of them, flagged `well_known` and never a treasure.

Well known = a homebrew-core formula (no taps) in the top MAX_RANK by
install-on-request over the last 365 days (formulae.brew.sh analytics, a
public source the brief allows), whose source is a GitHub repository. Stars
are not used: star-sorted searches return libraries and star-farmed repos.
The category comes from the same prescreen and extraction as discovery (the
category definitions), and per category the top N by installs are taken; no
tool is added or left out by hand.

    uv run python -m pickfit.discover.well_known add --upto-rank 300
    uv run pickfit prescreen --no-review --limit 300 --repo gh:...   (ids printed by add)
    uv run python -m pickfit.discover.well_known list --category local_ai

`add` stores the repos as candidates (query id QUERY_ID) with details, rules
and the install-count evidence; `list` prints them in rank order with the
prescreen's and the extraction's category, for `pickfit extract --repo`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

from pickfit.discover.github import USER_AGENT, GitHub, GitHubError, github_token, normalize_repo, runs_dir
from pickfit.discover.rules import classify, RULES_VERSION
from pickfit.discover.store import PipelineDB

ANALYTICS_URL = "https://formulae.brew.sh/api/analytics/install-on-request/365d.json"
FORMULAE_URL = "https://formulae.brew.sh/api/formula.json"
BASIS = "homebrew_installs_on_request_365d"
MAX_RANK = 1000  # about 9.5k installs a year on 2026-10-29
QUERY_ID = "well_known:homebrew"
# The store needs a query category; the profile's category comes from the extraction.
STORE_CATEGORY = "well_known"

_GITHUB = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/#?]|$)")


def github_repo(formula: dict[str, Any]) -> str | None:
    """owner/name of the formula's source on GitHub: stable URL, then head URL, then homepage."""
    urls = formula.get("urls") or {}
    for url in ((urls.get("stable") or {}).get("url"), (urls.get("head") or {}).get("url"), formula.get("homepage")):
        m = _GITHUB.search(url or "")
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def ranked_pool(analytics: dict[str, Any], formulae: list[dict[str, Any]], max_rank: int = MAX_RANK) -> list[dict[str, Any]]:
    """Core formulae in the top `max_rank` with a GitHub source, best rank first, one row per repo.

    The rank is the formula's place in the analytics list (taps included, as Homebrew counts it);
    analytics may still list a formula under an old name or an alias.
    """
    by_name: dict[str, dict[str, Any]] = {}
    for formula in formulae:
        for name in [formula["name"], *(formula.get("aliases") or []), *(formula.get("oldnames") or [])]:
            by_name.setdefault(name, formula)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, item in enumerate(analytics["items"][:max_rank], 1):
        name = item["formula"]
        formula = by_name.get(name)
        if "/" in name or formula is None:
            continue  # a tap, or no longer in homebrew-core
        repo = github_repo(formula)
        if repo is None or repo.lower() in seen:
            continue
        seen.add(repo.lower())
        count = int(str(item["count"]).replace(",", ""))
        pool.append({"rank": rank, "formula": formula["name"], "count": count, "repo": repo,
                     "license": formula.get("license"), "desc": formula.get("desc")})
    return pool


def evidence(row: dict[str, Any], analytics: dict[str, Any], max_rank: int, checked_at: str) -> dict[str, Any]:
    """The `well_known` fact as a profile carries it (schema WellKnown)."""
    return {"basis": BASIS, "package": f"homebrew:{row['formula']}", "rank": row["rank"], "count": row["count"],
            "max_rank": max_rank, "period_start": analytics["start_date"], "period_end": analytics["end_date"],
            "source_url": ANALYTICS_URL, "checked_at": checked_at}


def _fetch(url: str, cache: Path) -> Any:
    """GET a JSON document once a day; the copy in runs/cache is what the evidence was read from."""
    path = cache / f"{datetime.now(UTC).date().isoformat()}-{url.rsplit('/', 1)[-1]}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with httpx2.Client(headers={"user-agent": USER_AGENT}, timeout=120, follow_redirects=True) as http:
            resp = http.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
    return json.loads(path.read_text(encoding="utf-8"))


def add(db: PipelineDB, gh: GitHub, pool: list[dict[str, Any]], analytics: dict[str, Any], *, upto_rank: int,
        max_rank: int, from_rank: int = 1, log=print) -> list[str]:
    """Store pool rows from `from_rank` to `upto_rank` as candidates with details, rules and evidence; return their ids."""
    checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # as the records write it
    ids: list[str] = []
    for row in pool:
        if row["rank"] > upto_rank:
            break
        if row["rank"] < from_rank:
            continue
        try:
            item = gh.repo(row["repo"])
        except GitHubError as err:
            log(f"skip {row['repo']}: {err}")
            continue
        if item is None or item.get("fork") or item.get("archived"):
            log(f"skip {row['repo']}: missing, a fork or archived")
            continue
        repo = normalize_repo(item)
        db.upsert_repo(repo, category=STORE_CATEGORY, query_id=QUERY_ID)
        repo_id = f"gh:{repo['id']}"
        db.save_well_known(repo_id, evidence(row, analytics, max_rank, checked_at))
        c = db.candidate(repo_id)
        if c["details_at"] is None or c["details_error"] or c["details_pushed_at"] != repo.get("pushed_at"):
            try:
                db.save_details(repo_id, gh.details(repo), pushed_at=repo.get("pushed_at"))
            except GitHubError as err:
                db.save_details(repo_id, None, pushed_at=repo.get("pushed_at"), error=str(err))
                log(f"details failed {row['repo']}: {err}")
                continue
            c = db.candidate(repo_id)
        result = classify(c)
        db.save_rules(repo_id, label=result.label, passed=result.passed, reasons=result.reasons, version=RULES_VERSION)
        ids.append(repo_id)
        log(f"{row['rank']:>4} {row['formula']:<20} {repo_id:<14} {row['repo']:<40} {result.label}")
    return ids


def listing(db: PipelineDB, category: str | None = None) -> list[dict[str, Any]]:
    """Stored well-known candidates in rank order with what prescreen and extraction said."""
    decisions = db.prescreen_decisions()
    rows = []
    for repo_id, ev in db.well_known().items():
        c = db.candidate(repo_id)
        decision = decisions.get(repo_id) or {}
        screen = (decision.get("review") or decision.get("screen") or {}).get("result") or {}
        extraction = db.last_extraction(repo_id, "muse-spark-1.3")
        result = (extraction or {}).get("result") or {}
        extracted = (result.get("category") or {}).get("value") if isinstance(result.get("category"), dict) else None
        kind = (result.get("kind") or {}).get("value") if isinstance(result.get("kind"), dict) else None
        rows.append({"rank": ev["rank"], "package": ev["package"], "repo_id": repo_id, "full_name": c["full_name"],
                     "rule": c["rule_label"], "screen_keep": (decisions.get(repo_id) or {}).get("keep"),
                     "screen_category": screen.get("category"), "extracted_category": extracted, "kind": kind})
    rows.sort(key=lambda r: r["rank"])
    if category:
        rows = [r for r in rows if (r["extracted_category"] or r["screen_category"]) == category]
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pickfit.discover.well_known")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add", help="store the top Homebrew formulae's GitHub repos as candidates ($0)")
    a.add_argument("--upto-rank", type=int, required=True, help="stop at this rank (at most --max-rank)")
    a.add_argument("--from-rank", type=int, default=1, help="start at this rank, to go on from an earlier run")
    a.add_argument("--max-rank", type=int, default=MAX_RANK, help=f"the well-known threshold (default {MAX_RANK})")
    a.add_argument("--db", default=None, help="pipeline database (default runs/pipeline.db)")
    li = sub.add_parser("list", help="stored well-known candidates in rank order")
    li.add_argument("--category", choices=["dev_cli", "local_ai", "other"])
    li.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    db = PipelineDB(args.db or runs_dir() / "pipeline.db")
    if args.command == "list":
        for r in listing(db, args.category):
            print(json.dumps(r, ensure_ascii=False))
        return 0
    if args.upto_rank > args.max_rank:
        parser.error("--upto-rank must not exceed --max-rank")
    cache = runs_dir() / "cache" / "homebrew"
    analytics, formulae = _fetch(ANALYTICS_URL, cache), _fetch(FORMULAE_URL, cache)
    pool = ranked_pool(analytics, formulae, args.max_rank)
    log = lambda line: print(line, file=sys.stderr)  # noqa: E731
    log(f"pool: {len(pool)} repos in the top {args.max_rank} ({analytics['start_date']}..{analytics['end_date']})")
    gh = GitHub(github_token())
    try:
        ids = add(db, gh, pool, analytics, upto_rank=args.upto_rank, max_rank=args.max_rank,
                  from_rank=args.from_rank, log=log)
    finally:
        log(f"github requests: {dict(gh.requests)}")
        gh.close()
    labels = Counter(db.candidate(i)["rule_label"] for i in ids)
    log(f"added {len(ids)}: {dict(labels)}")
    print(" ".join(f"--repo {i}" for i in ids if db.candidate(i)["rule_passed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
