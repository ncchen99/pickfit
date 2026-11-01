"""`pickfit verify`: agent, replay and judge for a fixture or a batch, in Docker, on Modal, or in a macOS or Windows VM."""

from __future__ import annotations

import argparse
import json

LIFETIME_MARGIN_S = 120  # the box outlives the agent's time limit, so the last turn still has it
MAC_GUI_AGENT_S = 45 * 60  # tart + display: room for a desktop app's long download (tart_box.GUI_COMMAND_S)
TART_MAX_VMS = 2  # Apple's limit on macOS VMs running at once on one Mac
# Display boxes: room for operate_gui (one per listed feature) after the install and the launch.
GUI_LIMITS = {"max_turns": 32, "max_commands": 20, "max_seconds": 35 * 60, "scope_cap_usd": 0.80}
VBOX_MAX_VMS = 1  # one Windows base, reset from its snapshot for every box


def add_parser(sub: argparse._SubParsersAction) -> None:
    v = sub.add_parser("verify", help="install, smoke-test, replay and judge one tool in a sandbox with Muse Spark")
    v.add_argument("--fixture", help="JSON with slug, repo_url, readme_url and an ExtractionResult")
    v.add_argument("--batch", type=int, metavar="N", help="verify N extracted candidates from the pipeline database")
    v.add_argument("--concurrency", type=int, default=5, help="batch: tools verified at once (default 5)")
    v.add_argument("--db", default=None, help="batch: pipeline database (default runs/pipeline.db), read-only")
    v.add_argument("--repo", action="append", help="batch: only this repo id (gh:<id>) or owner/name")
    v.add_argument("--records", action="store_true",
                   help="batch: only candidates that have a record in --data-dir (the profiles)")
    v.add_argument("--category", action="append", choices=["dev_cli", "local_ai", "mcp_server"],
                   help="batch: only this category (repeatable)")
    v.add_argument("--force", action="store_true", help="batch: also tools that already have a run")
    v.add_argument("--since", metavar="YYYYmmdd-HHMMSS",
                   help="batch: skip only tools with a run started at or after this Taipei time")
    v.add_argument("--data-dir", default=None,
                   help="records to take slugs from and write back to (default data/software)")
    v.add_argument("--dry-run", action="store_true", help="batch: list what would run and why others are skipped")
    v.add_argument("--runner", choices=["docker", "modal", "tart", "vbox"], default="docker",
                   help="local DockerBox (development), ModalBox (gVisor on Modal), TartBox (macOS VM on this Mac) "
                        "or VBoxBox (Windows 11 VM in VirtualBox on this PC)")
    v.add_argument("--model", default=None,
                   help='agent model: "dev", "prod", "open" (Muse Spark Open on Baseten) or a model id '
                        '(default: PICKFIT_MODE); the judges stay on muse-spark-1.3 when it is "open"')
    v.add_argument("--extraction-model", default=None,
                   help='batch: verify only extractions by this model ("prod", "open" or an id)')
    v.add_argument("--mode", choices=["chain", "replay"], default=None,
                   help="carry history by previous_response_id (chain) or resend it (replay)")
    v.add_argument("--max-turns", type=int, default=None, help="turn limit (default 25)")
    v.add_argument("--gpu", choices=["T4", "L4", "A10"], default=None,
                   help="Modal: give each box this NVIDIA GPU (for tools whose core job needs one)")
    v.add_argument("--runtime", choices=["gvisor", "vm"], default="gvisor",
                   help="Modal: gVisor (default) or a microVM; a VM also drops DNS while the network is off")
    v.add_argument("--display", action="store_true",
                   help="Modal: a virtual display (Xvfb); tart: a desktop seen over VNC (the GUI base). Adds "
                        "launch_gui and operate_gui, so GUI apps can be launched, operated and checked (with more "
                        "time and commands per app)")
    v.add_argument("--platform", default="linux/amd64", help="Docker platform (Modal runs x86_64)")
    v.add_argument("--keep-box", action="store_true", help="Docker: leave the agent's container running")
    v.add_argument("--write-back", action="store_true",
                   help="record a passed, replayed run in data/software/<slug>.json")
    v.add_argument("--rejudge-features", action="store_true",
                   help="no box: run the feature judge on records' runs checked before it (from runs/verify evidence)")
    v.add_argument("--slug", action="append", help="--rejudge-features: only this record (repeatable)")
    v.add_argument("--limits-test", action="store_true",
                   help="no model: check the box's limits (user, metadata, network cut, memory, disk, pids)")
    v.add_argument("--prepare-base", action="store_true",
                   help="tart: build the base macOS VM the boxes clone (needs `tart pull` of the source image); "
                        "vbox: build the router VM and the Windows base (needs the ISOs in ~/.pickfit/vbox/iso)")
    v.add_argument("--iso", default=None, help="vbox --prepare-base: the Windows 11 Enterprise evaluation ISO")
    v.set_defaults(func=run)


