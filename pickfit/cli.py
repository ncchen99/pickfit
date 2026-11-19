"""Command-line entry point: `uv run pickfit <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pickfit import __version__


def _ping(args: argparse.Namespace) -> int:
    from pickfit.meta import ping

    result = ping(provider=args.provider, model=args.model)
    print(json.dumps({
        "model": result.model,
        "text": result.text,
        "cost_usd": result.cost_usd,
        "cache_hit": result.cache_hit,
        "usage": vars(result.usage) if result.usage else None,
    }, ensure_ascii=False, indent=2))
    return 0


def _spend(args: argparse.Namespace) -> int:
    from pickfit.ledger import default_ledger

    print(json.dumps(default_ledger().spend_summary(), ensure_ascii=False, indent=2))
    return 0


# --- discovery and extraction (P2) ----------------------------------------------


def _discover(args: argparse.Namespace) -> int:
    from pickfit.discover.github import GitHubError, github_token
    from pickfit.discover.run import run_discover

    try:
        token = github_token()
    except GitHubError as err:
        print(f"pickfit discover: {err}", file=sys.stderr)
        return 2
    if args.repo:
        from pickfit.discover.github import GitHub
        from pickfit.discover.run import add_repos, pipeline_db_path
        from pickfit.discover.store import PipelineDB
        from pickfit.verify.result import DATA_DIR

        gh = GitHub(token, rate_limit_max_wait_s=args.max_rate_wait)
        try:
            rows = add_repos(gh, PipelineDB(pipeline_db_path()), args.repo, data_dir=DATA_DIR,
                             log=lambda line: print(line, file=sys.stderr))
        finally:
            gh.close()
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0 if all(row["outcome"] in ("added", "refreshed") for row in rows) else 1
    exclude = None
    if args.cap is not None:
        from pickfit.verify.result import DATA_DIR

        # Repos that already have a record are not new candidates.
        exclude = {json.loads(p.read_text()).get("repo_id") for p in DATA_DIR.glob("*.json")} - {None}
    funnel = run_discover(token=token, channel=args.channel, per_query=args.per_query,
                          pushed_days=args.pushed_days, days=args.days, categories=args.category,
                          skip_details=args.skip_details, max_rate_wait_s=args.max_rate_wait,
                          pick_n=args.pick, seed=args.seed, stars=args.stars, cap=args.cap, exclude=exclude)
    print(json.dumps(funnel, ensure_ascii=False, indent=2))
    return 0


def _extract(args: argparse.Namespace) -> int:
    from pickfit.extract import run_extract

    repo_ids = args.repo
    if args.records:
        from pickfit.verify.batch import record_slugs
        from pickfit.verify.result import DATA_DIR

        repo_ids = [*(repo_ids or []), *record_slugs(DATA_DIR)]
    if args.install_docs:
        from pickfit.discover.run import pipeline_db_path
        from pickfit.discover.store import PipelineDB
        from pickfit.extract import same_tier
        from pickfit.installdocs import run_docs
        from pickfit.meta import resolve_model

        docs = run_docs(PipelineDB(pipeline_db_path()), models=same_tier(resolve_model(args.model)),
                        repo_ids=repo_ids, force=args.force, log=lambda line: print(line, file=sys.stderr))
        # A candidate that got a page is extracted again below without --force: its sources changed.
        print(f"install guides: looked for {docs['looked']}, read for {len(docs['read'])}", file=sys.stderr)
    summary = run_extract(limit=args.limit, model=args.model, reasoning_effort=args.effort,
                          repo_ids=repo_ids, force=args.force, features_only=args.features_only,
                          concurrency=args.concurrency, max_attempts=args.attempts, categories=args.category,
                          refresh_before=args.refresh_before)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


def _prescreen(args: argparse.Namespace) -> int:
    from pickfit.prescreen import run_prescreen

    summary = run_prescreen(limit=args.limit, repo_ids=args.repo, force=args.force,
                            concurrency=args.concurrency, review=not args.no_review, categories=args.category)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _profiles(args: argparse.Namespace) -> int:
    from pickfit.discover.run import pipeline_db_path
    from pickfit.discover.store import PipelineDB
    from pickfit.meta import resolve_model
    from pickfit.profiles import DEFAULT_CATEGORIES, DEFAULT_OUT, write_features, write_profiles

    if args.features_only:
        summary = write_features(PipelineDB(pipeline_db_path()), model=resolve_model(args.model),
                                 out_dir=args.out or DEFAULT_OUT, slugs=args.slug, dry_run=args.dry_run,
                                 log=lambda line: print(line, file=sys.stderr))
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
        return 0
    summary = write_profiles(PipelineDB(pipeline_db_path()), model=resolve_model(args.model),
                             out_dir=args.out or DEFAULT_OUT,
                             categories=tuple(args.category or DEFAULT_CATEGORIES),
                             dry_run=args.dry_run, log=lambda line: print(line, file=sys.stderr))
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _webapps(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from pickfit.discover import webapps
    from pickfit.discover.github import GitHub, GitHubError, github_token
    from pickfit.discover.run import pipeline_db_path
    from pickfit.discover.showhn import HN
    from pickfit.ledger import taipei_now

    db = webapps.WebSites(pipeline_db_path())
    log = lambda line: print(line, file=sys.stderr)  # noqa: E731
    if args.action == "funnel":
        print(json.dumps(webapps.funnel(db), ensure_ascii=False, indent=2))
        return 0
    if args.action == "purge":
        print(json.dumps({"pages_dropped": db.purge_pages()}))
        return 0
    if args.action == "recheck-terms":
        print(json.dumps(webapps.recheck_terms(db, log=log)))
        return 0
    if args.action == "extract":
        from pickfit.extract import run_extract
        from pickfit.webrecords import web_candidate

        sites = [web_candidate(r) for r in db.rows(outcome="selected")]
        summary = run_extract(limit=args.limit or max(1, len(sites)), model=args.model, reasoning_effort=args.effort,
                              candidates=sites, force=args.force, concurrency=args.concurrency, log=log)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["errors"] == 0 else 1
    if args.action == "records":
        from pickfit.meta import resolve_model
        from pickfit.webrecords import write_web_records

        if not args.dry_run:
            webapps.probe_https(db, log=log)
        summary = write_web_records(db, model=resolve_model(args.model), dry_run=args.dry_run, log=log)
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
        return 0
    try:
        gh = GitHub(github_token())
    except GitHubError as err:
        print(f"pickfit webapps: {err}", file=sys.stderr)
        return 2
    run_id = f"webapps-{args.action}-" + taipei_now().strftime("%Y%m%d-%H%M%S")
    out = []
    for source in args.source or webapps.SOURCES:
        if args.action == "gather":
            out.append(webapps.run_gather(db, source=source, hn=HN(), gh=gh, now=datetime.now(UTC), days=args.days,
                                          per_query=args.per_query, run_id=run_id, log=log).to_dict())
        elif args.action == "recheck-thin":
            out.append(webapps.recheck_thin(db, source=source, quota=args.quota, seed=args.seed, hn=HN(), gh=gh,
                                            run_id=run_id, log=log, review=not args.no_review))
        else:
            taken = {r["site_key"] for r in db.rows() if r["source"] != source and r["outcome"] in webapps.PASSED}
            out.append(webapps.run_pick(db, source=source, quota=args.quota, seed=args.seed, hn=HN(), gh=gh,
                                        run_id=run_id, concurrency=args.concurrency, max_checks=args.max_checks,
                                        taken=taken, log=log, review=not args.no_review))
    print(json.dumps({"run_id": run_id, "results": out}, ensure_ascii=False, indent=2))
    return 0


def _funnel(args: argparse.Namespace) -> int:
    from pickfit.discover.run import pipeline_db_path, prescreen_status
    from pickfit.discover.store import PipelineDB

    print(json.dumps(PipelineDB(pipeline_db_path()).funnel(prescreen_status()),
                     ensure_ascii=False, indent=2))
    return 0


def _add_pipeline_commands(sub: argparse._SubParsersAction) -> None:
    from pickfit.discover.github import PUSHED_DAYS, RATE_LIMIT_MAX_WAIT_S, STARS, TOPICS
    from pickfit.discover.run import CHANNELS, DEFAULT_PER_QUERY, DEFAULT_SEED
    from pickfit.discover.showhn import DEFAULT_DAYS
    from pickfit.schema import LISTED_CATEGORIES

    d = sub.add_parser("discover", help="find candidates (GitHub search, Show HN, Flathub, Homebrew Cask), "
                                        "fetch details, apply rules ($0)")
    d.add_argument("--channel", choices=CHANNELS, default="github",
                   help="github: topic searches per category (default); show_hn: recent Show HN posts "
                        "that point to a GitHub repo; flathub, homebrew_cask: the store's catalog under "
                        "neutral rules (docs/source-terms.md)")
    d.add_argument("--repo", action="append", metavar="OWNER/NAME",
                   help="no search: store this repository (owner/name or its github.com URL; repeatable) with its "
                        "README, files and rule label, so extract and verify can select it by --repo. For a record "
                        "whose candidate is in another machine's database")
    d.add_argument("--pick", type=int, default=0,
                   help="flathub, homebrew_cask: list a batch of N candidates and fetch their details")
    d.add_argument("--seed", default=DEFAULT_SEED,
                   help=f"flathub, homebrew_cask: the batch is ordered by sha256(seed:app id) (default {DEFAULT_SEED})")
    d.add_argument("--days", type=int, default=DEFAULT_DAYS,
                   help=f"show_hn: posts from the last N days (default {DEFAULT_DAYS})")
    d.add_argument("--per-query", type=int, default=DEFAULT_PER_QUERY,
                   help=f"github: results to take from each search query (default {DEFAULT_PER_QUERY}, max 1000)")
    d.add_argument("--pushed-days", type=int, default=PUSHED_DAYS,
                   help=f"github: only repos pushed in the last N days (default {PUSHED_DAYS})")
    d.add_argument("--category", action="append", choices=sorted(TOPICS),
                   help="limit to one category (repeatable; default all)")
    d.add_argument("--stars", default=STARS,
                   help=f"github: star band, e.g. 301..5000 for rule github-well-known.v1 (default {STARS})")
    d.add_argument("--cap", type=int, default=None,
                   help="github: keep only the first N new repos, round-robin by rank across the queries, "
                        "skipping repos that already have a record (default: keep all)")
    d.add_argument("--skip-details", action="store_true",
                   help="only search; do not fetch README, releases or files")
    d.add_argument("--max-rate-wait", type=float, default=RATE_LIMIT_MAX_WAIT_S,
                   help=f"seconds to wait for a GitHub rate-limit reset before failing (default "
                        f"{RATE_LIMIT_MAX_WAIT_S:.0f}; the REST limit resets hourly, so a bulk run needs ~3700)")
    d.set_defaults(func=_discover)

    from pickfit.prescreen import DEFAULT_CONCURRENCY as PRESCREEN_CONCURRENCY

    s = sub.add_parser("prescreen", help="screen rule-passed candidates with the bulk model (Claude Haiku; "
                                         "paid; low-confidence and a 5%% sample reviewed by Claude Opus)")
    s.add_argument("--limit", type=int, required=True, help="candidates to screen in this run")
    s.add_argument("--repo", action="append", help="screen this repo id (gh:<id>) or owner/name")
    s.add_argument("--force", action="store_true", help="screen again even if already screened")
    s.add_argument("--concurrency", type=int, default=PRESCREEN_CONCURRENCY,
                   help=f"candidates in flight at once (default {PRESCREEN_CONCURRENCY})")
    s.add_argument("--no-review", action="store_true", help="screen only; skip the prod-model reviews")
    s.add_argument("--category", action="append", choices=sorted(TOPICS),
                   help="only candidates of this discovery category (repeatable; default all)")
    s.set_defaults(func=_prescreen)

    e = sub.add_parser("extract", help="read candidates with a model into ExtractionResult (paid)")
    e.add_argument("--limit", type=int, required=True, help="candidates to extract in this run")
    e.add_argument("--model", default="prod", help='"prod" (Claude Opus, default), "dev" (Claude Haiku), "open" (the bulk model) or a model id')
    e.add_argument("--effort", default="minimal", help="reasoning effort (default minimal)")
    e.add_argument("--repo", action="append", help="extract this repo id (gh:<id>) or owner/name")
    e.add_argument("--force", action="store_true", help="extract again even if already extracted")
    e.add_argument("--refresh-before", default=None, metavar="VERSION",
                   help="also extract again what an older prompt or renderer read, e.g. p5, web-p2 or r2 "
                        "(by default only a changed README, release, store entry or install page is read again)")
    e.add_argument("--features-only", action="store_true",
                   help="ask only for the main advertised features (records extracted before features existed)")
    e.add_argument("--records", action="store_true", help="the candidates that have a record in data/software")
    e.add_argument("--install-docs", action="store_true",
                   help="first read the install guide a README points to (the repository's own docs, the linked "
                        "page, or the homepage; robots.txt obeyed), for candidates whose extraction by this model "
                        "names no install path the Linux sandbox can run; one that got a page is then extracted "
                        "again, since its sources changed")
    e.add_argument("--concurrency", type=int, default=1, help="calls in flight at once (default 1)")
    e.add_argument("--attempts", type=int, default=2,
                   help="tries per candidate for transient failures (default 2)")
    e.add_argument("--category", action="append", choices=sorted(TOPICS),
                   help="only candidates of this discovery category (repeatable; default all)")
    e.set_defaults(func=_extract)

    p = sub.add_parser("profiles", help="write data/software/<slug>.json from stored extractions ($0)")
    p.add_argument("--model", default="prod", help='extractions by this model: "prod" (default), "dev", "open" or an id')
    p.add_argument("--category", action="append", choices=[*LISTED_CATEGORIES, "other"],
                   help="categories to write (repeatable; default " + ", ".join(LISTED_CATEGORIES) + ")")
    p.add_argument("--out", type=Path, default=None, help="output directory (default data/software)")
    p.add_argument("--dry-run", action="store_true", help="build and validate, write nothing")
    p.add_argument("--features-only", action="store_true",
                   help="only set the advertised features (and their evidence) on existing records")
    p.add_argument("--slug", action="append", help="--features-only: only this record (repeatable)")
    p.set_defaults(func=_profiles)

    from pickfit.discover import webapps

    wa = sub.add_parser("webapps", help="hosted web apps (P2.8): gather Show HN and GitHub rows under neutral "
                                        "rules ($0), pick and check sites in hash order (Spark Open screen, paid)")
    wa.add_argument("action", choices=["gather", "pick", "funnel", "recheck-terms", "recheck-thin", "extract",
                                       "records", "purge"],
                    help="gather: rules 1-3; pick: rules 4-8 until each source has its quota; funnel: counts; "
                         "recheck-terms: rule 7 again for passed sites; recheck-thin: rules 4-8 again, rendered, for "
                         "sites whose page showed no text before rendering; extract: selected sites with a Meta "
                         "model (paid); records: write new web_app records ($0); purge: drop stored page text. "
                         "Rendering needs `uv run --with playwright`")
    wa.add_argument("--source", action="append", choices=webapps.SOURCES, help="one source (default both)")
    wa.add_argument("--days", type=int, default=webapps.DEFAULT_DAYS,
                    help=f"show_hn: posts from the last N days (default {webapps.DEFAULT_DAYS})")
    wa.add_argument("--per-query", type=int, default=1000, help="github: results per topic query (max 1000)")
    wa.add_argument("--quota", type=int, default=50, help="pick: sites to select per source (default 50)")
    wa.add_argument("--seed", default=webapps.DEFAULT_SEED, help=f"pick order seed (default {webapps.DEFAULT_SEED})")
    wa.add_argument("--concurrency", type=int, default=4, help="pick: sites checked at once (default 4)")
    wa.add_argument("--max-checks", type=int, default=None, help="pick: stop after checking N sites")
    wa.add_argument("--no-review", action="store_true", help="pick: skip the prod-model reviews")
    wa.add_argument("--model", default="prod", help='extract, records: "prod" (Claude Opus, default) or a model id')
    wa.add_argument("--effort", default="minimal", help="extract: reasoning effort (default minimal)")
    wa.add_argument("--limit", type=int, default=None, help="extract: at most N sites (default all selected)")
    wa.add_argument("--force", action="store_true", help="extract: again even if already extracted")
    wa.add_argument("--dry-run", action="store_true", help="records: build and validate, write nothing")
    wa.set_defaults(func=_webapps)

    f = sub.add_parser("funnel", help="counts, models and cost per funnel stage from runs/pipeline.db")
    f.set_defaults(func=_funnel)


# --- scoring (P5.1) ---------------------------------------------------------------


def _add_score_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.score import DEFAULT_CONCURRENCY, main_score

    s = sub.add_parser("score", help="quality, popularity and treasure scores for data/software (rubric call is paid)")
    s.add_argument("--slug", action="append", help="score only this record (repeatable; default all)")
    s.add_argument("--kind", default=None, help="score only records of this kind, e.g. web_app (with --slug: both)")
    s.add_argument("--limit", type=int, default=None, help="score at most N records (in slug order)")
    s.add_argument("--data-dir", default=None, help="records to score (default data/software)")
    s.add_argument("--db", default=None, help="pipeline database with the GitHub snapshots (default runs/pipeline.db)")
    s.add_argument("--model", default="prod", help='rubric model: "prod" (default), "dev" or a model id')
    s.add_argument("--force", action="store_true", help="grade the README again even if it has not changed")
    s.add_argument("--no-github", action="store_true",
                   help="no GitHub calls: keep the stored responsiveness; no live snapshots for repos not in --db")
    s.add_argument("--no-registries", action="store_true",
                   help="no npm, PyPI, crates.io, Homebrew or Hacker News lookups: keep the stored signals")
    s.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="records at once")
    s.add_argument("--refresh", action="store_true",
                   help="recompute only what follows the record (sandbox, usage, cap, total, treasure) and move a "
                        "refreshable older formula to this one; no GitHub, registry or model call")
    s.add_argument("--dry-run", action="store_true", help="compute and print; write nothing")
    s.add_argument("--verbose", action="store_true", help="print every record's scores")
    s.set_defaults(func=main_score)


def _add_security_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.security import main_security

    s = sub.add_parser("security", help="known vulnerabilities in what the software brings, judged by where they sit "
                                        "and whether they run (sec.v2: OSV.dev, CISA KEV, FIRST EPSS; no model call, "
                                        "$0); --write stores security and data/security/<slug>.json")
    s.add_argument("--slug", action="append", help="check this record (repeatable)")
    s.add_argument("--all", action="store_true", help="every listed record")
    s.add_argument("--unchecked", action="store_true", help="listed records not checked yet or left unchecked")
    s.add_argument("--stale-days", type=int, default=None, metavar="N",
                   help="listed records not checked in the last N days (advisories keep changing; e.g. 14)")
    s.add_argument("--reassess", action="store_true",
                   help="print each record's sec.v2 level from what it already stores (no package lookups); "
                        "never writes")
    s.add_argument("--offline-intel", action="store_true", help="skip CISA KEV and FIRST EPSS (kev, epss stay null)")
    s.add_argument("--gaps", action="store_true",
                   help="print what could not be checked, grouped by gap code, ecosystem, category and platform "
                        "(every listed record unless --slug/--all narrow it); reads only, never writes")
    s.add_argument("--data-dir", default=None, help="records (default data/software)")
    s.add_argument("--workers", type=int, default=6, help="records checked at once")
    s.add_argument("--write", action="store_true", help="store each check in its record and refresh its scores")
    s.add_argument("--report", default=None, help="write every record's result and score change to this JSON file")
    s.add_argument("--verbose", action="store_true", help="print each record's status")
    s.set_defaults(func=main_security)


def _add_visual_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.usability import VISUAL_CAP_USD, main_visual

    v = sub.add_parser("visual", help="measurable visual defects of desktop and web apps from pickfit's own "
                                      "screenshots (one model call each, paid); --write adds visual_check")
    v.add_argument("--slug", action="append", help="check this record (repeatable)")
    v.add_argument("--pilot", action="store_true", help="the 12 apps in data/calibration/ease-pilot.json")
    v.add_argument("--all", action="store_true", help="every desktop_app and web_app with copied evidence")
    v.add_argument("--data-dir", default=None, help="records (default data/software)")
    v.add_argument("--cap", type=float, default=VISUAL_CAP_USD, help="this run's ledger cap in USD")
    v.add_argument("--force", action="store_true", help="check again even when the screens and prompt are the same")
    v.add_argument("--write", action="store_true", help="add each result to its record as visual_check")
    v.add_argument("--dry-run", action="store_true", help="count what would be checked and estimate the cost")
    v.add_argument("--verbose", action="store_true", help="print each record's score")
    v.set_defaults(func=main_visual)


def _add_usability_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.usability import COMFORT_MODEL, MODEL, SAMPLES, STAGE_CAP_USD, main_usability

    u = sub.add_parser("usability", help="how easy GUI and web apps are to use, from pickfit's own screenshots "
                                         "(Claude Opus, paid; prints costs, never the scores)")
    u.add_argument("--slug", action="append", help="judge this record (repeatable)")
    u.add_argument("--pilot", action="store_true", help="judge the 12 apps in data/calibration/ease-pilot.json")
    u.add_argument("--data-dir", default=None, help="records (default data/software)")
    u.add_argument("--model", default=MODEL, help='"prod" (Claude Opus, default) or a model id')
    u.add_argument("--samples", type=int, default=SAMPLES, help="times each call is made")
    u.add_argument("--comfort-model", default=COMFORT_MODEL,
                   help=f'who lists measurable visual defects for comfortable, one call (default {COMFORT_MODEL}, '
                        'effort medium); "same" leaves comfortable to the main judge\'s checks')
    u.add_argument("--cap", type=float, default=STAGE_CAP_USD, help="the stage's ledger cap in USD")
    u.add_argument("--out", default=None, help="where results go (default ~/.pickfit/usability)")
    u.add_argument("--write", action="store_true", help="also add each result to its record as `usability`")
    u.add_argument("--dry-run", action="store_true", help="build the inputs and run OCR; no model call")
    u.set_defaults(func=main_usability)


# --- submissions and reported failures (P5.2, P5.3) ----------------------------------


def _d1(args: argparse.Namespace):
    from pickfit.d1 import D1

    return D1(remote=not args.local, worker_dir=args.worker)


def _queue_status(d1) -> int:
    """Read-only: what waits in D1 for `pickfit watch` and `pickfit reverify`."""
    from pickfit.d1 import D1Error
    from pickfit.reverify import pending

    try:
        subs = d1.query("SELECT id, url, status, slug, reason, submitted_at, updated_at FROM submissions "
                        "ORDER BY submitted_at DESC LIMIT 20")
        reports = pending(d1, 20)
    except D1Error as err:
        print(f"pickfit: {err}", file=sys.stderr)
        return 2
    print(json.dumps({"d1": d1.where, "submissions": subs, "reverify_pending": [vars(r) for r in reports]},
                     ensure_ascii=False, indent=2))
    return 0


def _watch(args: argparse.Namespace) -> int:
    from pickfit.discover.github import GitHubError, runs_dir
    from pickfit.discover.run import pipeline_db_path
    from pickfit.ledger import default_ledger
    from pickfit.watch import Settings, Watcher, live_data_sha, live_steps

    from pickfit.lanes import ALL_LANES

    lanes = tuple(dict.fromkeys(n.strip() for n in args.lanes.split(",") if n.strip()))
    unknown = [n for n in lanes if n not in ALL_LANES]
    if unknown or "linux" not in lanes:
        print(f"pickfit watch: --lanes takes {','.join(ALL_LANES)} and always has linux "
              f"(got {args.lanes})", file=sys.stderr)
        return 2
    d1 = _d1(args)
    if args.status:
        code = _queue_status(d1)
        if code == 0:
            from pickfit.watch import lane_status

            print(json.dumps({"lanes": lane_status(runs_dir() / "watch" / "jobs", _watch_lanes(args, lanes),
                                                   now=None)}, ensure_ascii=False, indent=2))
            status = runs_dir() / "watch" / "status.json"  # the running watcher's last tick, when there is one
            if status.exists():
                print(json.dumps({"watch": json.loads(status.read_text(encoding="utf-8"))}, ensure_ascii=False,
                                 indent=2))
        return code
    if args.publish and args.no_commit:
        print("pickfit watch: --publish deploys committed data only; drop --no-commit", file=sys.stderr)
        return 2
    if args.publish and args.reverify:
        print("pickfit watch: --reverify rewrites steps from a user's report; read its diff and publish yourself, "
              "so not with --publish", file=sys.stderr)
        return 2
    from pickfit.env import REPO_ROOT
    from pickfit.watch import env_defaults

    try:
        env = env_defaults()
    except ValueError as err:
        print(f"pickfit watch: {err}", file=sys.stderr)
        return 2
    picked = {key: env[key] if getattr(args, key) is None else getattr(args, key) for key in env}
    settings = Settings(data_dir=args.data, runs_dir=runs_dir(), db_path=pipeline_db_path(), worker_dir=args.worker,
                        commit=not args.no_commit, publish=bool(args.publish), max_usd=args.max_usd,
                        budget_path=REPO_ROOT / "loop" / "budget.json", interval_s=args.interval, lanes=lanes,
                        publish_mode=args.publish or "deploy", update_check_s=args.update_check_hours * 3600,
                        **picked)
    try:
        steps = live_steps(runner=args.runner)
    except GitHubError as err:
        print(f"pickfit watch: {err}", file=sys.stderr)
        return 2
    steps.lanes = _watch_lanes(args, lanes)
    if "web" in lanes:
        import importlib.util

        from pickfit.web_intake import live_site_steps

        steps.site = live_site_steps(runner=args.runner if args.runner in ("modal", "ec2") else "modal")
        if importlib.util.find_spec("playwright") is None:
            print("pickfit watch: playwright is missing, so sites drawn by script are tried again later instead of "
                  "read; run `uv run --with playwright pickfit watch ...`", file=sys.stderr)
    reverifier = None
    if args.reverify:
        from pickfit.reverify import Reverifier
        from pickfit.reverify import live_steps as reverify_steps

        reverifier = Reverifier(d1, reverify_steps(runner=args.runner), data_dir=args.data, runs_dir=runs_dir(),
                                db_path=pipeline_db_path(), commit=not args.no_commit,
                                log=lambda line: print(line, flush=True))
    watcher = Watcher(d1, steps, settings, meta_ledger=default_ledger(),
                      reverifier=reverifier, log=lambda line: print(line, flush=True),
                      live_sha=None if args.local else live_data_sha(args.worker))
    mac = steps.lanes.get("macos")
    cap, cap_from = watcher.daily_cap()
    slots = " ".join(f"{slot} {watcher.slot_limit(slot)}" for slot in ("linux", "web", *watcher.lanes)
                     if slot != "web" or "web" in lanes)
    print(f"watch · {d1.where} · polls every {args.interval:.0f}s, and at once when a job ends · slots {slots}, "
          f"harvest {settings.harvest_slots} · ${cap:g} a rolling 24 h ({cap_from})"
          f"{f', ${settings.user_reserve_usd:g} kept for people' if settings.harvest_slots else ''}"
          f"{f' · --max-usd {args.max_usd}' if args.max_usd is not None else ''}"
          f"{f' · hourly cap {settings.hourly_cap}' if settings.hourly_cap else ''} · {args.runner} · "
          f"{'commit + push (CI deploys)' if args.publish == 'push' else 'commit + publish' if args.publish else 'commit, no deploy' if settings.commit else 'no commit'}"
          f"{' · reverify queue too' if reverifier else ''} · lanes {','.join(lanes)}"
          + (f" · macOS batch {mac.policy.describe()}, "
             f"{'rents up to ' + str(mac.max_rentals) + ' a week' if mac.rent else 'no renting'}" if mac else ""))
    try:
        jobs = watcher.run(once=args.once)
    except KeyboardInterrupt:
        print("watch: stopped")
        return 0
    for job in jobs:
        print(job.summary())
    return 75 if watcher.restart_wanted else 0  # EX_TEMPFAIL: its service starts it again on the new code


def _e2e(args: argparse.Namespace) -> int:
    """pickfit's end-to-end test (pickfit.e2e): test submissions through the live site, never published."""
    import shutil
    import subprocess
    from datetime import timedelta

    from pickfit import e2e
    from pickfit.discover.github import runs_dir

    try:
        lanes = e2e.lanes_from(args.lanes)
    except ValueError as err:
        print(f"pickfit e2e: {err}", file=sys.stderr)
        return 2
    if args.dry_run:
        for name in lanes:
            c = e2e.CANARIES[name]
            print(f"{name}: expects {c.expect} via {c.via} within {c.timeout} · {', '.join(c.urls)}\n    {c.what}")
        return 0
    if not args.no_service_check and shutil.which("systemctl"):
        state = subprocess.run(["systemctl", "is-active", "pickfit-watch"], capture_output=True, text=True).stdout
        if state.strip() != "active":
            print(f"pickfit e2e: pickfit-watch is {state.strip() or 'not running'}; the test follows submissions "
                  "through the running watcher, so start it first (or pass --no-service-check)", file=sys.stderr)
            return 2
    timeouts = {name: timedelta(minutes=args.timeout_minutes) for name in lanes} if args.timeout_minutes else None
    site = e2e.Site(args.site)
    runner = e2e.Runner(_d1(args), site, runs_dir=runs_dir(), data_dir=args.data, lanes=lanes,
                        hosts=[site, *(e2e.Site(h) for h in args.also_host)], keep=args.keep, timeouts=timeouts,
                        log=lambda line: print(line, flush=True))
    return 0 if runner.run().ok else 1


