"""Take a hand-written candidate list through pickfit's own pipeline (rule post-hackathon-candidates.v1).

The list is docs/discovery/post-hackathon-candidates-v1.md: tables of command-line tools, MCP servers and web
apps 念誠 put together on 2026-11-15. This script adds nothing to it and drops nothing from it; it reads the
tables, sets aside what the directory already has, and hands the rest to the code that takes every other
candidate (docs/source-terms.md has the rule):

- an entry with a GitHub repository (tools, MCP servers, self-hosted web tools) goes through `pickfit watch`'s
  single-repository pipeline: GitHub details, rules, prescreen, extraction, record, verification in a Modal
  sandbox (agent, fresh-box replay, judges), scores, known vulnerabilities. The queue is a local SQLite file
  with the Worker's schema (d1.SqliteD1); the live D1 is never touched, and nothing is deployed.
- a hosted web app (an address people open) goes through the web-app rules of pickfit.discover.webapps:
  robots.txt, the home page, the terms page (a site that forbids automated access is out), then the model
  screen. `web` marks the sites that pass as selected; `pickfit webapps extract`, `pickfit webapps records`
  and `python -m pickfit.verify.web_verify --records … --write-back` do the rest, one visit per site.

    uv run python scripts/ingest_candidates.py list                    # parse, check duplicates, write the JSON
    uv run python scripts/ingest_candidates.py repos --section cli --limit 3 --max-usd 20
    uv run python scripts/ingest_candidates.py web                     # rules 1 and 4-8 for the hosted web apps
    uv run python scripts/ingest_candidates.py results                 # fill each entry's outcome into the JSON

One repository is one record, so the seven reference servers of modelcontextprotocol/servers are one entry
here, and an entry the list names only by package (no repository) is listed as not taken.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

RULE = "post-hackathon-candidates.v1"
LIST_MD = REPO / "docs" / "discovery" / "post-hackathon-candidates-v1.md"
LIST_JSON = REPO / "docs" / "discovery" / "post-hackathon-candidates-v1.json"
SECTIONS = {"3": "cli", "4": "mcp", "5": "web"}
WEB_SOURCE = "curated"  # web_sites.source for these rows; show_hn and github are the discovered ones
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TICKED = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def parse_list(text: str) -> list[dict[str, Any]]:
    """One entry per tool the tables name, in the list's order. A row that names two tools (dust / duf) is
    two entries; `flow` says which pipeline takes the entry: repo, web (hosted), or none (no repository named)."""
    entries: list[dict[str, Any]] = []
    section = group = None
    for line in text.splitlines():
        if line.startswith("## "):
            section = SECTIONS.get(line[3:].split(".", 1)[0].strip())
            group = None
        elif line.startswith("### "):
            group = line[4:].strip()
        if section is None or not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        names = [n.strip() for n in _BOLD.findall(cells[0])]
        tokens = _TICKED.findall(cells[1])
        urls = [t for t in tokens if t.startswith(("http://", "https://"))]
        repos = [t for t in tokens if _REPO.match(t) and not t.startswith("@")]
        packages = [t for t in tokens if t not in urls and t not in repos]
        hosted = section == "web" and cells[2].strip("` ") == "web_app"
        pairs = list(zip(names, repos)) if len(names) > 1 and len(names) == len(repos) else None
        for name, repo in pairs or [(" / ".join(names), repos[0] if repos else None)]:
            entries.append({
                "order": len(entries) + 1, "section": section, "group": group, "name": name, "repo": repo,
                "url": urls[0] if urls else None, "packages": packages,
                "listed_as": cells[2].strip("` ") if section == "web" else None,
                "flow": "web" if hosted else "repo" if repo else "none",
            })
    return entries


def existing_records(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(repository full name, lower case -> slug; web address key -> slug) of the records already written."""
    from pickfit.discover.webapps import site_key

    repos: dict[str, str] = {}
    sites: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        full_name = (data.get("repo") or {}).get("full_name")
        if full_name:
            repos[full_name.lower()] = data["slug"]
        key = site_key((data.get("web") or {}).get("url"))
        if key:
            sites[key] = data["slug"]
    return repos, sites