def box_factory(runner: str, lifetime_s: int, *, platform: str = "linux/amd64", gpu: str | None = None,
                runtime: str = "gvisor", display: bool = False):
    """(run_id, role) -> an unstarted box of the chosen runner."""
    from pickfit.verify.box import BoxLimits, DockerBox

    if runner != "modal" and runtime != "gvisor":
        raise ValueError("--runtime needs --runner modal")
    if display and runner not in ("modal", "tart"):
        raise ValueError("--display needs --runner modal or tart")
    if runner == "tart":
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.tart_box import GUI_COMMAND_S, TartBox

        longer = {"max_command_s": GUI_COMMAND_S} if display else {}
        return lambda run_id, role: TartBox(limits=BoxLimits(lifetime_s=lifetime_s, **longer), display=display)
    if runner == "vbox":
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.vbox_box import VBoxBox

        return lambda run_id, role: VBoxBox(limits=BoxLimits(lifetime_s=lifetime_s))
    if runner == "modal":
        from pickfit.verify.modal_box import ModalBox

        return lambda run_id, role: ModalBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                             limits=BoxLimits(lifetime_s=lifetime_s), gpu=gpu, runtime=runtime,
                                             display=display)
    if gpu:
        raise ValueError("--gpu needs --runner modal")
    return lambda run_id, role: DockerBox(platform=platform, labels={"pickfit.run": run_id, "pickfit.role": role},
                                          limits=BoxLimits(lifetime_s=lifetime_s))