def _watch_lanes(args: argparse.Namespace, lanes: tuple[str, ...]) -> dict[str, Any]:
    """The parked lanes `pickfit watch` takes (pickfit.lanes): Windows on EC2, macOS on a Mac host."""
    from datetime import timedelta

    from pickfit.lanes import Policy, windows_lane
    from pickfit.watch import MODEL

    out: dict[str, Any] = {}
    if "windows" in lanes:
        out["windows"] = windows_lane(model=MODEL)
    if "macos" in lanes:
        from pickfit.verify.mac_batch import MacLane

        out["macos"] = MacLane(model=MODEL, policy=Policy(min_batch=args.mac_batch,
                                                          max_wait=timedelta(hours=args.mac_max_wait_hours)),
                               rent=args.mac_rent, provider=args.mac_provider, zone=args.mac_zone,
                               root_from_provider=args.mac_root_from_provider, max_rentals=args.mac_max_rentals)
    return out


def _reverify(args: argparse.Namespace) -> int:
    from pickfit.discover.github import GitHubError, runs_dir
    from pickfit.discover.run import pipeline_db_path
    from pickfit.ledger import default_ledger
    from pickfit.reverify import Reverifier, live_steps
    from pickfit.watch import WORST_CASE_META_USD, budget_blocked

    d1 = _d1(args)
    if args.list:
        return _queue_status(d1)
    try:
        steps = live_steps(runner=args.runner)
    except GitHubError as err:
        print(f"pickfit reverify: {err}", file=sys.stderr)
        return 2
    reverifier = Reverifier(d1, steps, data_dir=args.data, runs_dir=runs_dir(), db_path=pipeline_db_path(),
                            commit=not args.no_commit, log=lambda line: print(line, flush=True))
    ledger = default_ledger()
    results = reverifier.run(args.limit, blocked=lambda: budget_blocked(
        [("Model pipeline", ledger, WORST_CASE_META_USD)]))
    print(json.dumps([{k: v for k, v in vars(r).items() if k != "diff"} for r in results], ensure_ascii=False,
                     indent=2))
    return 0 if all(r.outcome != "retry" for r in results) else 1


