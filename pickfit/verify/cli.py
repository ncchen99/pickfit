"""`pickfit verify`: agent, replay and judge for a fixture or a batch, in Docker or on Modal."""

from __future__ import annotations

import argparse
import json

LIFETIME_MARGIN_S = 120  # the box outlives the agent's time limit, so the last turn still has it


def add_parser(sub: argparse._SubParsersAction) -> None:
    v = sub.add_parser("verify", help="install, smoke-test, replay and judge one tool in a sandbox with Muse Spark")
    v.add_argument("--fixture", help="JSON with slug, repo_url, readme_url and an ExtractionResult")
    v.add_argument("--batch", type=int, metavar="N", help="verify N extracted candidates from the pipeline database")
    v.add_argument("--concurrency", type=int, default=5, help="batch: tools verified at once (default 5)")
    v.add_argument("--db", default=None, help="batch: pipeline database (default runs/pipeline.db), read-only")
    v.add_argument("--repo", action="append", help="batch: only this repo id (gh:<id>) or owner/name")
    v.add_argument("--records", action="store_true",
                   help="batch: only candidates that have a record in --data-dir (the profiles)")
    v.add_argument("--category", action="append", choices=["dev_cli", "local_ai"],
                   help="batch: only this category (repeatable)")
    v.add_argument("--force", action="store_true", help="batch: also tools that already have a run")
    v.add_argument("--since", metavar="YYYYmmdd-HHMMSS",
                   help="batch: skip only tools with a run started at or after this Taipei time")
    v.add_argument("--data-dir", default=None,
                   help="records to take slugs from and write back to (default data/software)")
    v.add_argument("--dry-run", action="store_true", help="batch: list what would run and why others are skipped")
    v.add_argument("--runner", choices=["docker", "modal"], default="docker",
                   help="local DockerBox (development) or ModalBox (gVisor on Modal)")
    v.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE)')
    v.add_argument("--mode", choices=["chain", "replay"], default=None,
                   help="carry history by previous_response_id (chain) or resend it (replay)")
    v.add_argument("--max-turns", type=int, default=None, help="turn limit (default 25)")
    v.add_argument("--platform", default="linux/amd64", help="Docker platform (Modal runs x86_64)")
    v.add_argument("--keep-box", action="store_true", help="Docker: leave the agent's container running")
    v.add_argument("--write-back", action="store_true",
                   help="record a passed, replayed run in data/software/<slug>.json")
    v.add_argument("--limits-test", action="store_true",
                   help="no model: check the box's limits (user, metadata, network cut, memory, disk, pids)")
    v.set_defaults(func=run)


def box_factory(runner: str, lifetime_s: int, *, platform: str = "linux/amd64"):
    """(run_id, role) -> an unstarted box of the chosen runner."""
    from pickfit.verify.box import BoxLimits, DockerBox

    if runner == "modal":
        from pickfit.verify.modal_box import ModalBox

        return lambda run_id, role: ModalBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                             limits=BoxLimits(lifetime_s=lifetime_s))
    return lambda run_id, role: DockerBox(platform=platform, labels={"pickfit.run": run_id, "pickfit.role": role},
                                          limits=BoxLimits(lifetime_s=lifetime_s))


def run(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    if args.limits_test:
        from pickfit.verify.agent import _runs_dir
        from pickfit.verify.limits import limits_test

        results, _ = limits_test(box_factory(args.runner, 900, platform=args.platform), _runs_dir(None))
        return 0 if all(r.ok for r in results) else 1
    if not args.fixture and not args.batch:
        print("pickfit verify: give --fixture or --batch N")
        return 2
    limits = AgentLimits()
    if args.max_turns:
        limits = replace(limits, max_turns=args.max_turns)
    make_box = box_factory(args.runner, int(limits.max_seconds) + LIFETIME_MARGIN_S, platform=args.platform)
    if args.batch:
        return _batch(args, make_box, limits)
    outcome = verify_task(load_fixture(args.fixture), make_box, model=args.model, mode=args.mode or DEFAULT_MODE,
                          limits=limits, write=args.write_back, keep_agent_box=args.keep_box)
    print(json.dumps(outcome.summary(), ensure_ascii=False, indent=2))
    return 0 if outcome.passed else 1


def _batch(args: argparse.Namespace, make_box, limits) -> int:
    from pathlib import Path

    from pickfit.discover.run import pipeline_db_path
    from pickfit.meta import resolve_model
    from pickfit.verify.agent import DEFAULT_MODE, _runs_dir
    from pickfit.verify.batch import load_candidates, record_slugs, run_batch, verified_slugs
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.result import DATA_DIR

    runs_dir = _runs_dir(None)
    db = Path(args.db) if args.db else pipeline_db_path()
    if not db.exists():
        print(f"pickfit verify: no pipeline database at {db} (use --db)")
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    skip = verified_slugs(runs_dir, since=args.since) if args.since else \
        set() if args.force else verified_slugs(runs_dir)
    known = record_slugs(data_dir)
    repos = [*(args.repo or []), *(known if args.records else [])] or None
    if args.records and not known:
        print(f"pickfit verify: no records in {data_dir}")
        return 2
    items, skipped = load_candidates(db, limit=args.batch, repos=repos, categories=args.category,
                                     skip_slugs=skip, known_slugs=known)
    print(f"batch · {len(items)} to verify · {len(skipped)} set aside · {args.runner} · "
          f"concurrency {args.concurrency} · {resolve_model(args.model)}")
    for item in items:
        print(f"  {item.priority:+d} {item.task.slug:<28} {item.category:<9} {item.kind or '-':<12} "
              f"{item.full_name}")
    if args.dry_run:
        for s in skipped:
            print(f"  skip {s['slug']:<28} {s['reason']}")
        return 0
    if args.runner == "modal":  # build or fetch the image once, not in every thread
        from pickfit.verify.modal_box import ensure_published_image

        ensure_published_image()

    def verify(task, log):
        return verify_task(task, make_box, model=args.model, mode=args.mode or DEFAULT_MODE, limits=limits,
                           runs_dir=runs_dir, log=log, write=args.write_back, data_dir=data_dir)

    summary = run_batch(items, verify, concurrency=args.concurrency, runs_dir=runs_dir,
                        meta={"db": str(db), "runner": args.runner, "model": resolve_model(args.model),
                              "skipped": skipped})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