def run(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    if args.prepare_base:
        if args.runner == "vbox":
            from pathlib import Path

            from pickfit.verify.vbox_box import ROUTER_VM, VBox, prepare_base, prepare_router

            if VBox()("showvminfo", ROUTER_VM, check=False).returncode != 0:
                prepare_router()
            prepare_base(iso=Path(args.iso) if args.iso else None)
            return 0
        if args.runner != "tart":
            print("pickfit verify: --prepare-base needs --runner tart or vbox")
            return 2
        from pickfit.verify.tart_box import prepare_base, prepare_gui_base

        prepare_gui_base() if args.display else prepare_base()
        return 0
    if args.rejudge_features:
        return _rejudge(args)
    if args.runtime != "gvisor" and args.runner != "modal":
        print("pickfit verify: --runtime needs --runner modal")
        return 2
    if args.display and args.runner not in ("modal", "tart"):
        print("pickfit verify: --display needs --runner modal or tart")
        return 2
    if args.limits_test:
        from pickfit.verify.agent import _runs_dir
        from pickfit.verify.limits import limits_test

        results, _ = limits_test(box_factory(args.runner, 900, platform=args.platform, runtime=args.runtime,
                                             display=args.display), _runs_dir(None))
        return 0 if all(r.ok for r in results) else 1
    if not args.fixture and not args.batch:
        print("pickfit verify: give --fixture or --batch N")
        return 2
    limits = AgentLimits()
    if args.display:  # a GUI app also gets one operation per listed feature, each a few minutes of model turns
        limits = replace(limits, **GUI_LIMITS)
    if args.max_turns:
        limits = replace(limits, max_turns=args.max_turns)
    if args.gpu and args.runner != "modal":
        print("pickfit verify: --gpu needs --runner modal")
        return 2
    if args.runner == "tart" and args.display:
        limits = replace(limits, max_seconds=max(limits.max_seconds, MAC_GUI_AGENT_S))
    make_box = box_factory(args.runner, int(limits.max_seconds) + LIFETIME_MARGIN_S, platform=args.platform,
                           gpu=args.gpu, runtime=args.runtime, display=args.display)
    if args.batch:
        if args.runner == "tart" and args.concurrency > TART_MAX_VMS:
            print(f"pickfit verify: macOS allows {TART_MAX_VMS} VMs at once; concurrency {args.concurrency} -> "
                  f"{TART_MAX_VMS}")
            args.concurrency = TART_MAX_VMS
        if args.runner == "vbox" and args.concurrency > VBOX_MAX_VMS:
            print(f"pickfit verify: one Windows box at a time; concurrency {args.concurrency} -> {VBOX_MAX_VMS}")
            args.concurrency = VBOX_MAX_VMS
        return _batch(args, make_box, limits)
    outcome = verify_task(load_fixture(args.fixture), make_box, model=args.model, mode=args.mode or DEFAULT_MODE,
                          limits=limits, write=args.write_back, keep_agent_box=args.keep_box)
    print(json.dumps(outcome.summary(), ensure_ascii=False, indent=2))
    return 0 if outcome.passed else 1


def _rejudge(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pickfit.verify.agent import _runs_dir
    from pickfit.verify.feature_judge import rejudge_record
    from pickfit.verify.pipeline import judge_model_for
    from pickfit.verify.result import DATA_DIR

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    rows = []
    for path in sorted(data_dir.glob("*.json")):
        if args.slug and path.stem not in args.slug:
            continue
        row = rejudge_record(path, _runs_dir(None), model=judge_model_for(args.model), force=args.force,
                             log=lambda line, s=path.stem: print(f"[{s}] {line}"))
        if row["judged"] or row["skipped"]:
            rows.append(row)
    print(json.dumps({"records": len(rows), "features_judged": sum(r["judged"] for r in rows),
                      "lowered": sum(r["lowered"] for r in rows),
                      "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
                      "rows": rows}, ensure_ascii=False, indent=2))
    return 0


def _batch(args: argparse.Namespace, make_box, limits) -> int:
    from pathlib import Path

    from pickfit.discover.run import pipeline_db_path
    from pickfit.meta import resolve_model
    from pickfit.verify.agent import DEFAULT_MODE, _runs_dir
    from pickfit.verify.batch import (
        load_candidates,
        recheck_slugs,
        record_categories,
        record_slugs,
        run_batch,
        verified_slugs,
    )
    from pickfit.verify.pipeline import judge_model_for, verify_task
    from pickfit.verify.result import DATA_DIR

    runs_dir = _runs_dir(None)
    db = Path(args.db) if args.db else pipeline_db_path()
    if not db.exists():
        print(f"pickfit verify: no pipeline database at {db} (use --db)")
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    runner = {"tart": "tart-vz", "vbox": "vbox"}.get(args.runner)  # macOS/Windows runs do not count Linux ones
    skip = verified_slugs(runs_dir, since=args.since, runner=runner) if args.since else \
        set() if args.force else verified_slugs(runs_dir, runner=runner)
    skip -= recheck_slugs(data_dir, runs_dir)  # a new release since the last attempt, which did not pass
    known = record_slugs(data_dir)
    extraction_model = resolve_model(args.extraction_model) if args.extraction_model else None
    repos = [*(args.repo or []), *(known if args.records else [])] or None
    if args.records and not known:
        print(f"pickfit verify: no records in {data_dir}")
        return 2
    items, skipped = load_candidates(db, limit=args.batch, repos=repos, categories=args.category,
                                     skip_slugs=skip, known_slugs=known,
                                     known_categories=record_categories(data_dir), gpu=bool(args.gpu),
                                     os={"tart": "macos", "vbox": "windows"}.get(args.runner, "linux"),
                                     display=args.display, extraction_model=extraction_model)
    print(f"batch · {len(items)} to verify · {len(skipped)} set aside · {args.runner}"
          f"{' ' + args.runtime if args.runner == 'modal' else ''}{' + display' if args.display else ''}"
          f"{' + ' + args.gpu if args.gpu else ''} · "
          f"concurrency {args.concurrency} · agent {resolve_model(args.model)} · "
          f"judges {resolve_model(judge_model_for(args.model))}"
          f"{' · extractions by ' + extraction_model if extraction_model else ''}")
    for item in items:
        print(f"  {item.priority:+d} {item.task.slug:<28} {item.category:<9} {item.kind or '-':<12} "
              f"{item.full_name}")
    if args.dry_run:
        for s in skipped:
            print(f"  skip {s['slug']:<28} {s['reason']}")
        return 0
    if args.runner == "modal":  # build or fetch the image once, not in every thread
        from pickfit.verify.modal_box import ensure_published_image

        ensure_published_image(runtime=args.runtime, display=args.display)

    def verify(task, log):
        return verify_task(task, make_box, model=args.model, mode=args.mode or DEFAULT_MODE, limits=limits,
                           runs_dir=runs_dir, log=log, write=args.write_back, data_dir=data_dir)

    summary = run_batch(items, verify, concurrency=args.concurrency, runs_dir=runs_dir,
                        meta={"db": str(db), "runner": args.runner, "runtime": args.runtime, "display": args.display,
                              "gpu": args.gpu, "model": resolve_model(args.model),
                              "judge_model": resolve_model(judge_model_for(args.model)),
                              "extraction_model": extraction_model,
                              "skipped": skipped})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