def _add_queue_commands(sub: argparse._SubParsersAction) -> None:
    from pickfit.d1 import DEFAULT_WORKER_DIR
    from pickfit.profiles import DEFAULT_OUT
    from pickfit.watch import (DEFAULT_CONCURRENCY, DEFAULT_DAILY_USD, DEFAULT_HARVEST_SLOTS, DEFAULT_INTERVAL_S,
                               DEFAULT_MAX_USD, DEFAULT_USER_RESERVE_USD, DEFAULT_WEB_CONCURRENCY,
                               DEFAULT_WINDOWS_CONCURRENCY, WINDOWS_MAX_BOXES)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--local", action="store_true", help="the local D1 of `wrangler dev` instead of the remote one")
        p.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR,
                       help="the Worker directory (wrangler runs there)")
        p.add_argument("--data", type=Path, default=DEFAULT_OUT, help="records directory (default data/software)")
        p.add_argument("--runner", choices=["modal", "ec2", "docker"], default="modal",
                       help="sandbox for verification")
        p.add_argument("--no-commit", action="store_true", help="write records but do not commit them")

    w = sub.add_parser("watch", help="every 60 s, turn queued submit_software rows into records "
                                     "(paid: prescreen, extraction, verification; deploys only with --publish)")
    common(w)
    w.add_argument("--once", action="store_true", help="take what is queued now, finish it, and stop")
    w.add_argument("--publish", nargs="?", const="deploy", choices=["deploy", "push"], default=None,
                   help="publish each record that passes every check (not with --reverify). deploy (the default) "
                        "deploys the Worker from here; push pushes the commits to origin/main, whose CI deploys "
                        "them (for a watcher on its own machine)")
    w.add_argument("--update-check-hours", type=float, default=0,
                   help="when idle, this often look for new program code on origin/main and stop with exit 75 so "
                        "the service pulls it and starts again (default 0: never)")
    w.add_argument("--reverify", action="store_true", help="also take reported failures from reverify_queue")
    w.add_argument("--status", action="store_true",
                   help="read-only: list submissions, the reverify queue, each lane's parked jobs and the running "
                        "watcher's last status (runs/watch/status.json: running, queued, why nothing new starts)")
    w.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S,
                   help="seconds between polls for new submissions (default 60); a job that ends wakes it sooner")
    # Unset flags take PICKFIT_WATCH_* from the environment (the service's watch.env), else pickfit.watch's default.
    w.add_argument("--concurrency", type=int, default=None,
                   help=f"linux: repository submissions read and verified at once (default {DEFAULT_CONCURRENCY}; "
                        "PICKFIT_WATCH_LINUX_CONCURRENCY)")
    w.add_argument("--web-concurrency", type=int, default=None,
                   help=f"web: website submissions at once (default {DEFAULT_WEB_CONCURRENCY}; "
                        "PICKFIT_WATCH_WEB_CONCURRENCY)")
    w.add_argument("--windows-concurrency", type=int, default=None,
                   help=f"windows: EC2 boxes at once, never more than {WINDOWS_MAX_BOXES} (the account's quota; "
                        f"default {DEFAULT_WINDOWS_CONCURRENCY}; PICKFIT_WATCH_WINDOWS_CONCURRENCY)")
    w.add_argument("--harvest-slots", type=int, default=None,
                   help=f"slots harvest rows may hold in all lanes together; people's submissions go first "
                        f"(default {DEFAULT_HARVEST_SLOTS}; PICKFIT_WATCH_HARVEST_SLOTS)")
    w.add_argument("--user-reserve-usd", type=float, default=None,
                   help=f"of the rolling 24 h money, what a harvest row leaves free for people's submissions "
                        f"(default {DEFAULT_USER_RESERVE_USD:g}; PICKFIT_WATCH_USER_RESERVE_USD)")
    w.add_argument("--daily-usd", type=float, default=None,
                   help="model spend allowed in any rolling 24 hours, counted in the shared ledger (default: "
                        f"loop/budget.json's model_usd.daily, else {DEFAULT_DAILY_USD:g}; PICKFIT_WATCH_DAILY_USD)")
    w.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                   help="optional: stop starting submissions once this run has spent this much on models "
                        "(default none: the rolling 24 h cap holds)")
    w.add_argument("--hourly-cap", type=int, default=None,
                   help="optional: at most this many submissions start in a rolling hour (default 0: none, the "
                        "Worker caps intake; PICKFIT_WATCH_HOURLY_CAP)")
    w.add_argument("--lanes", default="linux,windows,macos,web",
                   help="where submissions are verified (default all): linux at once; windows (EC2) as soon as AWS "
                        "answers; macos in batches on a Mac host; web: website submissions, visited once")
    w.add_argument("--mac-batch", type=int, default=10, help="macOS: start a batch once this many wait (default 10)")
    w.add_argument("--mac-max-wait-hours", type=float, default=24.0,
                   help="macOS: or once the oldest has waited this long (default 24)")
    w.add_argument("--mac-rent", action="store_true",
                   help="macOS: rent a Mac when no known host is ready (Scaleway: billed 24 h at least, about EUR 6)")
    w.add_argument("--mac-max-rentals", type=int, default=1, help="macOS: at most this many rentals a week (default 1)")
    w.add_argument("--mac-provider", default="scaleway", help="macOS: who rents the Mac (default scaleway)")
    w.add_argument("--mac-zone", default=None, help="macOS: the provider's zone (Scaleway default fr-par-1)")
    w.add_argument("--mac-root-from-provider", action="store_true",
                   help="macOS: read a rented Mac's sudo password from the provider and pipe it into its root step "
                        "(never logged or saved); without it the lane waits for `pickfit mac-host root NAME`")
    w.set_defaults(func=_watch)

    t = sub.add_parser("e2e", help="end-to-end test on the watch machine: test submissions through the live website "
                                   "and MCP, followed through the running watcher, never published "
                                   "(paid: a sandbox run per lane)")
    t.add_argument("--local", action="store_true", help="the local D1 of `wrangler dev` instead of the remote one")
    t.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR, help="the Worker directory (wrangler runs there)")
    t.add_argument("--data", type=Path, default=DEFAULT_OUT, help="records directory (default data/software)")
    t.add_argument("--lanes", default="default",
                   help="default (reject, linux, web), all, or names from reject,linux,web,windows,macos joined by "
                        "commas or dashes")
    t.add_argument("--site", default="https://pickfit.app", help="the public site to submit through")
    t.add_argument("--also-host", action="append", default=["https://pickfit-mcp.ncchen99.workers.dev"],
                   help="another host whose served data must match origin/main (repeatable)")
    t.add_argument("--keep", action="store_true", help="leave the D1 rows and job files for a look")
    t.add_argument("--timeout-minutes", type=float, default=None, help="one timeout for every lane")
    t.add_argument("--no-service-check", action="store_true",
                   help="do not require the pickfit-watch service (a watcher started some other way)")
    t.add_argument("--dry-run", action="store_true", help="print the lanes and their test URLs; submit nothing")
    t.set_defaults(func=_e2e)

    r = sub.add_parser("reverify", help="re-verify reported install failures in a fresh box; "
                                        "write back changed steps and show the record's git diff (paid)")
    common(r)
    r.add_argument("--limit", type=int, default=5, help="queued reports to take (default 5)")
    r.add_argument("--list", action="store_true", help="read-only: list submissions and the reverify queue")
    r.set_defaults(func=_reverify)


