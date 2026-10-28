"""Command-line entry point: `uv run pickfit <command>`."""

from __future__ import annotations

import argparse
import json
import sys

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
    funnel = run_discover(token=token, per_query=args.per_query, pushed_days=args.pushed_days,
                          categories=args.category, skip_details=args.skip_details)
    print(json.dumps(funnel, ensure_ascii=False, indent=2))
    return 0


def _extract(args: argparse.Namespace) -> int:
    from pickfit.extract import run_extract

    summary = run_extract(limit=args.limit, model=args.model, reasoning_effort=args.effort,
                          repo_ids=args.repo, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


def _funnel(args: argparse.Namespace) -> int:
    from pickfit.discover.run import pipeline_db_path, prescreen_status
    from pickfit.discover.store import PipelineDB

    print(json.dumps(PipelineDB(pipeline_db_path()).funnel(prescreen_status()),
                     ensure_ascii=False, indent=2))
    return 0


def _add_pipeline_commands(sub: argparse._SubParsersAction) -> None:
    from pickfit.discover.github import PUSHED_DAYS, TOPICS
    from pickfit.discover.run import DEFAULT_PER_QUERY

    d = sub.add_parser("discover", help="search GitHub for candidates, fetch details, apply rules ($0)")
    d.add_argument("--per-query", type=int, default=DEFAULT_PER_QUERY,
                   help=f"results to take from each search query (default {DEFAULT_PER_QUERY}, max 1000)")
    d.add_argument("--pushed-days", type=int, default=PUSHED_DAYS,
                   help=f"only repos pushed in the last N days (default {PUSHED_DAYS})")
    d.add_argument("--category", action="append", choices=sorted(TOPICS),
                   help="limit to one category (repeatable; default all)")
    d.add_argument("--skip-details", action="store_true",
                   help="only search; do not fetch README, releases or files")
    d.set_defaults(func=_discover)

    e = sub.add_parser("extract", help="read candidates with a Meta model into ExtractionResult (paid)")
    e.add_argument("--limit", type=int, required=True, help="candidates to extract in this run")
    e.add_argument("--model", default="dev", help='"dev" (contributor, default), "prod", or a model id')
    e.add_argument("--effort", default="minimal", help="reasoning effort (default minimal)")
    e.add_argument("--repo", action="append", help="extract this repo id (gh:<id>) or owner/name")
    e.add_argument("--force", action="store_true", help="extract again even if already extracted")
    e.set_defaults(func=_extract)

    f = sub.add_parser("funnel", help="counts, models and cost per funnel stage from runs/pipeline.db")
    f.set_defaults(func=_funnel)


# --- publish (P4.2) ---------------------------------------------------------------


def _publish(args: argparse.Namespace) -> int:
    from pickfit.publish import publish

    return publish(args.data, args.worker, dry_run=args.dry_run, allow_dirty=args.allow_dirty, env=args.env)


def _add_publish_command(sub: argparse._SubParsersAction) -> None:
    from pathlib import Path

    from pickfit.publish import DEFAULT_DATA_DIR, DEFAULT_WORKER_DIR

    p = sub.add_parser("publish", help="validate data/software, build the Worker index, wrangler deploy")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="directory of <slug>.json")
    p.add_argument("--worker", type=Path, default=DEFAULT_WORKER_DIR, help="the Worker directory")
    p.add_argument("--dry-run", action="store_true", help="run every check and print the plan; deploy nothing")
    p.add_argument("--allow-dirty", action="store_true", help="publish even if data/software has uncommitted changes")
    p.add_argument("--env", help="deploy the env.<NAME> section of wrangler.jsonc (e.g. a frozen evaluation deployment)")
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