def mark_known(entries: list[dict[str, Any]], data_dir: Path) -> None:
    """already_listed: the record that has this repository or address; same_repo_as: an earlier entry's name
    when two entries share a repository (one repository is one record)."""
    from pickfit.discover.webapps import site_key

    repos, sites = existing_records(data_dir)
    first: dict[str, str] = {}
    for e in entries:
        key = (e["repo"] or "").lower()
        e["already_listed"] = (repos.get(key) if key else None) or (
            sites.get(site_key(e["url"]) or "") if e["flow"] == "web" else None)
        e["same_repo_as"] = first.get(key) if key and e["flow"] == "repo" else None
        if key and e["flow"] == "repo":
            first.setdefault(key, e["name"])


def load_entries(data_dir: Path) -> list[dict[str, Any]]:
    entries = parse_list(LIST_MD.read_text(encoding="utf-8"))
    mark_known(entries, data_dir)
    return entries


def submission_id(repo: str) -> str:
    return "sub_c1_" + hashlib.sha256(repo.lower().encode()).hexdigest()[:16]


def chosen(entries: list[dict[str, Any]], args: argparse.Namespace, flow: str) -> list[dict[str, Any]]:
    """The entries of `flow` this run takes: not listed already, not a second entry of one repository."""
    out = [e for e in entries if e["flow"] == flow and not e["already_listed"] and not e["same_repo_as"]
           and (not args.section or e["section"] in args.section)
           and (not args.only or e["name"] in args.only or (e["repo"] or "") in args.only)]
    return out[: args.limit] if args.limit else out


# ---------------------------------------------------------------- list


def cmd_list(args: argparse.Namespace) -> int:
    from pickfit.ledger import taipei_now

    entries = load_entries(args.data)
    earlier = json.loads(LIST_JSON.read_text(encoding="utf-8")) if LIST_JSON.exists() else {}
    kept = {e["order"]: e.get("result") for e in earlier.get("entries", [])}
    for e in entries:
        e["result"] = kept.get(e["order"])
    counts: dict[str, int] = {}
    for e in entries:
        what = ("already_listed" if e["already_listed"] else "same_repository" if e["same_repo_as"]
                else {"repo": "to_run_repo", "web": "to_run_web", "none": "no_repository_named"}[e["flow"]])
        counts[f"{e['section']}:{what}"] = counts.get(f"{e['section']}:{what}", 0) + 1
    doc = {"rule": RULE, "registered_in": "docs/source-terms.md", "list": str(LIST_MD.relative_to(REPO)),
           "created_at": earlier.get("created_at") or taipei_now().isoformat(timespec="seconds"),
           "records_before": len(list(args.data.glob("*.json"))) if "records_before" not in earlier
           else earlier["records_before"],
           "counts": dict(sorted(counts.items())), "entries": entries}
    LIST_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(entries), **doc["counts"]}, ensure_ascii=False, indent=1))
    return 0


# ---------------------------------------------------------------- repositories


def cmd_repos(args: argparse.Namespace) -> int:
    from pickfit.d1 import DEFAULT_WORKER_DIR, SqliteD1, sql, timestamp
    from pickfit.discover.github import runs_dir
    from pickfit.discover.run import pipeline_db_path
    from pickfit.ledger import default_ledger, taipei_now
    from pickfit.watch import Settings, Watcher, live_steps

    todo = chosen(load_entries(args.data), args, "repo")
    queue = runs_dir() / "candidates-v1" / "queue.sqlite"
    if args.dry_run:
        print(f"{RULE}: {len(todo)} entries would run")
        for e in todo:
            print(f"  {e['section']:<4} {e['name']:<28} {e['repo']}")
        return 0
    queue.parent.mkdir(parents=True, exist_ok=True)
    d1 = SqliteD1(queue)
    known = {row["id"]: row["status"] for row in d1.query("SELECT id, status FROM submissions")}
    # Only this run's entries may start: anything an earlier run left queued waits for its own run.
    d1.execute("UPDATE submissions SET status = 'rejected', reason = 'not in this run' WHERE status = 'queued'")
    now = timestamp(taipei_now())
    queued = 0
    for e in todo:
        sid = submission_id(e["repo"])
        job = _job(runs_dir(), sid)
        # An entry the pipeline turned down stays turned down: running it again until it passes would be
        # picking. --retry is for an entry that failed for a reason on pickfit's side (a bug since fixed).
        if job.get("result") == "rejected" and not args.retry:
            continue
        if known.get(sid) in (None, "queued", "rejected") and not job.get("landed"):
            if sid in known:
                d1.execute(sql("UPDATE submissions SET status = 'queued', reason = NULL, updated_at = ?2 "
                               "WHERE id = ?1", sid, now))
            else:
                d1.execute(sql("INSERT INTO submissions (id, url, status, submitter_role, note, submitted_at, "
                               "updated_at) VALUES (?1, ?2, 'queued', 'unknown', ?3, ?4, ?4)", sid,
                               f"https://github.com/{e['repo']}", RULE, now))
            queued += 1
    print(f"{RULE}: {len(todo)} entries chosen, {queued} queued in {queue.relative_to(REPO)} · "
          f"{args.concurrency} at a time · --max-usd {args.max_usd}", flush=True)
    if not queued:
        return 0
    settings = Settings(data_dir=args.data, runs_dir=runs_dir(), db_path=pipeline_db_path(),
                        worker_dir=DEFAULT_WORKER_DIR, commit=False, publish=False, hourly_cap=10_000,
                        max_usd=args.max_usd, concurrency=args.concurrency)
    watcher = Watcher(d1, live_steps(runner="modal"), settings, meta_ledger=default_ledger(),
                      log=lambda line: print(line, flush=True))
    jobs = watcher.run(once=True)
    for job in jobs:
        print(job.summary(), flush=True)
    spent = sum(sum(v for k, v in job.cost_usd.items() if k != "box") for job in jobs)
    print(json.dumps({"jobs": len(jobs), "results": _tally(j.result for j in jobs), "model_usd": round(spent, 2)}))
    return 0