# --- usage outcomes from D1 ------------------------------------------------------


def _outcomes_sync(args: argparse.Namespace) -> int:
    from pickfit.d1 import D1, D1Error
    from pickfit.ledger import taipei_now
    from pickfit.outcomes import load_exclude, sync

    try:
        exclude = load_exclude(args.exclude)
        return sync(args.data, D1(remote=not args.local, worker_dir=args.worker), now=taipei_now(),
                    dry_run=args.dry_run, exclude=exclude)
    except (D1Error, ValueError) as err:
        print(f"pickfit: {err}", file=sys.stderr)
        return 2


def _add_outcomes_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.d1 import DEFAULT_WORKER_DIR
    from pickfit.profiles import DEFAULT_OUT

    o = sub.add_parser("outcomes", help="usage reports from the Worker's D1")
    osub = o.add_subparsers(dest="outcomes_command", required=True)
    s = osub.add_parser("sync", help="read report_outcome counts from D1 (read-only) into data/software and "
                                     "refresh scores; outside reports only ($0)")
    s.add_argument("--dry-run", action="store_true", help="print what would change per slug; write nothing")
    s.add_argument("--exclude", type=Path, default=None,
                   help="file of rec_ids (one per line, kept outside the repo) to leave out: our own checks "
                        "sent without X-Pickfit-Reporter")
    s.add_argument("--local", action="store_true", help="the local D1 of `wrangler dev` instead of the remote one")
    s.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR, help="the Worker directory (wrangler runs there)")
    s.add_argument("--data", type=Path, default=DEFAULT_OUT, help="records directory (default data/software)")
    s.set_defaults(func=_outcomes_sync)


