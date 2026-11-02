"""Command-line entry point: `uv run pickfit <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    summary = run_extract(limit=args.limit, model=args.model, reasoning_effort=args.effort,
                          repo_ids=repo_ids, force=args.force, features_only=args.features_only,
                          concurrency=args.concurrency, max_attempts=args.attempts, categories=args.category)
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

    s = sub.add_parser("prescreen", help="screen rule-passed candidates with Muse Spark Open on Baseten "
                                         "(paid; low-confidence and a 5%% sample reviewed by muse-spark-1.3)")
    s.add_argument("--limit", type=int, required=True, help="candidates to screen in this run")
    s.add_argument("--repo", action="append", help="screen this repo id (gh:<id>) or owner/name")
    s.add_argument("--force", action="store_true", help="screen again even if already screened")
    s.add_argument("--concurrency", type=int, default=PRESCREEN_CONCURRENCY,
                   help=f"candidates in flight at once (default {PRESCREEN_CONCURRENCY}; Baseten allows 100 RPM)")
    s.add_argument("--no-review", action="store_true", help="screen only; skip muse-spark-1.3 reviews")
    s.add_argument("--category", action="append", choices=sorted(TOPICS),
                   help="only candidates of this discovery category (repeatable; default all)")
    s.set_defaults(func=_prescreen)

    e = sub.add_parser("extract", help="read candidates with a Meta model into ExtractionResult (paid)")
    e.add_argument("--limit", type=int, required=True, help="candidates to extract in this run")
    e.add_argument("--model", default="dev", help='"dev" (contributor, default), "prod", "open" (Muse Spark Open on Baseten) or a model id')
    e.add_argument("--effort", default="minimal", help="reasoning effort (default minimal)")
    e.add_argument("--repo", action="append", help="extract this repo id (gh:<id>) or owner/name")
    e.add_argument("--force", action="store_true", help="extract again even if already extracted")
    e.add_argument("--features-only", action="store_true",
                   help="ask only for the main advertised features (records extracted before features existed)")
    e.add_argument("--records", action="store_true", help="the candidates that have a record in data/software")
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
    wa.add_argument("--no-review", action="store_true", help="pick: skip muse-spark-1.3 reviews")
    wa.add_argument("--model", default="prod", help='extract, records: "prod" (muse-spark-1.3, default) or a model id')
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
    from pickfit.ledger import baseten_ledger, default_ledger
    from pickfit.watch import Settings, Watcher, hourly_cap, live_data_sha, live_steps

    d1 = _d1(args)
    if args.status:
        return _queue_status(d1)
    if args.publish and args.no_commit:
        print("pickfit watch: --publish deploys committed data only; drop --no-commit", file=sys.stderr)
        return 2
    if args.publish and args.reverify:
        print("pickfit watch: --reverify rewrites steps from a user's report; read its diff and publish yourself, "
              "so not with --publish", file=sys.stderr)
        return 2
    settings = Settings(data_dir=args.data, runs_dir=runs_dir(), db_path=pipeline_db_path(), worker_dir=args.worker,
                        commit=not args.no_commit, publish=args.publish, hourly_cap=hourly_cap(args.worker),
                        max_usd=args.max_usd, concurrency=args.concurrency, interval_s=args.interval)
    try:
        steps = live_steps(runner=args.runner)
    except GitHubError as err:
        print(f"pickfit watch: {err}", file=sys.stderr)
        return 2
    reverifier = None
    if args.reverify:
        from pickfit.reverify import Reverifier
        from pickfit.reverify import live_steps as reverify_steps

        reverifier = Reverifier(d1, reverify_steps(runner=args.runner), data_dir=args.data, runs_dir=runs_dir(),
                                db_path=pipeline_db_path(), commit=not args.no_commit,
                                log=lambda line: print(line, flush=True))
    watcher = Watcher(d1, steps, settings, meta_ledger=default_ledger(), baseten_ledger=baseten_ledger(),
                      reverifier=reverifier, log=lambda line: print(line, flush=True),
                      live_sha=None if args.local else live_data_sha(args.worker))
    print(f"watch · {d1.where} · every {args.interval:.0f}s · {args.concurrency} at a time · "
          f"hourly cap {settings.hourly_cap} · --max-usd {args.max_usd} · {args.runner} · "
          f"{'commit + publish' if args.publish else 'commit, no deploy' if settings.commit else 'no commit'}"
          f"{' · reverify queue too' if reverifier else ''}")
    try:
        jobs = watcher.run(once=args.once)
    except KeyboardInterrupt:
        print("watch: stopped")
        return 0
    for job in jobs:
        print(job.summary())
    return 0


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
        [("Meta pipeline", ledger, WORST_CASE_META_USD)]))
    print(json.dumps([{k: v for k, v in vars(r).items() if k != "diff"} for r in results], ensure_ascii=False,
                     indent=2))
    return 0 if all(r.outcome != "retry" for r in results) else 1


def _add_queue_commands(sub: argparse._SubParsersAction) -> None:
    from pickfit.d1 import DEFAULT_WORKER_DIR
    from pickfit.profiles import DEFAULT_OUT
    from pickfit.watch import DEFAULT_CONCURRENCY, DEFAULT_INTERVAL_S, DEFAULT_MAX_USD

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--local", action="store_true", help="the local D1 of `wrangler dev` instead of the remote one")
        p.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR,
                       help="the Worker directory (wrangler runs there)")
        p.add_argument("--data", type=Path, default=DEFAULT_OUT, help="records directory (default data/software)")
        p.add_argument("--runner", choices=["modal", "docker"], default="modal", help="sandbox for verification")
        p.add_argument("--no-commit", action="store_true", help="write records but do not commit them")

    w = sub.add_parser("watch", help="every 60 s, turn queued submit_software rows into records "
                                     "(paid: prescreen, extraction, verification; deploys only with --publish)")
    common(w)
    w.add_argument("--once", action="store_true", help="take what is queued now, finish it, and stop")
    w.add_argument("--publish", action="store_true",
                   help="deploy the Worker (pickfit publish) after each record that passes every check "
                        "(not with --reverify)")
    w.add_argument("--reverify", action="store_true", help="also take reported failures from reverify_queue")
    w.add_argument("--status", action="store_true", help="read-only: list submissions and the reverify queue")
    w.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="seconds between polls (default 60)")
    w.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"submissions processed at once (default {DEFAULT_CONCURRENCY})")
    w.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                   help="stop starting submissions after this much Meta and Baseten spend "
                        f"(default {DEFAULT_MAX_USD})")
    w.set_defaults(func=_watch)

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
                   help="skip translating new page sentences into zh-TW (Muse Spark Open on Modal, at most $1)")
    p.set_defaults(func=_publish)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pickfit")
    parser.add_argument("--version", action="version", version=f"pickfit {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ping", help="make the smallest possible model call through call_meta")
    p.add_argument("--provider", default="meta", choices=["meta", "baseten"])
    p.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE)')
    p.set_defaults(func=_ping)

    s = sub.add_parser("spend", help="show spending from the shared ledger")
    s.set_defaults(func=_spend)

    _add_pipeline_commands(sub)
    _add_score_command(sub)
    _add_queue_commands(sub)
    _add_outcomes_command(sub)
    _add_publish_command(sub)

    from pickfit.verify.cli import add_parser as add_verify_parser
    add_verify_parser(sub)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