def _job(runs: Path, sid: str) -> dict[str, Any]:
    """What the watcher saved about this entry's last run; empty when it never ran."""
    try:
        return json.loads((runs / "watch" / "jobs" / f"{sid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _tally(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- hosted web apps


def cmd_web(args: argparse.Namespace) -> int:
    """Rules 1 and 4-8 of pickfit.discover.webapps for each hosted web app of the list, in the list's order;
    the popularity band (rule 3) is the one rule a hand-written list of well-known sites is not put through."""
    from pickfit.discover import webapps
    from pickfit.discover.github import GitHub, GitHubError, github_token, normalize_repo
    from pickfit.discover.run import pipeline_db_path
    from pickfit.discover.store import repo_key
    from pickfit.ledger import taipei_now

    todo = chosen(load_entries(args.data), args, "web")
    db = webapps.WebSites(pipeline_db_path())
    gh = GitHub(github_token())
    fetch = webapps.Fetcher()
    run_id = "webapps-curated-" + taipei_now().strftime("%Y%m%d-%H%M%S")
    done = {r["item_id"]: r for r in db.rows(source=WEB_SOURCE)}
    outcomes: dict[str, int] = {}
    for e in todo:
        repo = None
        if e["repo"]:
            try:
                item = gh.repo(e["repo"])
                repo = normalize_repo(item) if item else None
            except GitHubError as err:
                print(f"  {e['name']}: GitHub: {err}", flush=True)
        item_id = repo_key(repo["id"]) if repo else webapps.site_key(e["url"]) or e["url"]
        if item_id in done and done[item_id]["checked_at"] and not args.force:
            outcome = done[item_id]["outcome"]
        else:
            row = {"source": WEB_SOURCE, "item_id": item_id, "item_url": repo["html_url"] if repo else e["url"],
                   "title": e["name"], "link": e["url"], "site_url": e["url"], "site_key": webapps.site_key(e["url"]),
                   "repo_id": repo_key(repo["id"]) if repo else None, "repo": repo,
                   "popularity": int(repo.get("stargazers_count") or 0) if repo else None,
                   "signals": {"rule": RULE, "list_order": e["order"]},
                   "outcome": webapps.site_outcome(e["url"]) or "site"}
            db.save(row, run_id)
            outcome = row["outcome"]
            if outcome == "site" and not args.dry_run:
                outcome, checks, page, readme = webapps.check_one(row, hn=None, gh=gh, fetch=fetch, run_id=run_id)
                # A site that passes every rule is selected: the list is the selection, there is no quota.
                outcome = "selected" if outcome == "passed" else outcome
                db.save_check(WEB_SOURCE, item_id, outcome=outcome, checks=checks, page=page, readme=readme)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        print(f"  {e['name']:<24} {e['url']:<40} {outcome}", flush=True)
    print(json.dumps({"sites": len(todo), "outcomes": dict(sorted(outcomes.items()))}))
    return 0


# ---------------------------------------------------------------- results


def cmd_results(args: argparse.Namespace) -> int:
    """Write what happened to each entry into the JSON: the record and its level, or why there is none."""
    from pickfit.discover import webapps
    from pickfit.discover.github import runs_dir
    from pickfit.discover.run import pipeline_db_path

    doc = json.loads(LIST_JSON.read_text(encoding="utf-8"))
    by_repo: dict[str, dict[str, Any]] = {}
    by_site: dict[str, dict[str, Any]] = {}
    for path in sorted(args.data.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        full_name = ((data.get("repo") or {}).get("full_name") or "").lower()
        if full_name:
            by_repo[full_name] = data
        key = webapps.site_key((data.get("web") or {}).get("url"))
        if key:
            by_site[key] = data
    jobs: dict[str, dict[str, Any]] = {}
    for path in sorted((runs_dir() / "watch" / "jobs").glob("sub_c1_*.json")):
        jobs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    sites = {r["site_key"]: r for r in webapps.WebSites(pipeline_db_path()).rows(source=WEB_SOURCE)}
    began = datetime.fromisoformat(doc["created_at"])

    def of_this_batch(record: dict[str, Any]) -> bool:
        return datetime.fromisoformat(record["first_seen_at"]) >= began

    tally: dict[str, int] = {}
    for e in doc["entries"]:
        record = by_repo.get((e["repo"] or "").lower()) if e["flow"] != "web" else by_site.get(
            webapps.site_key(e["url"]) or "") or by_repo.get((e["repo"] or "").lower())
        job = jobs.get(submission_id(e["repo"])) if e["repo"] else None
        if e["already_listed"]:
            result = {"outcome": "already_listed", "slug": e["already_listed"]}
        elif e["flow"] == "none":
            result = {"outcome": "not_taken", "why": "the list names a package, no repository"}
        elif e["same_repo_as"]:
            result = {"outcome": "same_repository", "as": e["same_repo_as"],
                      "slug": record["slug"] if record else None}
        elif record and of_this_batch(record):
            verification = record.get("verification") or {}
            result = {"outcome": "record", "slug": record["slug"], "category": record["category"],
                      "kind": record["kind"], "level": verification.get("level"),
                      "unverified_reason": verification.get("unverified_reason"),
                      "quality": ((record.get("scores") or {}).get("quality") or {}).get("total")}
        elif job:
            result = {"outcome": job.get("result") or "not_finished", "why": job.get("reason")}
        elif e["flow"] == "web" and webapps.site_key(e["url"]) in sites:
            result = {"outcome": "no_record", "why": sites[webapps.site_key(e["url"])]["outcome"]}
        else:
            result = None
        if job and result is not None:
            result["model_usd"] = round(sum(v for k, v in (job.get("cost_usd") or {}).items() if k != "box"), 4)
        e["result"] = result
        key = "not_run" if result is None else result["outcome"] + (
            f":{result['level']}" if result.get("level") else "")
        tally[f"{e['section']}:{key}"] = tally.get(f"{e['section']}:{key}", 0) + 1
    doc["results"] = dict(sorted(tally.items()))
    LIST_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc["results"], ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    from pickfit.profiles import DEFAULT_OUT

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_OUT, help="records directory (default data/software)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="parse the list, mark what is already listed, write the JSON").set_defaults(func=cmd_list)

    def selection(p: argparse.ArgumentParser) -> None:
        p.add_argument("--section", action="append", choices=sorted(SECTIONS.values()), help="only this section")
        p.add_argument("--only", action="append", help="only this entry (its name or owner/repo; repeatable)")
        p.add_argument("--limit", type=int, default=None, help="at most N entries, in the list's order")
        p.add_argument("--dry-run", action="store_true", help="say what would run; no model call, no sandbox")

    r = sub.add_parser("repos", help="entries with a repository, through pickfit watch's pipeline (paid)")
    selection(r)
    r.add_argument("--concurrency", type=int, default=3, help="repositories at once (default 3)")
    r.add_argument("--max-usd", type=float, default=30.0, help="stop starting entries past this model spend")
    r.add_argument("--retry", action="store_true",
                   help="also entries an earlier run rejected (only for a failure on pickfit's side, since fixed)")
    r.set_defaults(func=cmd_repos)
    w = sub.add_parser("web", help="hosted web apps: robots.txt, home page, terms and the model screen (paid)")
    selection(w)
    w.add_argument("--force", action="store_true", help="check a site again even if it was checked")
    w.set_defaults(func=cmd_web)
    sub.add_parser("results", help="write each entry's outcome into the JSON").set_defaults(func=cmd_results)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