# --- publish (P4.2) ---------------------------------------------------------------


def _publish(args: argparse.Namespace) -> int:
    from pickfit.publish import publish

    return publish(args.data, args.worker, dry_run=args.dry_run, allow_dirty=args.allow_dirty, env=args.env,
                   translate=not args.no_translate)


def _add_publish_command(sub: argparse._SubParsersAction) -> None:
    from pathlib import Path

    from pickfit.publish import DEFAULT_DATA_DIR, DEFAULT_WORKER_DIR

    p = sub.add_parser("publish", help="validate data/software, build the Worker index, wrangler deploy")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="directory of <slug>.json")
    p.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR, help="the Worker directory")
    p.add_argument("--dry-run", action="store_true", help="run every check and print the plan; deploy nothing")
    p.add_argument("--allow-dirty", action="store_true", help="publish even if data/software has uncommitted changes")
    p.add_argument("--env", help="deploy the env.<NAME> section of wrangler.jsonc (e.g. a frozen evaluation deployment)")
    p.add_argument("--no-translate", action="store_true",
                   help="skip translating new page sentences into zh-TW (Claude Opus, at most $1)")
    p.set_defaults(func=_publish)



# --- harvest: leads from many sources -----------------------------------------------


def _add_harvest_command(sub: argparse._SubParsersAction) -> None:
    from pickfit.harvest.leads import KINDS, PLATFORMS
    from pickfit.harvest.sources import DEFAULT_SOURCES, SOURCES

    h = sub.add_parser("harvest", help="collect leads from package registries, the MCP Registry, awesome lists, "
                                       "GitHub, HN and (with keys) Bluesky and X into runs/harvest.db ($0 except X)")
    h.add_argument("action", choices=["run", "summary", "top", "export", "feed"],
                   help="run: read the sources; summary: counts; top: best new leads; export: JSON lines; "
                        "feed: queue the best new leads as submit_software rows for `pickfit watch`")
    h.add_argument("--source", action="append", choices=sorted(SOURCES),
                   help=f"run: one source (repeatable; default {', '.join(DEFAULT_SOURCES)})")
    h.add_argument("--limit", type=int, default=5000, help="run: hits per source (default 5000)")
    h.add_argument("--days", type=int, default=7, help="run: look-back days of HN, winget, Bluesky (default 7)")
    h.add_argument("--x-max-reads", type=int, default=100,
                   help="run: paid X post reads per run, $0.005 each (default 100)")
    h.add_argument("-n", type=int, default=20, help="top, export, feed: how many (default 20)")
    h.add_argument("--kind", action="append", choices=KINDS, help="top, export, feed: only this kind hint")
    h.add_argument("--platform", action="append", choices=PLATFORMS, help="top, feed: only this platform")
    h.add_argument("--out", type=Path, default=None, help="export: file (default runs/harvest/leads-<date>.jsonl)")
    h.add_argument("--apply", action="store_true", help="feed: write to D1 (default: show what would be queued)")
    h.add_argument("--local", action="store_true", help="feed: the local D1 of `wrangler dev`")
    h.add_argument("--worker", type=Path, default=Path("worker"), help="feed: the Worker directory")
    h.set_defaults(func=_harvest)


def _harvest(args: argparse.Namespace) -> int:
    from pickfit.harvest.leads import LeadsDB
    from pickfit.harvest.run import export, feed, harvest_db_path, run_harvest
    from pickfit.ledger import taipei_now

    kinds = set(args.kind) if args.kind else None
    platforms = set(args.platform) if args.platform else None
    if args.action == "run":
        report = run_harvest(args.source, limit=args.limit, days=args.days, x_max_reads=args.x_max_reads,
                             log=lambda line: print(line, file=sys.stderr))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if not all(s["error"] for s in report["sources"].values()) else 1
    if args.action == "feed":
        from pickfit.d1 import D1
        from pickfit.watch import hourly_cap

        rows = feed(D1(remote=not args.local, worker_dir=args.worker), n=args.n, hourly_cap=hourly_cap(args.worker),
                    apply=args.apply, kinds=kinds, platforms=platforms, log=lambda line: print(line, file=sys.stderr))
        print(json.dumps({"applied": args.apply, "rows": rows}, indent=2, ensure_ascii=False))
        return 0
    if args.action == "export":
        out = args.out or harvest_db_path().parent / "harvest" / f"leads-{taipei_now().date().isoformat()}.jsonl"
        print(f"{export(out, limit=args.n or None)} leads -> {out}")
        return 0
    db = LeadsDB(harvest_db_path())
    try:
        if args.action == "summary":
            print(json.dumps(db.summary(), indent=2, ensure_ascii=False))
        else:
            for lead in db.ranked(kinds=kinds, platforms=platforms, limit=args.n):
                print(f"{lead['priority']:6.2f}  {lead['kind_hint']:<20} {lead['url']}  "
                      f"[{'+'.join(lead['sources'])}; signal {lead['best_signal']}]")
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pickfit")
    parser.add_argument("--version", action="version", version=f"pickfit {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ping", help="make the smallest possible model call through call_meta")
    p.add_argument("--provider", default="anthropic", choices=["anthropic", "meta", "baseten"],
                   help="anthropic (default); meta and baseten are the hackathon's providers")
    p.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE, else prod)')
    p.set_defaults(func=_ping)

    s = sub.add_parser("spend", help="show spending from the shared ledger")
    s.set_defaults(func=_spend)

    _add_pipeline_commands(sub)
    _add_score_command(sub)
    _add_usability_command(sub)
    _add_visual_command(sub)
    _add_security_command(sub)
    from pickfit.coverage import add_parser as add_coverage_parser
    add_coverage_parser(sub)
    _add_queue_commands(sub)
    _add_outcomes_command(sub)
    _add_publish_command(sub)
    _add_harvest_command(sub)

    from pickfit.verify.cli import add_parser as add_verify_parser
    add_verify_parser(sub)
    from pickfit.verify.mac_host import add_parser as add_mac_host_parser
    add_mac_host_parser(sub)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
